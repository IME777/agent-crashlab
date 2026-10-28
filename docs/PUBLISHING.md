# Publication and deployment status

Status date: October 27, 2026, America/Los_Angeles. This is a release candidate,
not a submitted Devpost entry.

## Verified hosted result

**URL:** <https://agent-crashlab-evidence-jm.emiandtuzi.chatgpt.site>

- Published with public access after the owner's explicit audience approval.
- Anonymous browser access reaches the application without a login gate.
- This is an **interactive recorded-evidence viewer**, not a hosted Python worker.
- Final/initial attempt selection, recorded-event navigation, patch/test output,
  report downloads and a sanitized runnable source download are provided.
- The browser makes no model API calls and has no model key.

The published evidence uses actual saved model/Docker results. Its initial
strict-check failure remains visible. The source package is built by an allowlist,
contains an internal SHA-256 manifest, and excludes `.env`, Git history, runtime
databases, caches and private credential files.

## Public GitHub repository

**Repository:** <https://github.com/IME777/agent-crashlab>

The owner supplied this existing public target. Its initial commit `872fbb8`
and original MIT copyright notice are preserved. The publication candidate uses
tag `v0.1.0-rc.1`; this is not the final submission freeze. Remote CI status is
reported by the repository's live Actions badge rather than a hardcoded claim.

Prepared source includes an English README, MIT license, offline GitHub Actions,
contributing/security notes, release packaging, the full runtime, viewer source,
real evidence, deployment recipe and submission materials.

## Full live worker hosting

**Not provisioned or deployed.** The owner has no existing VM and asked for a
concrete configuration and price proposal first.

The proposed dedicated Ubuntu 24.04 x86 host has 2 vCPU / 2 GiB RAM and persistent
disk. At the investigated DigitalOcean $18/month or $0.02679/hour plan, 49 days is
about $31.51 before taxes; reserve $40 hosting budget plus tax, inference and any
new domain purchase through December 15. See the [prepared VM recipe](../deploy/README.md)
and [official pricing](https://www.digitalocean.com/pricing/droplets).

The recipe provides native systemd execution, host Docker, Caddy HTTPS with judge
login, an explicit Host/Origin allowlist, a persistent cumulative live-run limit,
six-request per-run cap, health checks and imported recorded history. No model
key is in the source package. Remote Ubuntu installation, TLS issuance, login,
fresh live run and external worker recovery remain to be verified on the actual
approved host.

## Ready writing materials

- [Devpost fields and project description](DEVPOST.md)
- [2:45 English demo script with filming notes](DEMO-SCRIPT.md)
- [Judge guide and local reproduction](JUDGE-GUIDE.md)
- [Observed Nebius/NVIDIA tooling feedback](TOOLING-FEEDBACK.md)

The YouTube recording/upload and final Devpost submission are not completed.
Keep the submitted revision and judge access available through December 15.
