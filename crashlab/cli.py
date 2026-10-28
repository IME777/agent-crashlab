"""CLI reports support a bounded release check; no external CI service required."""

import argparse
import json
from pathlib import Path
import sys

from .config import load_env, public_config
from .manager import Manager
from .store import Store, now
from .tasks import list_tasks


def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def complete(manager, run, auto_resume):
    manager.start(run["id"])
    result = manager.wait(run["id"], timeout=600)
    if result["status"] == "crashed" and auto_resume:
        manager.start(run["id"], resume=True)
        result = manager.wait(run["id"], timeout=600)
    return result


def release_checks(run):
    fault_verified = run["fault"] == "none"
    if run["fault"] == "worker_crash_after_patch":
        fault_verified = run["fault_triggered"] and run["metrics"]["restarts"] > 0 and any(
            e["kind"] == "worker_exited" and e["detail"].get("returncode") == 86 for e in run["events"])
    elif run["fault"] == "model_429_once":
        fault_verified = run["fault_triggered"] and any(
            e["kind"] == "fault_injected" and e["detail"].get("synthetic") for e in run["events"])
    return {"acceptance_passed": run["status"] == "passed" and bool(run["checkpoint"].get("tests", {}).get("passed")),
            "fault_profile_verified": bool(fault_verified),
            "provider_evidence_valid": run["provider"] == "fixture" or run["eligibility"]["live_nvidia_model"]}


def main():
    parser = argparse.ArgumentParser(prog="crashlab")
    parser.add_argument("--data", default=".crashlab", help="Local run storage directory")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve", help="Open the local dashboard")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--public-origin", help="HTTPS origin of the authenticated reverse proxy")
    serve_parser.add_argument("--max-live-runs", type=int, help="Cumulative live run allowance for this data directory")
    sub.add_parser("doctor", help="Check live-mode prerequisites without inference")
    sub.add_parser("tasks")
    sub.add_parser("models", help="List account-visible NVIDIA models without inference")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("task_id")
    run_parser.add_argument("--provider", choices=["fixture", "nebius"], default="fixture")
    run_parser.add_argument("--policy", choices=["resume", "restart"], default="resume")
    run_parser.add_argument("--fault", choices=["none", "worker_crash_after_patch", "model_429_once"], default="none")
    run_parser.add_argument("--auto-resume", action="store_true")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("run_id")
    check_parser = sub.add_parser("check", help="Run all tasks against the same bounded fault matrix")
    check_parser.add_argument("--provider", choices=["fixture", "nebius"], default="fixture")
    check_parser.add_argument("--output", default=".crashlab/reports/check.json")
    demo_parser = sub.add_parser("demo", help="Compare restart and resume under a worker crash")
    demo_parser.add_argument("--task", default="capped-backoff")
    args = parser.parse_args()
    load_env()
    if args.command == "doctor":
        from .sandbox import preflight_docker
        config = public_config()
        config["docker_test_image"] = preflight_docker()
        print_json(config)
        return 0
    if args.command == "tasks":
        print_json(list_tasks())
        return 0
    if args.command == "models":
        from .models import catalogue_summary
        from .provider import ProviderError
        try:
            print_json(catalogue_summary())
            return 0
        except ProviderError as error:
            print_json({"error": str(error), "inference_requests": 0})
            return 2
    if args.command == "serve":
        from .server import serve
        limit = args.max_live_runs if args.max_live_runs is not None else 30 if args.public_origin else None
        serve(args.data, port=args.port, public_origin=args.public_origin, max_live_runs=limit)
        return 0
    store = Store(args.data)
    if args.command == "report":
        print_json(store.get(args.run_id))
        return 0
    manager = Manager(store)
    try:
        if args.command == "run":
            result = complete(manager, store.create(args.task_id, args.provider, args.policy, args.fault), args.auto_resume)
            print_json(result)
            return {"passed": 0, "blocked": 2, "crashed": 3}.get(result["status"], 1)
        reports = []
        if args.command == "demo":
            configurations = [(args.task, policy, "worker_crash_after_patch") for policy in ["restart", "resume"]]
            provider = "fixture"
        else:
            configurations = [(task["id"], policy, fault) for task in list_tasks()
                              for policy in ["restart", "resume"]
                              for fault in ["none", "worker_crash_after_patch", "model_429_once"]]
            provider = args.provider
        for task_id, policy, fault in configurations:
            reports.append(complete(manager, store.create(task_id, provider, policy, fault), True))
            if reports[-1]["status"] == "blocked":
                break
        for report in reports:
            report["release_checks"] = release_checks(report)
        gate_passed = len(reports) == len(configurations) and all(all(r["release_checks"].values()) for r in reports)
        report = {"schema_version": "1", "created_at": now(), "provider": provider,
                  "gate_passed": gate_passed, "expected_runs": len(configurations),
                  "completed_runs": len(reports), "reports": reports,
                  "notes": ["Offline fixture results are not NVIDIA model evaluation or hackathon eligibility evidence.",
                            "Small smoke matrix; no statistical performance or production reliability claims."]}
        if args.command == "check":
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print_json(report)
        return 0 if gate_passed else 1
    finally:
        manager.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TimeoutError) as exc:
        print(f"CrashLab: {exc}", file=sys.stderr)
        raise SystemExit(2)
