"""Validate the production proxy template in the official image with test-only credentials."""

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {"PATH": os.environ.get("PATH", os.defpath)}
    for name in ["HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"]:
        if os.getenv(name):
            env[name] = os.environ[name]
    # The official binary carries NET_BIND_SERVICE file capabilities; retain that
    # single capability so Linux permits exec, even though this check binds no ports.
    base = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--cap-add=NET_BIND_SERVICE",
            "--tmpfs", "/data", "--tmpfs", "/config"]
    # Public, fixed test input only: never a production credential or a loaded .env.
    hashed = subprocess.run(base + ["caddy:2", "caddy", "hash-password", "--plaintext", "test-only-not-a-judge-password"],
                            env=env, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
    env.update(CRASHLAB_DEMO_HOST="demo.example.com", CRASHLAB_JUDGE_PASSWORD_HASH=hashed)
    result = subprocess.run(base + ["-e", "CRASHLAB_DEMO_HOST", "-e", "CRASHLAB_JUDGE_PASSWORD_HASH",
                                    "--mount", f"type=bind,source={ROOT / 'deploy' / 'Caddyfile'},target=/etc/caddy/Caddyfile,readonly",
                                    "caddy:2", "caddy", "validate", "--config", "/etc/caddy/Caddyfile"],
                            env=env, capture_output=True, text=True, timeout=30)
    report = {"mode": "proxy_configuration_only", "passed": result.returncode == 0,
              "returncode": result.returncode, "image": "caddy:2",
              "notes": ["Test-only password hash; no private environment file was read.",
                        "No public port was bound and no remote VM or TLS certificate was provisioned."]}
    (ROOT / "examples" / "proxy-check.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise SystemExit("Proxy validation could not complete; inspect the Docker/test environment. No production secrets were read.")
