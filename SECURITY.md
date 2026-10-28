# Security boundaries

Agent CrashLab is a single-operator hackathon tool. It is not a general hostile
code-execution service or a hardened multi-tenant sandbox.

## Supported execution model

- The default control plane listens on loopback and rejects cross-origin
  mutations. Do not expose this local server directly to untrusted visitors.
- The task catalogue is fixed. There is no arbitrary repository import, user
  shell command or writable acceptance-test endpoint.
- Live model output is checked against a restricted pure-function AST policy
  and executed inside resource-limited Docker containers with networking disabled,
  read-only mounts, a nonroot user and no host credential mounts.
- Fixture mode accepts only exact trusted built-in source. It must never become
  a fallback for arbitrary generated code.
- Only worker processes and test containers owned by a run may be interrupted
  or cleaned up. Container-side deadlines remain active if the host worker exits.

These controls reduce risk in the stated environment. They do not guarantee
isolation against every interpreter, container, host-kernel or supply-chain issue.
Keep Docker and the host current, and use a dedicated host for an externally
accessible judging instance.

## Credentials and model spending

Keep the Token Factory key in local ignored `.env` or the deployment provider's
secret store. Never put it in browser code, public reports, screenshots, command
arguments or Git history. The source archive helper excludes runtime/credential
paths and can scan configured secret values; it does not replace a review of
what is published.

Public deployments must have their own access and spending controls. A shared
demo must not provide unlimited anonymous paid inference. Missing usage after a
request interruption is unknown, not zero; checkpointing does not make external
model requests universally exactly once.

## Reporting a vulnerability

Use the repository's private vulnerability reporting feature if enabled. If that
channel is unavailable, open an issue requesting a private contact without
including exploit details, credentials or private data. Do not submit a real key
as a reproduction. Describe the affected version, execution mode and trust
boundary, and use harmless test inputs wherever possible.
