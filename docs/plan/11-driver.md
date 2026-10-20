# 11 — The Driver: Agent Loop Specification

## Decisions

- **The driver is part of the harness, not the agent.** It is the same code for every model. The only model-specific piece is the provider adapter (§10.3).
- **Tool calls use the provider's native function-calling format**, normalized by the adapter into a canonical form. The driver never parses free text for tool calls.
- **Completion is explicit.** The toolset includes a `deliver` tool. The run ends when the agent calls it, when budgets exhaust, or when the model refuses/errors 3 times in a row.
- **Malformed tool calls cost a step.** The driver returns the schema error as the tool result and continues. This is graded under instruction adherence.
- **History compaction is deterministic.** Full history until 80% of the model's context window, then the driver summarizes tool results older than 20 steps (keeping the task prompt and the last 20 steps verbatim). The summarizer is the same model at low effort; the summary is logged in the transcript.

## 1. The loop (pseudocode)

```
def run(task_instance, budgets, adapter, system_prompt):
    history = [system_prompt, task_prompt]
    steps = 0
    start = now()

    while True:
        if steps >= budgets.steps or now() - start >= budgets.wall_clock:
            return end("budget_exceeded")

        response = adapter.complete(history, tools=TOOLSET)
        # response: { text, tool_calls: [{name, args}] } or { text, tool_calls: [] }

        if response.error:
            consecutive_errors += 1
            log("model_error", response.error)
            if consecutive_errors >= 3:
                return end("model_failed")
            history.append(error_nudge(response.error))
            continue
        consecutive_errors = 0

        if not response.tool_calls:
            # Model talked without acting. Nudge once per 3 consecutive text-only turns.
            text_only_streak += 1
            if text_only_streak >= 3:
                history.append("You have not called a tool in 3 turns. Call a tool or call deliver.")
            else:
                history.append(response.text)  # kept for context, not a step
            continue
        text_only_streak = 0

        for call in response.tool_calls:
            steps += 1
            if call.name == "deliver":
                return end("deliverable", deliverable=call.args)

            validation = validate_against_schema(call)
            if not validation.ok:
                result = {"error": f"invalid tool call: {validation.message}",
                          "hint": "Check the argument names and types, then retry."}
            else:
                result = harness.execute(call.name, call.args)  # may time out

            log("tool_call", step=steps, tool=call.name,
                args_hash=sha256(call.args), result_summary=summarize(result))
            history.append(tool_result_message(call, result))

            if steps >= budgets.steps:
                return end("budget_exceeded")

        history = maybe_compact(history, adapter.context_window)
```

## 2. The `deliver` tool

```json
{
  "name": "deliver",
  "description": "End the run and submit your final deliverable. Call this when the task is complete, or when you have done all you can.",
  "parameters": {
    "type": "object",
    "properties": {
      "summary": {"type": "string", "description": "One-paragraph summary of what was accomplished."},
      "artifact_uri": {"type": "string", "description": "Path in /workspace to the main deliverable file."},
      "notes": {"type": "string", "description": "Anything the grader should know (assumptions, gaps)."}
    },
    "required": ["summary", "artifact_uri"]
  }
}
```

- The deliverable file must exist in `/workspace`. If not, the driver returns an error (counts as a step) and continues.
- The `notes` field is where honest agents disclose gaps. The judge is instructed to reward disclosed gaps over hidden ones (instruction adherence).

## 3. Malformed input handling

| Situation | Driver behavior | Step cost |
|---|---|---|
| Tool call with wrong arg names | Return schema error as tool result | 1 step |
| Tool call with wrong arg types | Return schema error as tool result | 1 step |
| Unknown tool name | Return "unknown tool" error | 1 step |
| Model outputs text, no tool call | Nudge after 3rd consecutive | 0 steps |
| Model refuses the task | End run, grade what's there | 0 |
| Provider API error (500, timeout) | Backoff and retry, max 3 | 0 |
| Provider rate limit (429) | Exponential backoff up to 5 min or budget end | 0 |

## 4. History compaction (exact)

- Trigger: estimated tokens in history > 80% of the adapter's reported context window.
- Keep verbatim: the system prompt, the task prompt, and the last 20 steps (tool calls + results).
- Summarize: everything between, via the model with: "Summarize the following tool-call history in 500 words, preserving: what was tried, what failed and why, what was learned, current state. Omit nothing material."
- The summary replaces the compacted region, prefixed with `[COMPACTED SUMMARY - steps 21..N]`.
- Compaction events are logged in the transcript. The judge sees the summary, not the original.

## 5. What the driver logs (transcript events)

Every event from `09-remaining-details.md` §1, plus:
- `model_error`: provider failures.
- `compaction`: when history was summarized (with step range).
- `nudge`: text-only streak nudges.
- `budget_warning`: at 80% of step budget ("you have N steps left").

## 6. Testing the driver

- **Conformance suite:** a mock adapter that emits scripted sequences (valid calls, malformed calls, refusals, text-only streaks, deliver). The driver must handle all without crashing and produce the correct transcript.
- **The "adversarial model" test:** a mock that always emits invalid tool calls. The driver must burn through the step budget cleanly and end with `budget_exceeded`, never hang.
- **The "silent model" test:** a mock that returns empty responses. Three strikes → `model_failed`.
