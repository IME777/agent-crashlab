# Devpost submission copy

Status: written for review; not submitted. Replace the pending link fields only with verified public URLs. The project was built during the August 26–October 30, 2026 submission period; no earlier project version is being claimed.

## Submission fields

| Field | Value |
|---|---|
| Project name | Agent CrashLab |
| Tagline | Break the worker. Check the recovery. Keep the evidence. |
| Track | Coding and Agentic Engineering |
| Public source repository | https://github.com/IME777/agent-crashlab |
| Recorded evidence and source test build | https://agent-crashlab-evidence-jm.emiandtuzi.chatgpt.site — public recorded-evidence viewer and downloadable runnable source; hosted live worker is not yet deployed |
| Public YouTube video | PENDING_PUBLIC_YOUTUBE_URL — upload the final recording and verify it is shorter than 3 minutes |
| License | MIT |
| Source candidate | `v0.1.0-rc.1`; select the final submitted revision when freezing the entry |
| Model | `nvidia/nemotron-3-super-120b-a12b` through Nebius Token Factory |

## Inspiration

A coding agent can produce a correct patch in one successful run, yet leave a developer uncertain about what happens when its worker stops. Does recovery reuse completed work? Does it call the model again? Does the delivered patch still pass its tests?

I built Agent CrashLab to make those questions inspectable. It applies familiar reliability techniques to a small agent workflow and turns the result into a repeatable experiment with explicit acceptance checks.

## What it does

Agent CrashLab runs a code-repair task, injects a controlled worker failure, and checks the recovered artifact against independent tests. The dashboard shows the patch, execution trail, test output, model requests, and reported token usage. A downloadable report preserves the configuration and evidence.

The current task catalogue contains three small Python repairs. The verified live example repairs half-open pagination ranges and invalid-input handling. Developers can use the CLI to run checks before changing an agent configuration. Offline fixtures are clearly labelled and are used to test the infrastructure without model requests.

## How we built it

The control plane uses Python, an explicit bounded state machine, and SQLite in WAL mode. Each run starts an owned worker process. The model ID is pinned for that run, and the provider asks NVIDIA Nemotron on Nebius Token Factory to return a `submit_patch` function call containing the repaired source.

The worker commits the patch and known usage before the fault boundary. The selected fault then terminates the real worker with exit code 86. Recovery reconstructs the workspace from that checkpoint and continues to validation.

Model-generated code is restricted to the pure-function task domain and tested inside Docker, with no network, a read-only filesystem, a non-root user, and resource limits. The agent cannot edit the acceptance tests. Reports include runtime, task, and candidate hashes, plus explicit accounting for requests whose token usage is unknown.

The original contribution is the combination of reproducible fault boundaries, artifact-based acceptance, and inspectable release checks for this coding-agent workflow. Persistence, retries, and checkpointing themselves are established techniques.

## Challenges we ran into

The first live attempt exposed a useful distinction. Nemotron produced a repair using `list.append`, which violated the execution domain's existing method-call restriction. The agent repaired that after receiving validation feedback, and both runs ultimately passed their tests. However, the interrupted run needed another model request after recovery, so the stricter same-patch and no-additional-inference checks correctly failed.

We retained that report, made the generic execution contract explicit in the task prompt, and reran the same two-case check. We did not supply a reference answer or weaken the guard or acceptance tests.

## Accomplishments that we're proud of

The final live check passed both cases using the actual NVIDIA model response and Docker acceptance:

| Final case | Model requests | Reported input / output tokens | Independent tests |
|---|---:|---:|---|
| No-fault repair | 1 | 626 / 283 | 4/4 passed |
| Worker crash and one resume | 1 | 626 / 352 | 4/4 passed |

The recovery case preserved the candidate hash. Its model request count stayed at one, and its known token totals did not change when it resumed. Both final cases had zero fixture steps and zero requests with unknown usage.

The publication candidate passed 80 offline tests, an 18-configuration fixture smoke matrix, and 14 local HTTP checks. A separate real Docker check confirmed that killing the owned worker during a test removed its run-labelled container. Deployment controls and source-archive safety are covered locally; remote VM operation is not claimed.

Across the initial and final live attempts, there were six inference requests and 5,303 reported tokens. All attempts are retained in the repository. These are small smoke checks, not a held-out coding benchmark or a statistical reliability result.

## What we learned

Recovery correctness and candidate correctness need separate evidence. A system can faithfully recover an invalid patch, then legitimately need another repair. A useful release check must expose that distinction rather than turn every eventual success into a claim of zero recovery cost.

We also learned to place the execution contract where the model can follow it, preserve failed checks, and measure the exact boundary being claimed. A checkpoint cannot guarantee that an interrupted external inference request executes or bills exactly once.

## What's next for Agent CrashLab

Expand the independent task set, separate development tasks from held-out checks, and repeat fault experiments. Add a framework-default recovery baseline, more interruption windows, cancellation, and resource controls. A separate self-hosted inference experiment would be needed before claiming GPU-serving or inference-optimization results.

## Built with

Python · SQLite · Docker · JavaScript · HTML · CSS · Nebius Token Factory · NVIDIA Nemotron

No model training, GPU self-hosting, Kubernetes deployment, or third-party workflow framework is claimed in this version.

## Evidence and final checks

- [Final live check](../examples/live-check.json)
- [Preserved initial live check](../examples/live-check-initial.json)
- [Verification record](VERIFICATION.md)
- [Judge guide](JUDGE-GUIDE.md)
- [Tooling feedback](TOOLING-FEEDBACK.md)
- [Video script and filming notes](DEMO-SCRIPT.md)

Before copying into Devpost, verify every public link, remove unresolved link fields, confirm the hosted mode is described accurately, and attach the actual public video. The final Devpost submission has not been made.
