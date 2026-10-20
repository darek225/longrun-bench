# Q2 sales analysis

Analyze sales_q2.csv in the workspace. Rules: deduplicate by order_id keeping the first occurrence; EUR rows convert at 1.08 USD; rows dated after 2026-06-30 are excluded from revenue; rows with a missing unit price are excluded. For the the drawn region region, write report.md with the total revenue, the top the drawn N products by revenue, and the data quality issues (duplicate, EUR, future-dated, and missing-price rows).
