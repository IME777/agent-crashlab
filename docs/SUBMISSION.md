# Hackathon submission plan

Planning baseline: October 27, 2026. Submission deadline: **October 30, 2026, 10:00 a.m. PDT**, America/Los_Angeles. This checklist records work still requiring evidence; it does not imply the project has been submitted.

## Product statement

Agent CrashLab helps developers check whether a coding agent can still deliver a correct patch after a worker interruption. A real NVIDIA model on Nebius repairs a small codebase; the tool injects a failure, resumes or restarts the task, runs independent tests, and exports a traceable result.

Intended track: **Coding and Agentic Engineering**.

## Submission requirements

The official rules require an eligible NVIDIA open-model project on Nebius, a public repository with a license and setup instructions, a working demo/test build, English materials (or English translations), and a public YouTube demonstration under three minutes. Keep judge access available through December 15, 2026. See the [official rules](https://nebiusglobalaihackathon.devpost.com/rules) and [event overview](https://nebiusglobalaihackathon.devpost.com/).

Calling an NVIDIA model through Nebius Token Factory satisfies the platform requirement; the remaining application does not have to be hosted on AI Cloud. An offline fixture or another inference provider alone does not satisfy that requirement. See the [official FAQ](https://nebiusglobalaihackathon.devpost.com/details/faqs).

## Evidence and links

Fill this section only with verified outcomes. Never replace a missing live-model result with fixture output.

| Item | Verified link or evidence | State |
| --- | --- | --- |
| Public source repository and open-source license | https://github.com/IME777/agent-crashlab | Public target verified; original MIT license retained; candidate tag `v0.1.0-rc.1` |
| Recorded evidence and runnable source build | [Public result viewer](https://agent-crashlab-evidence-jm.emiandtuzi.chatgpt.site) | Deployed; anonymous access verified; recorded replay, not a newly executing hosted worker |
| Full hosted live runtime | [Prepared Linux VM deployment](../deploy/README.md) | No host provisioned; owner requested configuration and cost proposal first |
| English setup/testing instructions | [README](../README.md), [judge guide](JUDGE-GUIDE.md), [architecture](ARCHITECTURE.md) | Written; extracted source demo verified |
| Real Nebius/NVIDIA run, with model ID | [Final live report](../examples/live-check.json) | Verified: Nemotron Super, two final cases, one request each |
| Worker interruption/recovery report | [Live recovery](../examples/live-check.json), [initial attempt](../examples/live-check-initial.json), [Docker cleanup](../examples/docker-check.json) | Real exit 86, same saved patch and no added inference in the final resume; initial extra repair retained |
| Comparable resume/restart run reports | [18/18 offline smoke matrix](../examples/offline-check.json) | Fixture verified; no live model-quality claim |
| Local HTTP/API checks | [14 HTTP smoke checks](../examples/http-check.json) | Passed locally; includes report download and actual crash/resume |
| Public YouTube video, under 3 minutes | Pending | Not verified |
| Nebius/NVIDIA tooling feedback | [Observed tooling feedback](TOOLING-FEEDBACK.md) | Drafted from actual observations |
| Fixed submission source version | Pending | Not verified |
| Access and operating plan through December 15 | Pending | Not verified |

Current release-candidate milestone: 80 offline tests and the 18/18 fixture smoke matrix pass. Real Nebius model-generated patches passed four Docker tests in each final case. Worker exit 86 and saved-patch recovery were observed with no additional inference; all attempts total six real requests and 5,303 reported tokens. The public result viewer provides anonymous evidence inspection and a runnable source download. A fresh extracted archive passed the two-case offline demo. The full remote worker, target GitHub publication and public video remain pending.

The [verification index](VERIFICATION.md) links all local evidence, including 14 passing HTTP checks. Git is initialized locally on `main`; no commit, remote, or public source publication has been made. A local license file does not yet satisfy the public repository submission requirement.

## Three-minute demonstration script

The finished [English narration and shot list](DEMO-SCRIPT.md) targets 2:45 (295 spoken words), leaving room below three minutes. Use actual run data. If waiting is shortened, label the edit.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:20 | The task and its failing test | “A coding agent can succeed once and still fail to finish when its worker stops. CrashLab makes that failure reproducible.” |
| 0:20–0:55 | Live provider/model label, generated patch and current phase | “Nemotron on Nebius is generating the repair. Independent tests, outside the agent's edit scope, determine whether it works.” |
| 0:55–1:35 | Injected worker exit; saved checkpoint; resume | “This is a real worker process interruption after the patch is saved. The recovery policy reuses committed work and continues verification.” |
| 1:35–2:10 | Test output and labelled configuration comparison | “Here are the outcomes, repeated steps, and known token usage for these configurations. This is a limited task set, not a production reliability claim.” |
| 2:10–2:45 | Downloaded report, reproduction instructions and limitations | “Developers can rerun this check before releasing an agent. The report preserves the fault, result and accounting limits.” |

If only one reliable live case is available, show that case accurately and describe the remaining coverage as work in progress. The bounded 18-configuration smoke matrix (three tasks, two policies, three faults) is verified in fixture mode only. A live-mode matrix needs its own real model results. One execution per configuration is not a statistical benchmark.

## Description content

- **Problem and audience:** developers validating a coding agent before release.
- **What works in this version:** list only verified provider, task, fault, recovery and reporting paths.
- **Technical implementation:** explain persistent state, owned worker processes, Docker acceptance tests and the Nebius model's actual role.
- **Original contribution:** reproducible fault boundaries, explicit acceptance checks and experiment reports built on known reliability techniques.
- **Results:** include measured cases and failures, sample size, configuration differences and unknown usage. No invented percentage improvements.
- **Limitations:** small tasks, single-operator environment, model nondeterminism, no universal exactly-once, no GPU-serving optimization claim.
- **What comes next:** broader tasks, framework baselines, more faults and a separate self-hosted inference experiment.

## Release and access checklist

- [ ] Record the final source revision; create a submission tag such as `hackathon-2026-10-30` when that revision is ready.
- [ ] Confirm that the license is visible and the README includes exact startup, model setup, Docker-image preparation and test steps.
- [ ] Run those instructions from a fresh local setup or record remaining environment assumptions.
- [ ] Confirm browser/API/report responses contain no model key, authorization headers or private local paths.
- [ ] Confirm offline fixture labels remain visible and are explained in the README.
- [ ] Confirm at least one submitted result is a real NVIDIA model call through Nebius.
- [ ] Provide working judge access without requiring judges to supply a private API key; describe any login/test instructions.
- [ ] Test the judge-facing link or build outside the development session.
- [ ] Budget and operate the judging instance through December 15; verify it has persistent storage and bounded model/test execution.
- [ ] Upload the final English video publicly to YouTube and check duration and viewing access.
- [ ] Include feedback on the Nebius and NVIDIA tools actually used.
- [ ] If relevant, disclose significant updates to work that existed before the submission period.
- [ ] Submit before 10:00 a.m. PDT; target 9:00 a.m. to leave a buffer.

After the deadline, preserve the submitted version and its evidence. Continue development in a separately identified version. The rules restrict changes to the submission after the period closes; future portfolio updates should not silently replace the judged artifact.

Current canonical access/mode and remaining publication steps are tracked in [PUBLISHING.md](PUBLISHING.md). Devpost copy is prepared in [DEVPOST.md](DEVPOST.md); do not replace pending repository/video/revision fields with invented links.
