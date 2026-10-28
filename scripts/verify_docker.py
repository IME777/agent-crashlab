"""Explicit Docker integration check, never part of the default offline suite.

No model API calls or real credentials are needed. Requires the official test
image to have been prepared locally. Run: python3 -m scripts.verify_docker
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch

from crashlab.manager import Manager
from crashlab.sandbox import IMAGE, preflight_docker, run_tests
from crashlab.store import Store, now
from crashlab.tasks import get_task, list_tasks


def labelled_ids(run_id):
    result = subprocess.run(["docker", "ps", "-a", "--filter", f"label=agent-crashlab.run={run_id}",
                             "--format", "{{.ID}}"], capture_output=True, text=True, timeout=5, check=True)
    return result.stdout.strip().splitlines()


def main():
    readiness = preflight_docker()
    if not readiness["available"]:
        raise SystemExit(readiness["error"])
    image_id = subprocess.run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
                              capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    checks = []
    for metadata in list_tasks():
        task = get_task(metadata["id"])
        starter = run_tests(task["id"], task["starter"], "docker")
        solution = run_tests(task["id"], task["solution"], "docker")
        valid = not starter["passed"] and not starter.get("error") and solution["passed"]
        checks.append({"task_id": task["id"], "starter": starter, "trusted_solution": solution, "passed": valid})

    with tempfile.TemporaryDirectory(prefix="crashlab-kill-check-") as root:
        store = Store(root)
        manager = Manager(store)
        try:
            # A pre-seeded candidate tests execution/cleanup ONLY, with no inference stage.
            with patch.dict(os.environ, {"NEBIUS_API_KEY": "integration-placeholder-not-real",
                                        "NEBIUS_MODEL": "nvidia/integration-placeholder"}):
                run = store.create("capped-backoff", provider="nebius")
                def seed(r):
                    r["phase"] = "validate"
                    r["checkpoint"] = {"round": 1, "source":
                        "def capped_backoff(attempt, base_seconds, cap_seconds):\n    while True:\n        pass\n"}
                store.mutate(run["id"], seed)
                manager.start(run["id"])
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and not labelled_ids(run["id"]):
                    time.sleep(0.1)
                observed = bool(labelled_ids(run["id"]))
                if not observed:
                    raise RuntimeError("Did not observe the run-owned test container before the deadline")
                killed = manager.crash(run["id"])
            leftovers = labelled_ids(run["id"])
            cleanup = {"container_observed_before_kill": observed, "status": killed["status"],
                       "remaining_run_containers": leftovers, "model_requests": killed["metrics"]["model_calls"],
                       "passed": observed and not leftovers and killed["status"] == "crashed"
                                 and killed["metrics"]["model_calls"] == 0}
        finally:
            manager.close()

    report = {"created_at": now(), "mode": "docker_integration_without_model",
              "image": IMAGE, "image_id": image_id, "cases": checks,
              "manual_worker_kill_cleanup": cleanup,
              "passed": all(c["passed"] for c in checks) and cleanup["passed"],
              "notes": ["Candidate source is trusted fixture or explicitly pre-seeded test input.",
                        "No real model credentials or model API requests were used."]}
    output = Path("examples/docker-check.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({"passed": report["passed"], "tasks": len(checks), "kill_cleanup": cleanup,
                      "report": str(output)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
