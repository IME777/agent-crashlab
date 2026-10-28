#!/usr/bin/env bash
# Fresh, dedicated Ubuntu 24.04 VM only. This does not purchase a VM or start paid inference.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(id -u)" != 0 ]]; then
  echo "Run this installer as root on a fresh dedicated Ubuntu VM." >&2
  exit 2
fi
if [[ $# != 1 || ! -f "$1" ]]; then
  echo "Usage: sudo bash deploy/install.sh /tmp/agent-crashlab-source.tar.gz" >&2
  exit 2
fi
if [[ -e /opt/agent-crashlab || -e /etc/systemd/system/agent-crashlab.service ]]; then
  echo "Existing installation found. Preserve it and use the documented update procedure." >&2
  exit 2
fi
if command -v ss >/dev/null && ss -H -ltn '( sport = :80 or sport = :443 )' | read -r _; then
  echo "Ports 80/443 are already in use. This installer requires a dedicated VM." >&2
  exit 2
fi
CRASHLAB_ARCHIVE=$(realpath "$1")
python3 - "$CRASHLAB_ARCHIVE" <<'PY'
from pathlib import Path, PurePosixPath
import sys, tarfile
release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_ID', '').strip('"') != '24.04':
    raise SystemExit('Use a fresh Ubuntu 24.04 VM for this installation recipe.')
with tarfile.open(sys.argv[1], 'r:gz') as archive:
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts
                or path.parts[0] != 'agent-crashlab' or not member.isfile()):
            raise SystemExit('Source archive contains unsupported or unsafe members.')
PY
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 docker.io ca-certificates curl gnupg debian-keyring debian-archive-keyring apt-transport-https
# Use Caddy's official stable repository; Ubuntu's older package can lack basic_auth.
CRASHLAB_CADDY_KEY=$(mktemp)
curl --fail --silent --show-error --location https://dl.cloudsmith.io/public/caddy/stable/gpg.key --output "$CRASHLAB_CADDY_KEY"
gpg --batch --yes --dearmor --output /usr/share/keyrings/caddy-stable-archive-keyring.gpg "$CRASHLAB_CADDY_KEY"
rm -f "$CRASHLAB_CADDY_KEY"
curl --fail --silent --show-error --location https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt --output /etc/apt/sources.list.d/caddy-stable.list
chmod 0644 /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
systemctl enable --now docker
docker pull python:3.12-slim
id crashlab >/dev/null 2>&1 || useradd --system --home /var/lib/agent-crashlab --shell /usr/sbin/nologin crashlab
usermod -aG docker crashlab
install -d -m 0755 /opt/agent-crashlab /etc/agent-crashlab
tar -xzf "$CRASHLAB_ARCHIVE" --strip-components=1 -C /opt/agent-crashlab
chown -R root:root /opt/agent-crashlab
install -d -o crashlab -g crashlab -m 0700 /var/lib/agent-crashlab /var/lib/agent-crashlab/tmp /var/lib/agent-crashlab/runs
install -m 0600 /opt/agent-crashlab/deploy/environment.example /etc/agent-crashlab/runtime.env
install -m 0600 /opt/agent-crashlab/deploy/proxy-environment.example /etc/agent-crashlab/proxy.env
install -m 0644 /opt/agent-crashlab/deploy/agent-crashlab.service /etc/systemd/system/agent-crashlab.service
install -d -m 0755 /etc/systemd/system/caddy.service.d
install -m 0644 /opt/agent-crashlab/deploy/caddy-environment.conf /etc/systemd/system/caddy.service.d/agent-crashlab.conf
install -m 0644 /opt/agent-crashlab/deploy/Caddyfile /etc/caddy/Caddyfile
cd /opt/agent-crashlab
runuser -u crashlab -- /usr/bin/python3 -m deploy.seed_demo --data /var/lib/agent-crashlab/runs
systemctl disable --now caddy
systemctl daemon-reload
echo "Installed without starting inference. Configure /etc/agent-crashlab/runtime.env and proxy.env privately."
echo "Then run: sudo python3 /opt/agent-crashlab/deploy/activate.py"
