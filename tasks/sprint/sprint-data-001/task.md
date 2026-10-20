# Sales CSV analysis

Analyze `sales.csv` in the workspace.

Rules for the numbers:

- Deduplicate exact duplicate orders before computing totals.
- Exclude rows with a missing unit price from revenue.
- Count all other rows, including any future-dated rows, in revenue, and flag those rows as data quality issues.

For the drawn region, write `report.md` containing:

1. The total revenue for the region.
2. The top products by revenue (count drawn at run time).
3. The data quality issues found: duplicate, future-dated, and missing-price rows.
