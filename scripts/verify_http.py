"""Smoke-check a running localhost control plane. Uses fixtures only."""

import json
from pathlib import Path
import time
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8765"


def call(path, payload=None, *, headers=None, raw=None):
    body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(BASE + path, data=body,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read()
            return response.status, json.loads(data), dict(response.headers)
    except urllib.error.HTTPError as error:
        with error:
            return error.code, json.loads(error.read()), dict(error.headers)


def await_status(run_id, target):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        code, report, _ = call(f"/api/runs/{run_id}")
        if report["status"] == target:
            # Wait for the supervisor to finalize its exit event as well.
            if target == "crashed" and not any(e["kind"] == "worker_exited" for e in report["events"]):
                time.sleep(0.05)
                continue
            return report
        if report["status"] in {"blocked", "failed"}:
            raise AssertionError(f"Unexpected {report['status']} run")
        time.sleep(0.05)
    raise AssertionError(f"Run did not become {target}")


def main():
    checks = {}
    code, tasks, _ = call("/api/tasks")
    checks["public_catalogue_omits_answers"] = code == 200 and all("solution" not in t and "tests" not in t for t in tasks)
    code, config, _ = call("/api/config")
    checks["config_has_no_secret_value"] = code == 200 and "NEBIUS_API_KEY" not in config and "api_key" not in config
    checks["invalid_provider_rejected"] = call("/api/runs", {"task_id": tasks[0]["id"], "provider": "invalid"})[0] == 400
    checks["unknown_task_rejected"] = call("/api/runs", {"task_id": "unknown"})[0] == 404
    checks["malformed_json_rejected"] = call("/api/runs", raw=b"{")[0] == 400
    checks["cross_origin_mutation_rejected"] = call("/api/runs", {"task_id": tasks[0]["id"]}, headers={"Origin": "https://example.invalid"})[0] == 403
    code, created, _ = call("/api/runs", {"task_id": tasks[0]["id"], "provider": "fixture",
                                          "policy": "resume", "fault": "worker_crash_after_patch"})
    checks["create_returns_created"] = code == 201
    run_id = created["id"]
    checks["start_returns_ok"] = call(f"/api/runs/{run_id}/start", {})[0] == 200
    crashed = await_status(run_id, "crashed")
    checks["real_crash_preserves_patch"] = bool(crashed["checkpoint"].get("source"))
    checks["resume_returns_ok"] = call(f"/api/runs/{run_id}/resume", {})[0] == 200
    passed = await_status(run_id, "passed")
    checks["resume_acceptance_passed_without_regeneration"] = passed["checkpoint"]["tests"]["passed"] and passed["metrics"]["fixture_calls"] == 1
    checks["no_remote_model_calls"] = passed["metrics"]["model_calls"] == 0
    code, download, headers = call(f"/api/runs/{run_id}/report")
    checks["report_download_matches_run"] = code == 200 and download["id"] == run_id and "attachment" in headers.get("Content-Disposition", "")
    checks["cannot_restart_passed_run"] = call(f"/api/runs/{run_id}/start", {})[0] == 400
    result = {"mode": "localhost_http_fixture_smoke", "run_id": run_id, "checks": checks,
              "passed": all(checks.values()), "notes": ["No remote model calls. Local control-plane verification only."]}
    output = Path("examples/http-check.json")
    output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
