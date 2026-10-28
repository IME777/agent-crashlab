"""Nebius function calling adapter. Offline fixtures are explicitly separate."""

import json
import os
import socket
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    def __init__(self, message: str, retryable=False, retry_after=0, usage=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.usage = usage


def submit_patch(task: dict, previous: dict, provider: str, *, model: str | None = None) -> dict:
    if provider == "fixture":
        return {"source": task["solution"], "input_tokens": 0, "output_tokens": 0,
                "usage_known": True, "live": False}
    api_key = os.getenv("NEBIUS_API_KEY", "")
    model = model if model is not None else os.getenv("NEBIUS_MODEL", "")
    if not api_key or not model:
        raise ProviderError("Set NEBIUS_API_KEY and NEBIUS_MODEL in local .env, then restart the server.")
    if not model.lower().startswith("nvidia/"):
        raise ProviderError("Select an NVIDIA model ID (nvidia/...) for the hackathon mode.")
    source = previous.get("source", task["starter"])
    feedback = previous.get("tests", {}).get("stdout", "No previous attempt.")[-6000:]
    payload = {
        "model": model, "temperature": 0, "max_tokens": 2500,
        "messages": [
            {"role": "system", "content": "You repair a small Python module. Return its entire corrected source using submit_patch. Preserve public function signatures. Only change solution.py. Use pure functions, direct builtins and comprehensions. Attribute access and method calls such as list.append, decorators, imports, file access, network, subprocesses, external packages and top-level execution are not allowed."},
            {"role": "user", "content": f"Task: {task['description']}\n\nExecution contract: the submitted module is checked before tests. Define plain functions only. ALL attribute access and object method calls are rejected, including list.append(), even when the logic is correct. Build lists with comprehensions or list concatenation. Use direct builtins such as range, min, max, len, type and isinstance. Do not use imports, decorators or top-level calls.\n\nCurrent solution.py:\n{source}\n\nPrevious independent test output:\n{feedback}"},
        ],
        "tools": [{"type": "function", "function": {"name": "submit_patch",
                   "description": "Submit the complete corrected solution.py module.",
                   "parameters": {"type": "object", "properties": {"source": {"type": "string"}},
                                  "required": ["source"], "additionalProperties": False}}}],
        "tool_choice": {"type": "function", "function": {"name": "submit_patch"}},
    }
    request = urllib.request.Request("https://api.tokenfactory.nebius.com/v1/chat/completions",
                                     data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        # No automatic HTTP retries: every attempt is accounted for by the worker.
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ProviderError("Model response exceeded the one-megabyte limit.")
        result = json.loads(body)
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After", "0")
        try:
            delay = min(max(float(retry_after), 0), 10)
        except ValueError:
            delay = 0
        exc.close()
        # Never place provider response bodies or auth headers in logs/reports.
        raise ProviderError(f"Nebius returned HTTP {exc.code}.", exc.code in {429, 500, 502, 503, 504}, delay) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout):
        raise ProviderError("Nebius connection failed or timed out; billed token usage may be unknown.", True) from None
    except (ValueError, UnicodeError):
        raise ProviderError("Nebius returned an invalid JSON response.") from None
    if not isinstance(result, dict):
        raise ProviderError("Nebius returned an unexpected response shape.")
    usage = result.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    usage_known = all(isinstance(usage.get(k), int) and not isinstance(usage[k], bool) and usage[k] >= 0
                      for k in ["prompt_tokens", "completion_tokens"])
    try:
        calls = result["choices"][0]["message"].get("tool_calls", [])
        call = next(c for c in calls if c.get("function", {}).get("name") == "submit_patch")
        source = json.loads(call["function"]["arguments"])["source"]
        if not isinstance(source, str) or not source.strip() or len(source.encode()) > 65_536:
            raise ValueError()
    except (KeyError, IndexError, StopIteration, TypeError, ValueError, AttributeError):
        raise ProviderError("Model did not return a valid submit_patch tool call.",
                            usage={"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]}
                            if usage_known else None) from None
    return {"source": source, "input_tokens": usage["prompt_tokens"] if usage_known else 0,
            "output_tokens": usage["completion_tokens"] if usage_known else 0,
            "usage_known": usage_known,
            "live": True, "response_model": result.get("model", model)}
