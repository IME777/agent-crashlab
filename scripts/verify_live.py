"""Explicit, bounded live Nebius verification. Never falls back to fixtures.

Run from the repository root after local configuration:
    python3 -m scripts.verify_live

This script attempts at most two experiments: a no-fault repair and the same
task with a real worker exit after a durable patch checkpoint, followed by one
explicit resume. Transport/candidate retry limits belong to the worker.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from crashlab.config import load_env
from crashlab.manager import Manager
from crashlab.sandbox import preflight_docker
from crashlab.store import Store, now
from crashlab.tasks import get_task


def source_digest(report: dict) -> str | None:
    source = report.get("checkpoint", {}).get("source")
    return hashlib.sha256(source.encode()).hexdigest() if isinstance(source, str) else None


def case_checks(report: dict, model: str) -> dict:
    tests = report.get("checkpoint", {}).get("tests", {})
    return {
        "task_passed": report.get("status") == "passed" and tests.get("passed") is True,
        "live_nvidia_response": report.get("provider") == "nebius"
        and report.get("eligibility", {}).get("live_nvidia_model") is True,
        "docker_acceptance": tests.get("mode") == "docker" and tests.get("passed") is True,
        "pinned_model": report.get("model") == model,
        "remote_request_recorded": report.get("metrics", {}).get("model_calls", 0) > 0,
        "no_fixture_steps": report.get("metrics", {}).get("fixture_calls", 0) == 0,
    }


def recovery_checks(before: dict, after: dict, model: str) -> dict:
    checks = case_checks(after, model)
    digest_before = source_digest(before)
    digest_after = source_digest(after)
    checks.update({
        "observed_crashed_status": before.get("status") == "crashed",
        "crashed_after_patch_checkpoint": before.get("phase") == "validate"
        and bool(before.get("checkpoint", {}).get("source"))
        and before.get("fault_triggered") is True,
        "real_worker_exit_86": any(
            event.get("kind") == "worker_exited" and event.get("detail", {}).get("returncode") == 86
            for event in before.get("events", [])
        ),
        "same_saved_candidate": digest_before is not None and digest_before == digest_after,
        "no_additional_model_requests_after_resume": after.get("metrics", {}).get("model_calls")
        == before.get("metrics", {}).get("model_calls"),
        "known_token_totals_unchanged_on_resume": all(
            after.get("metrics", {}).get(key) == before.get("metrics", {}).get(key)
            for key in ("input_tokens", "output_tokens")
        ),
        "exactly_one_resume": after.get("metrics", {}).get("restarts")
        == before.get("metrics", {}).get("restarts", 0) + 1,
        "model_unchanged_on_resume": before.get("model") == after.get("model") == model,
    })
    return checks


def save_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def summary(report: dict, output: Path) -> dict:
    return {
        "mode": report["mode"], "complete": report["complete"], "passed": report["passed"],
        "model": report["model"], "task_id": report["task_id"],
        "cases": [{"name": case["name"], "run_id": case["report"]["id"],
                   "status": case["report"]["status"], "checks": case["checks"],
                   "metrics": case["report"]["metrics"]} for case in report["cases"]],
        "blockers": report["blockers"], "report": str(output),
    }


def verify(task_id: str, data: Path, output: Path) -> tuple[int, dict]:
    # Runtime-only credential loading. Credentials are never copied into output.
    load_env()
    model = os.getenv("NEBIUS_MODEL", "")
    report = {
        "schema_version": "1", "created_at": now(), "mode": "live_nebius_verification",
        "model": model or None, "task_id": task_id, "complete": False, "passed": False,
        "cases": [], "checks": {}, "blockers": [],
        "notes": [
            "Only two experiments are permitted: no fault, then worker crash and one resume.",
            "Token totals are reported known usage. Unknown requests may have incurred provider charges.",
            "Checkpoint recovery does not guarantee arbitrary external calls execute exactly once.",
            "These small task checks are not a general coding-quality or production reliability benchmark.",
        ],
    }
    manager = None
    active_id = None
    exit_code = 1
    try:
        get_task(task_id)
        if not os.getenv("NEBIUS_API_KEY"):
            report["blockers"].append("NEBIUS_API_KEY is not configured locally.")
        if not model or not model.lower().startswith("nvidia/"):
            report["blockers"].append("Choose an account-available NVIDIA NEBIUS_MODEL ID (nvidia/...).")
        readiness = preflight_docker()
        if not readiness["available"]:
            report["blockers"].append(readiness.get("error", "Docker acceptance environment is unavailable."))
        if report["blockers"]:
            exit_code = 2
            return exit_code, report

        store = Store(data)
        manager = Manager(store)
        run = store.create(task_id, provider="nebius", policy="resume", fault="none")
        active_id = run["id"]
        manager.start(active_id)
        baseline = manager.wait(active_id, timeout=600)
        active_id = None
        baseline_checks = case_checks(baseline, model)
        report["cases"].append({"name": "no_fault_repair", "report": baseline, "checks": baseline_checks})
        save_report(output, report)
        if not all(baseline_checks.values()):
            report["blockers"].append("The no-fault live repair did not pass; the fault experiment was not attempted.")
            return 1, report

        run = store.create(task_id, provider="nebius", policy="resume", fault="worker_crash_after_patch")
        active_id = run["id"]
        manager.start(active_id)
        before = manager.wait(active_id, timeout=600)
        active_id = None
        boundary_observed = before["status"] == "crashed" and before["phase"] == "validate" and any(
            event["kind"] == "worker_exited" and event["detail"].get("returncode") == 86
            for event in before["events"]
        )
        if boundary_observed:
            active_id = run["id"]
            manager.start(active_id, resume=True)
            after = manager.wait(active_id, timeout=600)
            active_id = None
        else:
            after = before
            report["blockers"].append("The expected worker exit after its saved patch was not observed; no resume was attempted.")
        checks = recovery_checks(before, after, model)
        report["cases"].append({
            "name": "worker_crash_and_resume", "before_resume": before,
            "report": after, "checks": checks,
            "recovery_comparison": {
                "source_sha256_before": source_digest(before), "source_sha256_after": source_digest(after),
                "metrics_before": before["metrics"], "metrics_after": after["metrics"],
            },
        })
        report["complete"] = True
        report["checks"] = {"no_fault_repair": all(baseline_checks.values()),
                            "worker_crash_and_resume": all(checks.values())}
        report["passed"] = all(report["checks"].values())
        if not report["passed"]:
            report["blockers"].append("The bounded live verification did not satisfy every acceptance and recovery check.")
        exit_code = 0 if report["passed"] else 1
        return exit_code, report
    except (ValueError, KeyError, TimeoutError, OSError) as error:
        # Avoid serializing exception messages that could include arbitrary data.
        report["blockers"].append(f"Verification stopped with {type(error).__name__}; inspect the saved run state locally.")
        if manager is not None and active_id:
            try:
                manager.crash(active_id)
            except ValueError:
                pass
            report["interrupted_run"] = manager.store.get(active_id)
        return 1, report
    finally:
        if manager is not None:
            manager.close()
        report["finished_at"] = now()
        save_report(output, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="page-slices")
    parser.add_argument("--data", type=Path, default=Path(".crashlab-live"))
    parser.add_argument("--output", type=Path, default=Path("examples/live-check.json"))
    args = parser.parse_args()
    code, report = verify(args.task, args.data, args.output)
    print(json.dumps(summary(report, args.output), indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
