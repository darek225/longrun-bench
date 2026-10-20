# LongRun Bench harness

Phase 2 starts with a local, dependency-light vertical slice of the standard harness:

- render parameterized task instances from `manifest.json`
- run a scripted/model adapter through the driver loop
- execute the standard workspace tools with step counting
- write JSONL transcripts in the Phase 1 schema shape
- replay deterministic checks and compute a checks-only provisional score

This is not the full Phase 2 definition of done yet. The Docker image, hosted protocol server, LLM judge, leaderboard, and full 85-task bank remain later Phase 2 slices.

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

Outputs land in the `--out` directory: `transcript.jsonl`, `score.json`, `run.json`, and the run `workspace/`.
