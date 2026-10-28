# Contributing

Agent CrashLab is a small coding-agent reliability experiment, with an explicit
separation between offline fixtures and live inference.

## Develop and verify

Use Python 3.11+ on macOS or Linux. No third-party runtime packages or frontend
build are required.

```bash
python3 -m unittest discover -s tests -v
python3 -m crashlab --data /tmp/crashlab-contribution check \
  --output /tmp/crashlab-contribution/report.json
```

These commands use trusted offline fixtures and never need model credentials.
Use a fresh temporary data directory so an existing dashboard does not own its
control-plane lease. Run Docker or live-model checks only when a change affects
those boundaries and you have explicitly selected that integration check.

## Useful changes

- Add a repair task with precise requirements, a buggy starter and independent
  acceptance tests. Show that the starter fails and a trusted solution passes.
- Add a reproducible failure case with an observable trigger and outcome.
- Improve recovery without dropping earlier events or cumulative usage.
- Document a limitation with a minimal failing case and the exact mode used.

Keep acceptance tests outside the agent's editable source. Never weaken a check
just to make a model output pass. Preserve failed experiments when they explain
a claimed improvement; separate prompt tuning from held-out evaluation.

## Pull requests

Explain the user-visible problem, the behavior after the change and the relevant
verification. Include model/task/fault settings for experimental results, with
known and unknown usage stated separately. Do not claim statistical improvements
from a single run.

Never commit `.env`, credentials, runtime databases, personal paths or provider
request headers. Use the source-packaging helper before sharing a release. For
execution-boundary issues, follow [SECURITY.md](SECURITY.md).
