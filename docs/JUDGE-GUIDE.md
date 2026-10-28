# Agent CrashLab — judge guide

Agent CrashLab checks whether a coding-agent task can recover after a controlled worker interruption and still deliver a patch that passes independent tests.

## Access links and mode

| Resource | Link / status |
|---|---|
| Public source repository | https://github.com/IME777/agent-crashlab |
| Public recorded evidence and source build | https://agent-crashlab-evidence-jm.emiandtuzi.chatgpt.site |
| Hosted mode | Recorded-evidence viewer plus runnable source download; a new live worker is not hosted on this website |
| Public video | **PENDING_PUBLIC_YOUTUBE_URL** |
| Source candidate | `v0.1.0-rc.1`; final submitted revision not yet frozen |
| Access through December 15, 2026 | Public viewer access verified October 27; owner must retain publication through judging |

The recorded-evidence URL is deployed with public access; it requires neither login nor an API key. Fields still marked PENDING are not verified links. The instructions below describe the runnable local system and its recorded evidence. See [deployment plan](../deploy/README.md) for the separate full-runtime VM package and operating budget.

### What each experience proves

| Experience | What it does | What it does not do |
|---|---|---|
| Operator-hosted live runtime, if provided | Starts a new owned worker, calls Nebius with the operator's server-side key, tests a new candidate, and supports actual interruption/recovery | Does not grant arbitrary shell or repository access |
| Recorded-evidence viewer, if provided | Lets you inspect and replay the ordered events, patch, tests, counters, and report from a captured real run | Playback does not make a new model request, start a new OS worker, or rerun Docker tests |
| Local source build | Runs the actual control plane and worker on your machine; supports offline fixtures or optional real inference | Real inference requires a local Token Factory key, model access, and Docker |

A hosted viewer must keep its replay label visible. A repository containing genuine model evidence does not turn a browser-only replay into a new live experiment. Conversely, the replay is useful for inspecting captured evidence without supplying credentials or consuming model credits.

## Inspect the verified result in two minutes

1. Open [the final live report](../examples/live-check.json). Confirm `mode=live_nebius_verification`, `complete=true`, and `passed=true`.
2. Find `no_fault_repair`: actual model `nvidia/nemotron-3-super-120b-a12b`, one request, zero fixture steps, and four passing Docker acceptance tests.
3. Find `worker_crash_and_resume`. Its `before_resume` has status `crashed`, phase `validate`, and a `worker_exited` event with return code 86.
4. Compare the saved candidate hash and counters before and after the resume. Requests remain 1; reported usage remains 626 input / 352 output tokens; all four Docker tests pass.
5. Open [the initial live attempt](../examples/live-check-initial.json). Both tasks eventually passed, but an invalid candidate required another repair. The stricter same-patch and no-additional-inference checks correctly returned false. This unsuccessful strict check was retained.

For the full evidence index, see [VERIFICATION.md](VERIFICATION.md). The live sample covers one small pagination-repair task and a specific post-checkpoint failure boundary. It does not support a general coding-quality or production-reliability claim.

## Run the local application without credentials

Requirements: Python 3.11+ on macOS or Linux. There are no third-party Python runtime dependencies or frontend build steps.

From a checkout of the source repository:

```bash
python3 -m crashlab serve
```

Open `http://127.0.0.1:8765`. Select **Offline fixture**, choose a task, select **Resume from checkpoint** and **Worker crash after patch**, then click **Run experiment**. After the status becomes **INTERRUPTED**, click **Resume run**. Inspect the timeline, patch, test output, and report download.

Fixture mode supplies a known trusted patch. Its counters use `fixture_calls`; it does not ask a model to solve the task and is not evidence of NVIDIA model quality.

The CLI can exercise the same bounded recovery comparison:

```bash
python3 -m crashlab --data /tmp/crashlab-judge-demo demo
python3 -m crashlab --data /tmp/crashlab-judge-check check \
  --output /tmp/crashlab-judge-check/report.json
python3 -m unittest discover -s tests -v
```

`demo` and the default `check` use fixtures. The matrix is three tasks × two policies × three fault profiles, one execution each. It is a plumbing smoke check, not a statistical benchmark. A single control-plane lease protects each data directory; use a separate directory for CLI work while the server runs.

## Optional fresh real-model reproduction

Judges should not need to provide a private key to inspect the submitted hosted demonstration and captured evidence. The following is optional reproduction on a local machine with your own account.

1. Follow [NEBIUS-SETUP.zh-CN.md](NEBIUS-SETUP.zh-CN.md) or the English [README](../README.md) to save a Token Factory key and an account-available NVIDIA model ID in ignored local `.env`.
2. Start Docker and prepare the official image: `docker pull python:3.12-slim`.
3. Run the readiness and account-catalogue checks:

```bash
python3 -m crashlab doctor
python3 -m crashlab models
```

4. Run the explicit two-case live verification:

```bash
python3 -m scripts.verify_live --task page-slices \
  --data .crashlab-live --output examples/live-check.json
```

This makes metered model requests. It attempts one no-fault repair, then one controlled crash and one resume. Candidate/transport retries are bounded. It stops on a failed prerequisite or no-fault check, never substitutes fixture output, and preserves failures. A new run may produce different code and token counts.

To inspect those new live records in the dashboard after stopping another server on that port:

```bash
python3 -m crashlab --data .crashlab-live serve
```

The agent cannot modify the acceptance harness. Real candidates execute in restricted Docker containers, not host Python. The model is pinned per run. Known usage and unknown-usage requests are separate; an external response lost before checkpointing can still be repeated or billed again.

## Expected scope and known limits

- Three small pure-function repair tasks are implemented; only `page-slices` has the submitted live two-case verification.
- Live recovery is verified at the saved-patch boundary. Broader interruption windows and a real restart-from-scratch comparison remain future work.
- The synthetic 429 profile is clearly labelled. It does not indicate an observed Nebius outage.
- Docker limits and the AST domain guard provide containment for a single-operator demo, not a hardened hostile multi-tenant service.
- The repository includes model integration and agent infrastructure; it does not claim model training or GPU-serving optimization.

## Operator checklist before giving this guide to judges

- [ ] Replace every pending access field with a verified URL/revision/mode.
- [ ] Confirm a visitor can reach the demo without supplying a private API key.
- [ ] If live execution is offered, document any access instructions and enforce its actual run/spend limits.
- [ ] If a viewer is offered, label playback and link the underlying unmodified reports and runnable source build.
- [ ] Test the submitted route from a fresh, unauthenticated browser session.
- [ ] Preserve the submitted version and visitor access through December 15, 2026.
- [ ] Record any access limitation explicitly in Devpost testing instructions rather than implying public live execution exists.
