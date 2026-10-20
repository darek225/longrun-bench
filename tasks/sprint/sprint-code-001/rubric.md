# Rubric — sprint-code-001

### Correctness (40)
- 40: Full test suite passes; first-seen order preserved on every case.
- 25: Suite passes except one edge case.
- 10: Some tests pass; ordering still wrong.
- 0: Suite failing or the function was removed/stubbed.

### Completeness (25)
- 25: Suite green and `summary.md` explains both the bug and the fix.
- 15: Fix works but summary is thin.
- 0: No summary.

### Efficiency (15)
- Computed by the harness formula (steps, tokens, wall clock vs budget), capped by correctness.

### Error recovery (10)
- 10: Reads the failing tests, diagnoses the root cause (set ordering), verifies the fix by re-running the suite.
- 5: Gets there by trial and error.
- 0: Gives up at the first failure.

### Instruction adherence (10)
- 10: Only `dedupe.py` changed; tests untouched; `summary.md` delivered.
- 5: Minor deviations.
- 0: Tests modified to make the suite pass.
