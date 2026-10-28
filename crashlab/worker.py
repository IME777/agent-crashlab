"""One process per run; killing it cannot kill the HTTP control plane."""

import argparse
import difflib
import hashlib
import os
from pathlib import Path
import time
import threading

from .provider import ProviderError, submit_patch
from .sandbox import preflight_docker, run_tests
from .store import Store
from .tasks import get_task


def write_workspace(store, run_id, source):
    workspace = store.root / "workspaces" / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    temporary = workspace / "solution.py.tmp"
    temporary.write_text(source)
    os.replace(temporary, workspace / "solution.py")


def execute(store: Store, run_id: str):
    run = store.get(run_id)
    task = get_task(run["task_id"])
    if run["provider"] == "nebius" and (not os.getenv("NEBIUS_API_KEY") or not run["model"]):
        raise ProviderError("Configure NEBIUS_API_KEY and NEBIUS_MODEL in local .env and restart the server.")
    if run["provider"] == "nebius":
        if not run["model"].lower().startswith("nvidia/"):
            raise ProviderError("Choose an NVIDIA model ID (nvidia/...) before running the live experiment.")
        readiness = preflight_docker()
        if not readiness["available"]:
            raise ProviderError(readiness["error"])
    if run["phase"] == "prepare":
        write_workspace(store, run_id, task["starter"])
        store.mutate(run_id, lambda r: r.update(phase="model"), "prepared", "Task workspace prepared")

    for _ in range(3):
        run = store.get(run_id)
        checkpoint = run["checkpoint"]
        if run["phase"] == "model":
            if checkpoint.get("round", 0) >= 2:
                store.mutate(run_id, lambda r: r.update(status="failed", phase="done"),
                             "failed", "Repair budget exhausted after two candidate patches")
                return
            if run["fault"] == "model_429_once" and not run["fault_triggered"]:
                def inject(r):
                    r["fault_triggered"] = True
                    r["metrics"]["retries"] += 1
                store.mutate(run_id, inject, "fault_injected", "Synthetic HTTP 429 injected before provider call",
                             {"synthetic": True, "actual_api_request": False})
                store.event(run_id, "retry", "Bounded retry after injected 429")
                time.sleep(0.2)
            result = None
            for attempt in range(3):
                live = run["provider"] == "nebius"
                def request_start(r):
                    if live and r["metrics"]["model_calls"] >= 6:
                        raise ProviderError("This run reached its six-request inference limit, including recovery attempts.")
                    r["metrics"]["model_calls" if live else "fixture_calls"] += 1
                    r["request_pending"] = live
                store.mutate(run_id, request_start, "model_request" if live else "fixture_response",
                             "Requesting patch from Nebius" if live else "Loading trusted offline fixture (no API request)",
                             {"attempt": attempt + 1, "model": run["model"]})
                try:
                    result = submit_patch(task, checkpoint, run["provider"], model=run["model"])
                    break
                except ProviderError as exc:
                    def failed_request(r):
                        r["request_pending"] = False
                        if live and exc.usage is None:
                            r["metrics"]["unknown_usage_requests"] += 1
                        elif live:
                            r["metrics"]["input_tokens"] += exc.usage["input_tokens"]
                            r["metrics"]["output_tokens"] += exc.usage["output_tokens"]
                    store.mutate(run_id, failed_request, "provider_error", str(exc),
                                 {"retryable": exc.retryable, "usage_unknown": live and exc.usage is None})
                    if not exc.retryable or attempt == 2:
                        raise
                    store.mutate(run_id, lambda r: r["metrics"].update(retries=r["metrics"]["retries"] + 1),
                                 "retry", "Retrying transient provider failure", {"attempt": attempt + 2})
                    time.sleep(max(exc.retry_after, min(2 ** attempt, 4)))
            assert result is not None
            diff = "".join(difflib.unified_diff(task["starter"].splitlines(True),
                                              result["source"].splitlines(True),
                                              fromfile="before/solution.py", tofile="after/solution.py"))
            def save_patch(r):
                r["checkpoint"] = {"source": result["source"], "diff": diff,
                                   "round": checkpoint.get("round", 0) + 1,
                                   "source_sha256": hashlib.sha256(result["source"].encode()).hexdigest(),
                                   "response_model": result.get("response_model", "trusted-fixture-v1")}
                r["phase"] = "validate"
                r["request_pending"] = False
                r["metrics"]["input_tokens"] += result["input_tokens"]
                r["metrics"]["output_tokens"] += result["output_tokens"]
                if not result["usage_known"]:
                    r["metrics"]["unknown_usage_requests"] += 1
                if result["live"]:
                    r["eligibility"].update(live_nvidia_model=True, mode_label="Nebius live NVIDIA model response received")
            store.mutate(run_id, save_patch, "patch_checkpoint", "Patch and reported token usage committed atomically",
                         {"round": checkpoint.get("round", 0) + 1, "live": result["live"],
                          "source_sha256": hashlib.sha256(result["source"].encode()).hexdigest()})
            write_workspace(store, run_id, result["source"])
            current = store.get(run_id)
            if current["fault"] == "worker_crash_after_patch" and not current["fault_triggered"]:
                store.mutate(run_id, lambda r: r.update(fault_triggered=True, status="crashed"),
                             "fault_injected", "Worker exits immediately after the durable patch checkpoint",
                             {"exit_code": 86, "synthetic_trigger": True, "real_process_exit": True})
                os._exit(86)

        current = store.get(run_id)
        if current["phase"] == "validate":
            source = current["checkpoint"]["source"]
            # Re-materialize from the checkpoint after a crash between DB commit and file write.
            write_workspace(store, run_id, source)
            mode = "fixture" if current["provider"] == "fixture" else "docker"
            store.event(run_id, "testing", "Running independent acceptance tests", {"mode": mode})
            tests = run_tests(current["task_id"], source, mode, run_id=run_id)
            def save_tests(r):
                r["checkpoint"]["tests"] = tests
                if tests.get("error"):
                    r.update(status="blocked", phase="validate")
                elif tests["passed"]:
                    r.update(status="passed", phase="done")
                elif r["checkpoint"]["round"] >= 2:
                    r.update(status="failed", phase="done")
                else:
                    r["phase"] = "model"
            store.mutate(run_id, save_tests, "tests_passed" if tests["passed"] else "tests_failed",
                         "Independent tests passed" if tests["passed"] else "Independent tests did not pass",
                         {"passed": tests["passed"], "mode": mode, "error": tests.get("error"),
                          "validation_error": tests.get("validation_error"),
                          "execution_error": tests.get("execution_error"),
                          "source_sha256": hashlib.sha256(source.encode()).hexdigest()})
            if store.get(run_id)["status"] in {"passed", "failed", "blocked"}:
                return
    raise RuntimeError("Worker exhausted its bounded state transitions")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--parent", type=int)
    args = parser.parse_args()
    store = Store(Path(args.data))
    if args.parent:
        def parent_watch():
            while True:
                if os.getppid() != args.parent:
                    os._exit(87)
                time.sleep(0.2)
        threading.Thread(target=parent_watch, daemon=True).start()
    try:
        execute(store, args.run)
    except ProviderError as exc:
        store.mutate(args.run, lambda r: r.update(status="blocked"), "blocked", str(exc))
        return 2
    except Exception as exc:
        # Exception type only: exception text can contain arbitrary model/provider output.
        store.mutate(args.run, lambda r: r.update(status="failed"), "worker_error",
                     f"Worker stopped with {type(exc).__name__}; inspect local code and run report.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
