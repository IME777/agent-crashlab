"""Independent acceptance runner.

``fixture`` is a trusted offline smoke mode, NOT a sandbox: it refuses every
source except the built-in task's known starter and solution. Arbitrary model
output may only use the Docker mode. Docker execution is bounded and isolated
for this local MVP; it is not advertised as a hostile multi-tenant sandbox.
"""

import ast
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from .tasks import get_task


IMAGE = "python:3.12-slim"
MAX_SOURCE_BYTES = 64 * 1024
TEST_TIMEOUT_SECONDS = 12
MAX_OUTPUT_BYTES = 64 * 1024
RUN_LABEL = "agent-crashlab.run"
PURE_BUILTINS = frozenset({
    "min", "max", "range", "len", "int", "float", "type", "isinstance", "any", "all",
    "enumerate", "zip", "ValueError", "TypeError", "abs", "sum", "bool", "list", "tuple",
    "sorted", "set", "dict", "round", "reversed", "str", "pow", "divmod", "Exception",
})


def _source_error(source: str) -> str | None:
    if not isinstance(source, str):
        return "Candidate source must be text no larger than 64 KiB."
    try:
        if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            return "Candidate source must be text no larger than 64 KiB."
    except UnicodeEncodeError:
        return "Candidate source contains invalid Unicode."
    return None


def validate_candidate(source: str) -> str | None:
    """Limit this benchmark to pure-function repairs; this is not a sandbox.

    Docker provides execution isolation. The AST policy also prevents submitted
    code from importing or monkeypatching the independent acceptance harness.
    """
    size_error = _source_error(source)
    if size_error:
        return size_error
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        return f"Candidate syntax is invalid: {getattr(exc, 'msg', type(exc).__name__)}."
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not functions:
        return "Candidate must define at least one top-level function."
    for node in tree.body:
        docstring = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        if not isinstance(node, ast.FunctionDef) and not docstring:
            return "Only function definitions and docstrings are allowed at module level."
    banned = (ast.Import, ast.ImportFrom, ast.Attribute, ast.Global, ast.Nonlocal,
              ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda)
    for node in ast.walk(tree):
        if isinstance(node, banned):
            return f"Candidate uses unsupported syntax: {type(node).__name__}."
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            return "Decorators are not allowed in pure-function repair tasks."
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.arg)):
            names.append(node.name if isinstance(node, ast.FunctionDef) else node.arg)
        if any("__" in name for name in names):
            return "Dunder names are not allowed in pure-function repair tasks."
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in PURE_BUILTINS | functions:
                return "Only direct calls to named pure builtins or declared functions are allowed."
    return None


def preflight_docker() -> dict:
    """Check local execution prerequisites before spending model tokens."""
    if not shutil.which("docker"):
        return {"available": False, "error": "Docker CLI is unavailable. Install Docker and start its daemon."}
    try:
        inspected = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True,
            text=True, timeout=5, env=_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "error": "Docker is not responding. Start Docker and prepare python:3.12-slim."}
    if inspected.returncode:
        return {"available": False, "error": (
            "Docker daemon or python:3.12-slim image is unavailable. Start Docker, "
            "then run: docker pull python:3.12-slim. Images are never pulled automatically."
        )}
    return {"available": True}


def cleanup_run_containers(run_id: str) -> dict:
    """Remove only Docker containers labelled with a validated CrashLab run ID.

    Safe for a manager to call after abnormal worker exit. Both Docker commands
    have five-second limits; at most 32 validated container IDs are removed.
    """
    result = {"removed": []}
    if not isinstance(run_id, str) or re.fullmatch(r"[0-9a-f]{16}", run_id) is None:
        return {**result, "error": "Run ID must be exactly 16 lowercase hexadecimal characters."}
    if not shutil.which("docker"):
        return {**result, "error": "Docker CLI is unavailable; labelled containers could not be checked."}
    try:
        listed = subprocess.run(
            ["docker", "ps", "--filter", f"label={RUN_LABEL}={run_id}", "--format", "{{.ID}}"],
            capture_output=True, text=True, timeout=5, env=_env(),
        )
        if listed.returncode:
            return {**result, "error": "Docker could not list this run's containers. Check its daemon."}
        container_ids = list(dict.fromkeys(listed.stdout.split()))
        if len(container_ids) > 32 or any(re.fullmatch(r"(?:[0-9a-f]{12}|[0-9a-f]{64})", token) is None
                                         for token in container_ids):
            return {**result, "error": "Docker returned an invalid or excessive container ID list; nothing was removed."}
        if container_ids:
            removed = subprocess.run(["docker", "rm", "-f", *container_ids],
                                     capture_output=True, text=True, timeout=5, env=_env())
            if removed.returncode:
                return {**result, "error": "Docker could not remove all containers for this run. Check its daemon."}
            result["removed"] = container_ids
        return result
    except (OSError, subprocess.TimeoutExpired):
        return {**result, "error": "Docker cleanup did not complete within its command deadline."}


def _container_deadline_wrapper() -> str:
    """Trusted PID-1 wrapper: test deadline survives death of the host worker."""
    return (
        "import subprocess, sys\n"
        "try:\n"
        "    completed = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test_acceptance'], "
        f"timeout={TEST_TIMEOUT_SECONDS!r})\n"
        "    sys.exit(completed.returncode)\n"
        "except subprocess.TimeoutExpired:\n"
        "    print('Acceptance tests exceeded the container execution deadline.', flush=True)\n"
        "    sys.exit(124)\n"
    )


def _env() -> dict[str, str]:
    """Deliberately avoid copying model credentials or other host secrets."""
    result = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1"}
    # Docker's desktop CLI needs HOME to discover its socket/config, but we do
    # not forward this value or any host environment variable into the container.
    if os.environ.get("HOME"):
        result["HOME"] = os.environ["HOME"]
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"):
        if os.environ.get(key):
            result[key] = os.environ[key]
    return result


def _result(start: float, mode: str, returncode: int, stdout: str = "", error: str | None = None) -> dict:
    result = {
        "passed": returncode == 0 and error is None,
        "returncode": returncode,
        "stdout": stdout[-24000:],
        "duration_ms": round((time.monotonic() - start) * 1000),
        "mode": mode,
    }
    if error:
        result["error"] = error
    return result


def _execute(command: list[str], cwd: Path) -> tuple[int, str, str | None]:
    """Drain output with a size/deadline bound rather than unbounded capture."""
    deadline = time.monotonic() + TEST_TIMEOUT_SECONDS
    output = bytearray()
    error = None
    with subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, env=_env()) as process:
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    error = f"Acceptance tests exceeded the {TEST_TIMEOUT_SECONDS}-second limit."
                    break
                for key, _ in selector.select(min(remaining, 0.25)):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = MAX_OUTPUT_BYTES - len(output)
                    output.extend(chunk[:available])
                    if len(chunk) > available:
                        error = "Acceptance test output exceeded the 64 KiB limit."
                        break
                if error:
                    break
        if error:
            process.kill()
            process.wait()
            return 124, output.decode("utf-8", errors="replace"), error
        try:
            returncode = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return 124, output.decode("utf-8", errors="replace"), "Acceptance test process did not exit in time."
    return returncode, output.decode("utf-8", errors="replace"), None


def run_tests(task_id: str, source: str, mode: str = "fixture", *, run_id: str | None = None) -> dict:
    start = time.monotonic()
    if mode not in {"fixture", "docker"}:
        return _result(start, mode, 2, error="Test mode must be 'fixture' or 'docker'.")
    if run_id is not None and (not isinstance(run_id, str) or re.fullmatch(r"[0-9a-f]{16}", run_id) is None):
        return _result(start, mode, 2, error="Run ID must be exactly 16 lowercase hexadecimal characters.")
    owner_id = run_id if run_id is not None else uuid.uuid4().hex[:16]
    try:
        task = get_task(task_id)
    except KeyError as exc:
        return _result(start, mode, 2, error=str(exc))
    validation_error = _source_error(source)
    if mode == "docker" and not validation_error:
        validation_error = validate_candidate(source)
    if validation_error:
        result = _result(start, mode, 1, stdout=f"Candidate rejected: {validation_error}")
        result.update(candidate_invalid=True, validation_error=validation_error)
        return result
    if mode == "fixture" and source not in (task["starter"], task["solution"]):
        return _result(start, mode, 2, error=(
            "Fixture mode accepts only trusted built-in source. Start Docker and "
            "use docker mode to execute model-generated patches."
        ))
    if mode == "docker":
        preflight = preflight_docker()
        if not preflight["available"]:
            return _result(start, mode, 2, error=preflight["error"])

    container_name = f"crashlab-test-{uuid.uuid4().hex}"
    with tempfile.TemporaryDirectory(prefix="crashlab-acceptance-") as directory:
        work = Path(directory)
        work.chmod(0o755)
        (work / "solution.py").write_text(source, encoding="utf-8")
        (work / "test_acceptance.py").write_text(task["tests"], encoding="utf-8")
        for path in work.iterdir():
            path.chmod(0o644)
        command = [sys.executable, "-B", "-m", "unittest", "-v", "test_acceptance"]
        if mode == "docker":
            command = [
                "docker", "run", "--rm", "--pull=never", "--name", container_name,
                "--label", f"{RUN_LABEL}={owner_id}",
                "--network=none", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--pids-limit=64",
                "--memory=256m", "--cpus=1", "--user=65534:65534",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "--workdir=/work",
                "--mount", f"type=bind,source={work},target=/work,readonly",
                IMAGE, "python", "-B", "-c", _container_deadline_wrapper(),
            ]
        try:
            returncode, output, error = _execute(command, work)
            if returncode == 124:
                # A candidate exhausting its execution budget is an acceptance
                # failure, not a missing-environment blocker.
                reason = error or "Acceptance tests exceeded the container execution deadline."
                result = _result(start, mode, returncode, output + "\n" + reason)
                result.update(candidate_invalid=True, resource_exceeded=True, execution_error=reason)
                return result
            if mode == "docker" and returncode in {125, 126, 127}:
                return _result(start, mode, returncode, output,
                               "Docker could not launch the test command. Check its daemon and python:3.12-slim image.")
            return _result(start, mode, returncode, output, error)
        except OSError as exc:
            return _result(start, mode, 2, error=f"Could not start acceptance tests: {exc.strerror}.")
        finally:
            if mode == "docker":
                # A killed docker CLI does not necessarily kill its container.
                try:
                    subprocess.run(["docker", "rm", "-f", container_name],
                                   capture_output=True, timeout=5, env=_env())
                except (OSError, subprocess.TimeoutExpired):
                    pass
