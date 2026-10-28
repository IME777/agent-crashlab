"""Build the public, browser-local recorded-evidence viewer.

This copies a positive allowlist of assets and previously sanitized reports. It
does not load .env, make API calls, publish a site, or run a model/worker.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
from urllib.parse import urlparse
import zipfile


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ("index.html", "app.js", "style.css")
REPORTS = ("live-check.json", "live-check-initial.json", "offline-check.json")
SENSITIVE_KEYS = {"api_key", "authorization", "access_token", "refresh_token", "password", "credentials", "secret"}
PRIVATE_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)")


def _reject_sensitive(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                raise ValueError("A report contains a credential field; refusing publication.")
            _reject_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive(item)
    elif isinstance(value, str) and PRIVATE_PATH.search(value):
        raise ValueError("A report contains a private local filesystem path; refusing publication.")


def _digest(run):
    source = run["checkpoint"]["source"]
    if not isinstance(source, str):
        raise ValueError("Evidence candidate source must be text.")
    return hashlib.sha256(source.encode()).hexdigest()


def _check_case(case, model):
    run = case["report"]
    tests = run["checkpoint"]["tests"]
    metrics = run["metrics"]
    if not (run["provider"] == "nebius" and run["model"] == model
            and run["checkpoint"].get("response_model") == model
            and run["status"] == "passed" and tests["passed"] is True
            and tests["returncode"] == 0 and tests["mode"] == "docker"
            and run["eligibility"]["live_nvidia_model"] is True
            and metrics["fixture_calls"] == 0 and metrics["model_calls"] > 0):
        raise ValueError("A case is not a verified real-model Docker result.")
    for name in ("model_calls", "input_tokens", "output_tokens", "unknown_usage_requests"):
        if not isinstance(metrics[name], int) or isinstance(metrics[name], bool) or metrics[name] < 0:
            raise ValueError("Evidence accounting fields must be nonnegative integers.")
    if not run["events"] or not all(isinstance(event.get("at"), str) and isinstance(event.get("message"), str) for event in run["events"]):
        raise ValueError("Evidence is missing its recorded event trail.")
    if not re.search(r"Ran [1-9]\d* tests?", tests["stdout"]):
        raise ValueError("Evidence is missing its independent test count.")


def validate_evidence(final, initial, offline):
    """Reject a false-positive result before it becomes a public success page."""
    for report in (final, initial, offline):
        _reject_sensitive(report)
    model = final.get("model", "")
    if not isinstance(model, str) or not model.startswith("nvidia/"):
        raise ValueError("Expected a recorded NVIDIA model ID.")
    if final.get("complete") is not True or final.get("passed") is not True:
        raise ValueError("Final live verification did not pass.")
    if initial.get("complete") is not True or initial.get("passed") is not False:
        raise ValueError("The preserved initial failed strict check is missing.")
    expected = {"no_fault_repair", "worker_crash_and_resume"}
    for report in (final, initial):
        if report.get("mode") != "live_nebius_verification" or report.get("model") != model:
            raise ValueError("Live evidence mode or model is inconsistent.")
        if len(report["cases"]) != 2 or {case["name"] for case in report["cases"]} != expected:
            raise ValueError("Expected exactly the recorded repair and recovery cases.")
        for case in report["cases"]:
            _check_case(case, model)
    if not all(final.get("checks", {}).values()) or not final.get("checks"):
        raise ValueError("The final batch has a failed or missing strict check.")
    for case in final["cases"]:
        if not case.get("checks") or not all(case["checks"].values()):
            raise ValueError("A final case has a failed or missing strict check.")
    recovery = next(case for case in final["cases"] if case["name"] == "worker_crash_and_resume")
    before, after = recovery["before_resume"], recovery["report"]
    if not (before["status"] == "crashed" and before["phase"] == "validate"
            and before["fault_triggered"] is True
            and any(event["kind"] == "worker_exited" and event["detail"].get("returncode") == 86 for event in before["events"])
            and _digest(before) == _digest(after)
            and after["metrics"]["restarts"] == before["metrics"]["restarts"] + 1
            and all(before["metrics"][key] == after["metrics"][key] for key in ("model_calls", "input_tokens", "output_tokens"))):
        raise ValueError("The saved-patch recovery evidence does not satisfy its claimed boundary.")
    initial_recovery = next(case for case in initial["cases"] if case["name"] == "worker_crash_and_resume")
    initial_before, initial_after = initial_recovery["before_resume"], initial_recovery["report"]
    if not (initial_before["status"] == "crashed"
            and ".append(" in initial_before["checkpoint"]["source"]
            and _digest(initial_before) != _digest(initial_after)
            and initial_after["metrics"]["model_calls"] > initial_before["metrics"]["model_calls"]
            and initial_recovery["checks"].get("same_saved_candidate") is False
            and initial_recovery["checks"].get("no_additional_model_requests_after_resume") is False):
        raise ValueError("Initial evidence does not match the preserved constraint-mismatch narrative.")
    if not (offline.get("gate_passed") is True and offline.get("provider") == "fixture"
            and all(run["metrics"]["model_calls"] == 0 for run in offline.get("reports", []))):
        raise ValueError("Offline evidence must remain explicitly fixture-only.")
    cases = [case["report"] for batch in (initial, final) for case in batch["cases"]]
    summary = {"model": model, "task_id": final["task_id"],
               "final": {"cases": len(final["cases"]),
                         "model_requests": sum(case["report"]["metrics"]["model_calls"] for case in final["cases"])},
               "all_attempts": {"model_requests": sum(run["metrics"]["model_calls"] for run in cases),
                                "input_tokens": sum(run["metrics"]["input_tokens"] for run in cases),
                                "output_tokens": sum(run["metrics"]["output_tokens"] for run in cases),
                                "unknown_usage_requests": sum(run["metrics"]["unknown_usage_requests"] for run in cases)}}
    return summary


def _safe_archive_member(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    return not any(part == ".git" or part.startswith(".crashlab") or part == "__pycache__"
                   or (part.startswith(".env") and part != ".env.example") for part in path.parts)


def _check_archive(path):
    """Inspect without extracting; never publish a supplied credential archive."""
    token = os.getenv("NEBIUS_API_KEY", "").encode()
    total = 0
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > 5000:
                raise ValueError("Source archive has too many entries.")
            for member in members:
                if not _safe_archive_member(member.filename) or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Source archive contains an unsafe or private path.")
                total += member.file_size
                if total > 50_000_000:
                    raise ValueError("Source archive exceeds the public demo size limit.")
                if not member.is_dir() and token and token in archive.read(member):
                    raise ValueError("Source archive contains a configured credential value.")
        return ".zip"
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            count = 0
            for member in archive:
                count += 1
                if count > 5000 or not _safe_archive_member(member.name) or not (member.isfile() or member.isdir()):
                    raise ValueError("Source archive contains an unsafe or private entry.")
                total += member.size
                if total > 50_000_000:
                    raise ValueError("Source archive exceeds the public demo size limit.")
                if member.isfile() and token:
                    handle = archive.extractfile(member)
                    if handle and token in handle.read():
                        raise ValueError("Source archive contains a configured credential value.")
        return ".tar.gz"
    raise ValueError("Source archive must be a .zip or .tar.gz file.")


def _repository_url(url):
    if url is None:
        return None
    parsed = urlparse(url)
    if not (parsed.scheme == "https" and parsed.netloc == "github.com"
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path)):
        raise ValueError("Repository URL must be an exact public HTTPS GitHub repository URL.")
    return url.rstrip("/")


def build_site(output: Path, *, root: Path = ROOT, repository_url=None, source_archive: Path | None = None):
    root = root.resolve()
    output = output.absolute()
    if output.is_symlink():
        raise ValueError("Output cannot be a symbolic link.")
    output = output.resolve()
    if output == root or output in {root / "web-demo", root / "examples", root / "crashlab", root / "docs"}:
        raise ValueError("Output must be a dedicated build directory.")
    repository_url = _repository_url(repository_url)
    reports = {}
    for name in REPORTS:
        path = root / "examples" / name
        if path.is_symlink():
            raise ValueError("Evidence reports cannot be symbolic links.")
        reports[name] = json.loads(path.read_text())
    summary = validate_evidence(reports[REPORTS[0]], reports[REPORTS[1]], reports[REPORTS[2]])
    archive_extension = _check_archive(source_archive) if source_archive else None
    archive_relative = f"downloads/agent-crashlab-source{archive_extension}" if source_archive else None
    permitted = {"index.html", "app.js", "style.css", "site-config.json", "build-manifest.json", "_headers",
                 "data/summary.json", *(f"data/{name}" for name in REPORTS),
                 "downloads/agent-crashlab-source.zip", "downloads/agent-crashlab-source.tar.gz"}
    if output.exists():
        existing = {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file() or path.is_symlink()}
        if existing - permitted or any(path.is_symlink() for path in output.rglob("*")):
            raise ValueError("Output contains unmanaged files; refusing to package them.")
    output.mkdir(parents=True, exist_ok=True)
    for path in output.rglob("*"):
        if path.is_file() and path.relative_to(output).as_posix() in permitted:
            path.unlink()
    for name in ASSETS:
        source = root / "web-demo" / name
        if source.is_symlink() or not source.is_file():
            raise ValueError("A required viewer asset is missing or linked.")
        shutil.copyfile(source, output / name)
    (output / "data").mkdir(exist_ok=True)
    for name in REPORTS:
        (output / "data" / name).write_text(json.dumps(reports[name], indent=2, ensure_ascii=False) + "\n")
    (output / "data" / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    config = {"mode": "recorded_evidence", "new_inference": False, "hosted_worker": False,
              "repository_url": repository_url, "source_archive": archive_relative}
    (output / "site-config.json").write_text(json.dumps(config, indent=2) + "\n")
    if source_archive:
        (output / "downloads").mkdir(exist_ok=True)
        shutil.copyfile(source_archive, output / archive_relative)
    (output / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'\n")
    files = {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(output.rglob("*")) if path.is_file()}
    manifest = {"schema_version": "1", "mode": "recorded_evidence", "files": files, "evidence_summary": summary}
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository-url")
    parser.add_argument("--source-archive", type=Path)
    args = parser.parse_args()
    try:
        manifest = build_site(args.output, repository_url=args.repository_url, source_archive=args.source_archive)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile, tarfile.TarError):
        parser.exit(2, "Recorded viewer build failed validation; inspect local source/evidence without publishing it.\n")
    print(json.dumps({"output": str(args.output.resolve()), "files": len(manifest["files"]) + 1,
                      "mode": manifest["mode"], "evidence_summary": manifest["evidence_summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
