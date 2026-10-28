"""Small local configuration loader; credentials never enter reports."""

import os
from pathlib import Path
import subprocess


def load_env(path: Path | None = None) -> None:
    path = path or Path.cwd() / ".env"
    if not path.is_file():
        return
    allowed = {"NEBIUS_API_KEY", "NEBIUS_MODEL"}
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key in allowed and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


def docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def public_config() -> dict:
    from .sandbox import preflight_docker
    docker = docker_available()
    image = preflight_docker()["available"] if docker else False
    return {
        "nebius_key_configured": bool(os.getenv("NEBIUS_API_KEY")),
        "nebius_model": os.getenv("NEBIUS_MODEL") or None,
        "docker_available": docker,
        "docker_test_image_available": image,
        "fixture_mode_available": True,
        "version": "0.1.0",
    }
