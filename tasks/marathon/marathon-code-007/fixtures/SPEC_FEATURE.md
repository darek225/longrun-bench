# Spec: log summary tool

`summarize(lines)` returns a dict with total (non-blank lines), by_level (counts keyed by the first token of each line), and top_errors: the three most common ERROR messages (the text after the level) as (message, count) pairs from Counter.most_common. Blank lines are skipped entirely.
