# 01 — Standard Harness: Build Plan

## Decisions

- **Base image:** `python:3.12-slim`. Small, reproducible, every tool we need runs on it.
- **Language:** Python for the harness server and tools. The judge is a separate service (see `03-judge.md`).
- **Tool protocol:** tools are HTTP endpoints on localhost inside the container, called by the agent driver. The driver is model-specific glue (thin); the harness is model-agnostic.
- **Transcript format:** JSONL, one line per event: `{"t": "2026-10-19T20:00:00Z", "type": "tool_call", "tool": "shell.exec", "args": {...}, "result": {...}, "step": 12}`. Types: `run_start`, `prompt`, `thinking` (optional, redacted by default), `tool_call`, `deliverable`, `run_end`, `budget_exceeded`.
- **What counts as thinking:** anything the model emits that is not a tool call. Not counted as steps, optionally logged redacted (first 200 chars) for debugging, never shown to the judge.

## 1. Docker image

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git sqlite3 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy pandas requests beautifulsoup4 markdownify
COPY src/ /harness/
WORKDIR /workspace
EXPOSE 8000
CMD ["python", "-m", "harness.server"]
```

- Image tagged `longrun/harness:<semver>`, hash pinned in every run record.
- Rebuilt from scratch per run. The agent workspace is a fresh volume. Ultra memory file is mounted from task-scoped storage, wiped after the task's runs complete.

## 2. Tool implementations

### shell.exec
- `{"command": str, "timeout": int = 120}` → `{"exit_code", "stdout", "stderr", "timed_out"}`.
- Runs as non-root user `agent`. No sudo. Killed at timeout; partial output returned with `timed_out: true`.
- Denied commands: nothing at the shell level (the container is the sandbox). The network policy is the boundary.

### file.read / file.write / file.edit
- Paths restricted to `/workspace`. `..` traversal rejected.
- `file.edit`: exact-match replacement, fails if `old_text` not found or found more than once. (Prevents sloppy edits from passing silently.)
- Max file size 10 MB; larger reads are paged.

### python.exec
- `{"code": str, "timeout": 120}` → `{"stdout", "stderr", "exception"}`.
- Runs in-process with a restricted builtins subset? **Decision: no.** Restriction is theater inside a container; the container is the sandbox. Full Python, numpy, pandas, requests available.

### http.fetch
- `{"url": str, "max_chars": 50000}` → `{"status", "text_markdown", "final_url"}`.
- URL must match the task's allowlist (see §4). Redirects re-checked against the allowlist at each hop. Non-allowlisted → error, still counts as a step.
- HTML converted to markdown; scripts stripped. This is deliberate: the agent gets content, not code.

### browser.task
- `{"goal": str, "max_steps": 15}` → `{"observations": [...], "extracted": {...}}`.
- Text-mode browser (headless Chromium + readability extraction). One harness-level call = one agent step, but internally capped at 15 page loads to bound cost.
- JavaScript-heavy pages: the browser waits up to 10s for network idle, then extracts. No CAPTCHA solving; if blocked, the observation says so and the agent must route around it (this is graded under error recovery).

### code.nav
- Semantic code navigation, backed by a language server (Serena-style, via LSP). Operations:
  - `{"op": "find_definition", "symbol": str, "file": str}` → definition locations.
  - `{"op": "find_references", "symbol": str, "file": str}` → all reference sites.
  - `{"op": "list_symbols", "file": str}` → symbols defined in a file (functions, classes, methods).
  - `{"op": "search_symbols", "query": str}` → symbols matching a name across the workspace.
- One call = one step, same as every tool.
- **Why it's in the standard harness:** the `standard` profile models a well-equipped agent, and every real coding agent navigates code semantically rather than by grep. Excluding it would measure "model + grep," which understates what deployed agents do. The `bare` profile exists to isolate the raw model.
- Language support: Python at launch (the task bank is Python-first). Adding a language = adding its language server to the image; each addition is a MINOR harness version.

## 3. Budgets and termination

- The server tracks steps and wall-clock. At budget, in-flight tool call is killed, `budget_exceeded` is logged, the run ends.
- The agent may end the run early by emitting a `deliverable` event with the final artifact. The deliverable is what gets graded.
- No deliverable at termination → correctness and completeness score 0, other criteria graded on the transcript.

## 4. Network policy

- Default deny. Per-task allowlist in the manifest, e.g. `["docs.python.org", "stackoverflow.com"]`.
- Enforced by an egress proxy inside the container (tiny Python proxy on localhost:8888; `http_proxy`/`https_proxy` set). DNS resolves only allowlisted hosts; everything else NXDOMAIN.
- The agent is told the allowlist in the system prompt. Trying non-allowlisted hosts wastes steps (graded under efficiency).

## 5. The harness protocol (for `native` / `bare` vendors)

```
POST /run
  { "task_instance": {...}, "budgets": {"steps": 100, "wall_clock_minutes": 180} }
  -> { "run_id": "uuid" }

GET /run/{id}/status -> { "state": "running|done|failed", "steps_used": n }

GET /run/{id}/transcript -> { "events": [...] }   # JSONL format per §0

POST /run/{id}/deliver  (optional early stop)
  { "deliverable": {...} }
```

- The bench org fetches the transcript and runs deterministic checks itself. Vendor-reported scores are ignored.
- `bare` profile: the vendor's `/run` accepts the task and returns a single response as the deliverable with zero tool calls. Same transcript format, one step.

## 6. What the agent is told (system prompt template)

The harness injects a fixed system prompt per run:

```
You are being evaluated on a long multi-step task. Rules:
- You have {steps} tool calls and {minutes} minutes. One tool call = one step.
- Your deliverable is graded against a rubric: correctness (40), completeness (25),
  efficiency (15), error recovery (10), instruction adherence (10).
- Network access is limited to: {allowlist}. Other hosts will fail.
- When finished, emit your deliverable. Partial work is graded; do not stall.
- Do not attempt to access the grading system, the rubric weights, or the task manifest.
```

The exact prompt text is versioned with the harness. Prompt changes are MINOR harness versions.

## 7. Testing the harness

- `harness/tests/`: unit tests for every tool, the budget enforcer, the network policy (allowlist hit/miss), and the protocol server.
- A reference "do-nothing agent" and a "random agent" must complete a full run without crashing the harness. If the harness cannot survive a stupid agent, it is not ready.
- Golden transcripts: 3 recorded runs replayed through the checker on every harness release.
