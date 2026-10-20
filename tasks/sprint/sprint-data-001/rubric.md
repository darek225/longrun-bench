# Rubric — sprint-data-001

### Correctness (40)
- 40: Every deterministic check passes. Revenue matches ground truth for the drawn instance; top products are exactly right.
- 25: Top products right but revenue off, or revenue right with one product wrong.
- 10: Core figures present but multiple check failures.
- 0: Deliverable missing, fabricated, or figures unrelated to the dataset.

### Completeness (25)
- 25: Revenue, full top-N list, and all three data quality issues named.
- 15: One required element missing or the anomaly section is partial.
- 0: Most required elements missing.

### Efficiency (15)
- Computed by the harness formula (steps, tokens, wall clock vs budget), capped by correctness.

### Error recovery (10)
- 10: Notices and correctly handles the duplicate, missing-price, and future-dated rows instead of silently absorbing them.
- 5: Handles some planted data problems.
- 0: Numbers are wrong because planted data problems were ignored without mention.

### Instruction adherence (10)
- 10: Follows the dedupe and exclusion rules exactly; deliverable is `report.md` in the requested shape and length.
- 5: Minor deviations that do not change the numbers.
- 0: Ignores the stated rules.
