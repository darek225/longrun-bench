# 13 — Harness Hardening: Resource Limits and Security

## Decisions

- **The threat model is a malicious or compromised agent.** The harness runs arbitrary model-generated code. Every limit below assumes the agent is trying to break out, spam the network, or fork-bomb the host.
- **Defense in depth:** container limits + seccomp + network proxy + no privileges. No single layer is trusted alone.
- **A run that attacks the harness is valid data.** The transcript records it, the run is scored (likely 0), and the attack is logged for the security record. We do not silently discard hostile runs; they are the most informative ones.

## 1. Container limits (enforced by the runtime, not by convention)

| Resource | Limit | Enforcement |
|---|---|---|
| CPU | 2 cores | cgroup cpu quota |
| Memory | 4 GB | cgroup, OOM kills the container (run marked `oom`) |
| Disk | 10 GB on /workspace | quota; writes beyond fail cleanly |
| Processes | 256 pids | pids cgroup (fork bomb dies at 256) |
| Wall clock | task budget | harness server kills the container |
| Network | egress proxy allowlist only | proxy + no direct route (see §3) |

- OOM is a run outcome, not a harness failure: transcript records `oom`, rubric grades what's there. (Agents that leak memory are telling you something.)
- These limits are in the manifest and visible to the agent. An agent that plans around 4GB scores better than one that doesn't.

## 2. Container security

- Run as UID 1000 (`agent`), never root. `USER agent` in the Dockerfile; the entrypoint refuses to start as root.
- Drop all Linux capabilities (`--cap-drop=ALL`). No `--privileged`, ever.
- Seccomp: default Docker profile plus blocked `mount`, `ptrace`, `reboot`, `swapon`.
- Read-only root filesystem except `/workspace` and `/tmp` (mounted read-write, noexec on `/tmp`).
- No Docker socket mounted. No host filesystem mounted. The container cannot see the host.
- Image rebuilt from the pinned Dockerfile per task-set version; the hash is the identity. A runner with a modified image produces transcripts the server rejects (hash mismatch).

## 3. Network containment

- The container has no default route. The only egress is the in-container HTTP proxy on `localhost:8888`, configured via `http_proxy`/`https_proxy`.
- The proxy checks every request against the task allowlist (exact host match, no subdomains unless listed). Non-matching hosts get a proxy 403; the tool returns an error to the agent (counts as a step — the agent was told the allowlist).
- DNS inside the container resolves via the proxy only. Direct DNS queries go nowhere.
- The `url_alive` check (§12) is the sole exception: it runs server-side during grading, not in the agent container.

## 4. What gets logged as security events

- Repeated allowlist violations (>10 in a run): flagged `network_probing` in the transcript. Not punished in scoring (curiosity is fine), but visible to auditors.
- Attempts to read `/proc/1/`, the Docker socket path, or cloud metadata IPs (`169.254.169.254`): flagged `escape_attempt`. The run continues (the attempt will fail), the flag is public.
- Cryptominer signatures in process list (practical paranoia): the run is killed, the submitter's account is frozen pending review. This is the one case where the bench org acts unilaterally, and the action is logged publicly.

## 5. Supply chain

- Base image pinned by digest, not tag (`python:3.12-slim@sha256:...`).
- pip packages pinned with hashes (`pip install --require-hashes`).
- The harness repo's release process: tagged release → CI builds image → image hash published → task set version pins the hash. A task set version without a pinned harness hash is invalid and the ingestion API rejects it.
