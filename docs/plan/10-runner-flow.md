# 10 — The Runner Flow: BYO Key to Scoreboard

## Decisions

- **The runner's API key never leaves the runner's machine.** Not in the transcript, not in the upload, not in logs. This is a security invariant, not a preference.
- **Provider support is adapter-based.** Each model provider is a ~50-line driver adapter. Launch with: OpenAI-compatible (covers OpenAI, DeepSeek, xAI, Together, Fireworks, and any OpenAI-style endpoint), Anthropic, Google AI, Meta Model API.
- **Cost is shown before and after.** The harness prints estimated cost before the run (from the provider's public pricing and the task's budget) and actual cost after (from token counts). No surprises.

## 1. End to end, step by step

```
# 1. Install (one command)
docker pull longrun/harness:1.0.0

# 2. Run a task with your own key (key stays local, passed as env var)
docker run --rm \
  -e LONGRUN_MODEL="anthropic/claude-opus-5.5" \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -v ./my-results:/results \
  longrun/harness:1.0.0 \
  run --task marathon/m-01 --seed 42 --out /results

# 3. What happens inside the container:
#    - task instance rendered with seed 42
#    - driver calls YOUR model API with YOUR key, directly from the container
#    - every tool call logged to a signed transcript (key material redacted)
#    - deterministic checks run locally; you see your checks-only score immediately
#    - transcript + score claim signed with the harness key, written to /results

# 4. Upload (the key is not in the upload; it never was in the transcript)
longrun upload --dir ./my-results
# -> server replays the checks from your transcript, recomputes the score,
#    posts it to the board as `checks` tier (or `graded` if you paid judge compute)

# 5. Your score is on the board. Anyone can reproduce your seed.
```

## 2. Key handling (exact rules)

1. Keys enter via environment variables only. No flags, no config files, no prompts that echo.
2. The harness redacts key-shaped strings from transcripts automatically (`sk-`, `xai-`, `AIza`, bearer tokens, `-----BEGIN` blocks) before signing. Redaction is declared in the submission manifest.
3. The upload payload contains: transcript hashes, score claim, task set version, harness hash, seed, redaction manifest. It does not contain the key, the full tool args (hashes only), or anything that could reconstruct the key.
4. If a key leaks into a transcript despite redaction, the submitter can revoke the submission (signed revocation) and rotate their key. The board marks the score `revoked`, never deletes the row.

## 3. Provider adapters

Each adapter implements:

```python
class ProviderAdapter:
    name: str                      # "anthropic", "openai_compat", ...
    def complete(self, messages, tools, **kw) -> Response: ...
    def count_tokens(self, messages) -> int: ...
    def price_per_mtok(self) -> (float, float): ...  # (input, output), from public pricing
```

- `openai_compat` takes a `--base-url` so any OpenAI-style endpoint works (local models via llama.cpp/vLLM included — this is the "people running stuff locally" lane from the original brief).
- Local models: the runner points the adapter at `http://localhost:8080/v1`. Same flow, same board, flagged `local` in the hardware field.
- Adding a provider is a PR with the adapter + a test run against the calibration task. No maintainer approval needed beyond code review.

## 4. What the runner sees

Before the run:
```
Task: marathon/m-01 (competitive teardown)   Level: Marathon
Budgets: 100 steps, 180 min                   Est. cost: $1.20-3.40 (claude-opus-5.5)
Your key: ANTHROPIC_API_KEY (from env, never transmitted)
```

After the run:
```
Done in 64 steps, 91 min.
Checks: 4/5 passed. Checks-only score: 71/100 (correctness+completeness portion).
Full transcript: /results/m-01-seed42.jsonl (signed)
Upload with: longrun upload --dir ./my-results
```

## 5. Failure modes

- **Key invalid:** the run fails before step 1, clear error, no partial transcript submitted.
- **Rate limited mid-run:** the driver backs off (exponential, max 5 min). If the budget expires during backoff, the run ends and partial work is graded.
- **Provider outage:** run marked `abandoned (provider)`, not scored, resubmittable with the same seed at no penalty.
