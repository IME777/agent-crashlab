"""Validate private VM configuration, then start the loopback app and TLS proxy."""

import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import urllib.request
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crashlab.hosting import request_allowlist


def read_environment(path: Path) -> dict:
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if not sep or name.strip() in values:
            raise ValueError("Private environment file has an invalid or duplicate field.")
        values[name.strip()] = value.strip().strip("\"'")
    return values


def validate(runtime: dict, proxy: dict) -> None:
    origin = runtime.get("CRASHLAB_PUBLIC_ORIGIN", "")
    request_allowlist(8765, origin)
    if not origin or "YOUR_" in origin or urlsplit(origin).netloc != proxy.get("CRASHLAB_DEMO_HOST"):
        raise ValueError("Configure one matching public HTTPS origin and proxy hostname.")
    if len(runtime.get("NEBIUS_API_KEY", "")) < 8 or not runtime.get("NEBIUS_MODEL", "").lower().startswith("nvidia/"):
        raise ValueError("Configure a genuine Token Factory key and NVIDIA model privately.")
    limit = int(runtime.get("CRASHLAB_MAX_LIVE_RUNS", "0"))
    if not 1 <= limit <= 100:
        raise ValueError("Choose a cumulative live allowance between 1 and 100 runs.")
    password_hash = proxy.get("CRASHLAB_JUDGE_PASSWORD_HASH", "")
    if not password_hash.startswith(("$2a$", "$2b$", "$2y$")) or len(password_hash) != 60:
        raise ValueError("Configure a bcrypt judge password hash from caddy hash-password.")


def main():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Activate only as root on the intended Linux VM.")
    config = Path("/etc/agent-crashlab")
    runtime = read_environment(config / "runtime.env")
    proxy = read_environment(config / "proxy.env")
    validate(runtime, proxy)
    subprocess.run(["caddy", "validate", "--config", "/etc/caddy/Caddyfile"],
                   env={"PATH": os.defpath, "HOME": "/var/lib/caddy", **proxy}, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "agent-crashlab"], check=True)
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/healthz", timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit("Application health check failed; inspect its service status locally.")
    subprocess.run(["systemctl", "enable", "--now", "caddy"], check=True)
    print("Application healthy; HTTPS proxy started. Verify public access and judge login externally.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError):
        raise SystemExit("Activation failed. Check private configuration and service status on the VM; values were not printed.")
