# LongRun Bench harness

The standard harness (SPEC.md §5), dependency-light:

- render parameterized task instances from `manifest.json`
- run a scripted/model adapter through the driver loop (BYO key via env;
  OpenAI-compatible, Anthropic, and Google adapters in `adapters.py`)
- execute the standard workspace tools with step counting
- write JSONL transcripts in the spec schema shape
- replay deterministic checks and compute scores (checks-only, or graded
  with the LLM judge via `longrun grade`)
- serve the harness protocol for native/bare submissions (`server.py`)
- Ultra session mode: `--session-steps` pauses a run at a session
  boundary, `--resume` continues it from its `session.json` snapshot with
  cumulative budgets, and `longrun abandon` closes a run as abandoned
  (docs/runbooks/ultra-ops.md)

## Quickstart

```bash
cd harness
python -m pytest
python -m longrun.cli validate-task ../tasks/sprint/sprint-data-001
python -m longrun.cli render ../tasks/sprint/sprint-data-001 --seed 42
```

Run the scripted smoke agent:

```bash
python -m longrun.cli run-scripted ../tasks/sprint/sprint-code-001 \
  --seed 7 \
  --script ../tasks/sprint/sprint-code-001/smoke-script.json \
  --out /tmp/longrun-smoke
```

Outputs land in the `--out` directory: `transcript.jsonl`, `score.json`, `run.json`, `submission.json`, and the run `workspace/`.
