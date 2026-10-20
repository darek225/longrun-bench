# Rubric — sprint-vendor-001

### Correctness (40)
- 40: Every deterministic check passes. Vendor names and prices match `vendors.json` exactly; no invented vendors.
- 25: All vendors named but one price wrong or missing.
- 10: A vendor invented or most prices wrong.
- 0: Deliverable missing or unrelated to the source data.

### Completeness (25)
- 25: Every vendor has name, price, and features; recommendation paragraph names a vendor with reasoning.
- 15: Vendors complete but recommendation missing or perfunctory.
- 0: Most required elements missing.

### Efficiency (15)
- Computed by the harness formula (steps, tokens, wall clock vs budget), capped by correctness.

### Error recovery (10)
- 10: Source-data quirks noticed and handled; brief stays internally consistent.
- 5: Minor inconsistencies.
- 0: Contradictions copied blindly or run abandoned.

### Instruction adherence (10)
- 10: Requested format followed exactly; `brief.md` delivered.
- 5: Minor format deviations.
- 0: Format ignored.
