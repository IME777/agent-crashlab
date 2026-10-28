# Nebius and NVIDIA tooling feedback

This feedback is based on the recorded Agent CrashLab workflow. It distinguishes observations from suggested improvements and does not claim a provider outage, a performance benchmark, or an untested model capability.

## Tools actually used

- Nebius Token Factory model catalogue: authenticated `GET /v1/models`.
- Nebius Token Factory inference: `POST /v1/chat/completions` with the `submit_patch` function schema and explicit tool choice.
- NVIDIA model requested and returned: `nvidia/nemotron-3-super-120b-a12b`.
- Local Docker and Python acceptance tooling: candidate-domain validation, independent tests, worker interruption, and scoped container cleanup.

No Nebius AI Cloud GPU, Dedicated Endpoint, model training, NVIDIA NIM, or GPU profiler was used in the submitted live check.

## What worked in the observed workflow

### Model discovery reduced setup ambiguity

Reading the account-scoped model list confirmed that the exact configured Super ID was visible to the saved Token Factory key. The application then verified inference separately. This distinction matters: a model catalogue response alone does not establish that billing access or a particular tool-call request will succeed.

### Function calling supplied a useful boundary

Nemotron returned source code through a `submit_patch` tool call. This kept model output separate from execution: the backend validated the response, applied the pure-function domain policy, and ran its own tests. The final no-fault and crash/recovery cases each completed with one genuine model request and four passing Docker tests.

### Returned identity and usage supported an audit trail

The captured response model matched the requested Super ID. Usage fields allowed the project to persist reported prompt and completion tokens alongside the patch. In the final recovery case, the request count stayed at one and the recorded 626 input / 352 output tokens stayed unchanged after recovery.

All six requests across initial and final attempts had known usage in the saved reports. This observation should not be generalized to requests interrupted before their responses can be persisted; the application explicitly represents that case as unknown.

## A challenge and how it changed the implementation

The first candidate used `slices.append`. Its pagination logic could be reasonable, but method calls were outside the benchmark's existing execution domain. Validation rejected it; the model corrected the candidate after receiving feedback. Both initial tasks eventually passed, while the stricter same-final-patch and no-additional-inference recovery check correctly failed.

We made the generic execution contract explicit in the user task prompt, including the method-call restriction. The same two-case check then passed without changing the guard, weakening the tests, or supplying a reference solution. The [initial report](../examples/live-check-initial.json) and [final report](../examples/live-check.json) are both retained.

This is an observation from a small constrained task, not evidence of a general model weakness. It suggests that agent examples should make runtime execution policies as visible as task requirements.

## Suggestions for the onboarding and agent examples

1. **Keep credential and platform distinctions prominent.** A short path from “Token Factory key” to model discovery, tool-call example, and usage inspection helps a developer avoid confusing inference credentials with AI Cloud IAM setup.
2. **Show execution-policy constraints in a complete tool-use example.** An example that separates valid tool JSON, admissible candidate source, independent test failure, and transport error would help builders avoid treating every unsuccessful attempt as a provider retry.
3. **Make recovery accounting an explicit example.** Persisting known usage with the artifact, then recording unknown usage for an interrupted request, is more useful than presenting retry as if it were automatically free or exactly once.
4. **Surface model feature details next to the selected ID.** For this workflow, discoverable tool-choice support, reasoning/output-budget behavior, and usage-field semantics are useful before the first request. We used the basic model list and have not audited whether equivalent metadata is already available in other catalogue modes or product screens; this is a workflow suggestion rather than a claim that the platform lacks it.

## What we did not observe

The simulated HTTP 429 is an intentional pre-request fault profile in CrashLab. It is not a Nebius incident. We did not measure production throughput, tail latency, dollar-cost savings, model training quality, or GPU utilization. The final two-case verification supports the specific repair/recovery result only.

## Evidence

- [Verification record](VERIFICATION.md)
- [Final live check](../examples/live-check.json)
- [Preserved initial attempt](../examples/live-check-initial.json)
- [Architecture and accounting boundaries](ARCHITECTURE.md)
