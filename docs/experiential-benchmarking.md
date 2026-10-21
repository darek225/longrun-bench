# Experiential Labs benchmarking protocol

Status: authorized by Darek on 2026-10-20, with conditions. This protocol
exists so gateway-run benchmarks are never mislabeled and Experiential
credits are never burned casually.

## Trigger conditions

Run Experiential benchmarks only after both are true:

1. The production LongRun Bench site is live.
2. Darek's real account exists on that site and the runs can be submitted
   under it with an account upload token.

Until then, no benchmark calls. A tiny connectivity smoke call is part of
the first run, not a separate loophole.

## Disclosure rules (non-negotiable)

Every published result must say, in the board fields themselves:

- the exact model ID requested from the gateway;
- the model ID returned by the gateway, if the response reports one;
- that the run went through the **Experiential Labs API/gateway**.

Board labeling convention:

- `agent_name`: `LongRun gateway runner`
- `model`: `<exact model id> (via Experiential Labs API)`
- `profile`: the real harness profile used (`standard` for the open
  harness). Never label a gateway run as a direct vendor API run.

If a report or social post summarizes the results, it repeats the model
ID and the Experiential Labs route. No exceptions for brevity.

## Credit discipline

Experiential credits are not cheap on some models. Default sequence:

1. **Smoke first.** One tiny non-benchmark chat completion to confirm the
   exact model ID responds through the gateway. Record token usage from
   the response. The connector cannot list models or check balances, so
   the smoke response is the availability evidence.
2. **One Sprint task next.** Run exactly one Sprint task for one cheap
   model. Extrapolate the full subset cost from actual usage before
   running anything else.
3. **Cheap Sprint subset only by default.** Prefer previously validated
   low-cost models (for example `deepseek-chat` or `gpt-4o-mini`) only if
   the smoke call proves the gateway serves that exact ID.
4. **Stop and ask before scale.** No Marathon or Ultra runs, no premium
   models, and no multi-model sweep without showing Darek the measured
   per-task cost and the projected total first.

Every run record keeps input/output token totals. Any cost figure shown
publicly is labeled actual (from gateway usage fields) or estimated
(from the harness pricing table), never blended silently.

## Credential handling

The Experiential key stays in the Muse connector vault. It is never
exported into a shell environment, a CLI argument, a transcript, or a
log. A future gateway runner must call the gateway through the
connector's dynamic-credential surrogate, restricted to
`api.experientiallabs.ai`, the same pattern as the Jev helper.
