# Full judge-runtime deployment

This package preserves the actual Python subprocess and host-Docker execution
path. It is separate from the public recorded-evidence viewer. No VM has been
created and these production services have not yet been verified on a remote host.

## Proposed host and approval boundary

Use a **dedicated Ubuntu 24.04 x86 VM**, 2 vCPU / 2 GiB RAM, with persistent disk
and a public IPv4 address. The current concrete proposal is DigitalOcean Basic
Regular at $18/month ($0.02679/hour), with 60 GiB disk and bundled IPv4. Forty-nine
days is approximately $31.51 at that hourly rate; allow **$40 hosting budget plus
tax and Nebius inference** through December 15. Monthly caps can change the actual
bill. [Official pricing](https://www.digitalocean.com/pricing/droplets).

The estimate excludes a new domain purchase if one is needed. An existing domain
or a separately verified free IP-based DNS hostname can avoid that purchase.

Before provisioning, the owner must supply the destination account/SSH target
and approve its spending limit. Token Factory credentials do not grant VM access.
An existing compatible VM can be used instead. A hostname pointing to that VM
and inbound TCP 22/80/443 are required; keep TCP 8765 private.

## Prepared installation

Build the sanitized package locally:

```bash
python3 -m scripts.package_release --format tar.gz \
  --output dist/agent-crashlab-source.tar.gz --scan-local-env
```

Verify its SHA-256 sidecar, then transfer it to the approved VM. The exact host
and SSH identity must be supplied by the owner; no target is invented here.
On the fresh VM, extract a copy of the installer from the archive and run:

```bash
tar -xzf /tmp/agent-crashlab-source.tar.gz -C /tmp agent-crashlab/deploy/install.sh
sudo bash /tmp/agent-crashlab/deploy/install.sh /tmp/agent-crashlab-source.tar.gz
```

The installer refuses existing installations or ports already serving traffic.
It installs distro Python and Docker, plus Caddy's official stable package; prepares the official test image;
creates the service user and persistent data directory; and seeds clearly
labelled imported evidence. It does not start model inference. The archive uses
normal file permissions, so run shell scripts with `bash` rather than relying on
an executable bit.

Privately configure `/etc/agent-crashlab/runtime.env` and `proxy.env` from the
included examples. Both are root-owned mode 0600 and stay outside source. Generate
the judge password interactively using `caddy hash-password`; store only its hash
in `proxy.env`. Supply the actual judge password only through Devpost's private
testing instructions. Never publish it in README, screenshots or source.

Activate after setting the real domain and secrets:

```bash
sudo python3 /opt/agent-crashlab/deploy/activate.py
```

## Access and execution model

- Caddy terminates HTTPS and requires the `judge` account for the application.
  `/healthz` reports only service health without authentication.
- The control plane binds **127.0.0.1:8765**. The explicit HTTPS origin is added
  to Host/Origin checks; headers are not stripped to bypass them.
- By default there are **30 cumulative live runs**, including imported live
  evidence. Each run has at most **6 remote requests across retries/recovery**,
  two candidate patches and 2,500 output tokens per request.
- Existing reports remain readable when the allowance is reached. Source and
  fixture checks remain available. An operator must review allowance changes.
- The single service owns one active worker. Only preset task IDs and options
  are accepted; no arbitrary repository, shell command or source upload exists.
- The service user belongs to the host Docker group. This is administrative
  access on the dedicated VM; the candidate container receives neither that
  socket nor model credentials. This setup is not a multi-tenant sandbox.

Native systemd execution avoids a nested-container path mismatch: Docker must
be able to see the temporary paths it bind-mounts for acceptance tests.

## External acceptance before sharing with judges

1. Resolve the hostname and verify a publicly trusted HTTPS certificate.
2. Check `/healthz` externally; verify the app requires judge login.
3. Verify an incorrect login cannot read configuration or start work.
4. Log in as a judge, inspect imported evidence, and download its report.
5. Run one permitted live task with crash/recovery and verify real Docker tests,
   unchanged saved patch, known usage and clean container shutdown.
6. Confirm a disallowed Origin/Host and exhausted allowance are rejected.
7. Record host, source revision, image ID, exact URL and operating owner.

## Operation through December 15

Keep the VM, domain, certificate and model credits active through judging.
Check `systemctl status agent-crashlab caddy docker` and `/healthz`; inspect logs
without copying private environment values. The app does not log auth headers or
request bodies. Do not expose the Docker socket over TCP.

Back up SQLite with its online backup API, not by copying only the main file
while WAL writes are active. Keep credentials in a separate private backup.
Before an update, retain the old source package and a database backup; use the
same persistent data directory and verify recorded results afterward. The
initial installer intentionally refuses to overwrite an existing installation.

After the submission deadline, preserve the judged revision. After judging ends,
export needed evidence, revoke the VM-side model key when appropriate, and remove
paid infrastructure only after the owner confirms it is no longer needed.
