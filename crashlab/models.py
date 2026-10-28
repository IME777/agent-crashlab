"""Account-scoped model discovery; never expose credentials or raw responses."""

import json
import os
import re
import urllib.error
import urllib.request

from .provider import ProviderError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward the credential to a different destination.
        return None


def list_nvidia_models() -> list[str]:
    key = os.getenv("NEBIUS_API_KEY", "")
    if not key:
        raise ProviderError("NEBIUS_API_KEY is not configured. Save the key in local .env first.")
    request = urllib.request.Request(
        "https://api.tokenfactory.nebius.com/v1/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ProviderError("Model catalogue exceeded the expected size limit.")
        catalogue = json.loads(body)
        if not isinstance(catalogue, dict) or not isinstance(catalogue.get("data"), list):
            raise ProviderError("Nebius returned an unexpected model catalogue format.")
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        action = {401: "Check that this is a valid Token Factory API key.",
                  403: "Check the key's project and model access permissions."}.get(code, "Check Token Factory availability.")
        raise ProviderError(f"Model catalogue returned HTTP {code}. {action}") from None
    except (urllib.error.URLError, TimeoutError):
        raise ProviderError("Could not reach the Nebius model catalogue; no model inference was attempted.") from None
    except (UnicodeError, ValueError):
        raise ProviderError("Nebius returned invalid model catalogue JSON.") from None
    return sorted({entry["id"] for entry in catalogue["data"]
                   if isinstance(entry, dict) and isinstance(entry.get("id"), str)
                   and entry["id"].lower().startswith("nvidia/")
                   and re.fullmatch(r"[A-Za-z0-9_.\-/]{1,256}", entry["id"])})


def catalogue_summary() -> dict:
    models = list_nvidia_models()
    configured = os.getenv("NEBIUS_MODEL", "")
    return {"configured_model": configured or None,
            "configured_model_available": configured in models,
            "nvidia_models": models,
            "inference_requests": 0,
            "note": "Catalogue visibility does not prove billing access or successful tool calling."}
