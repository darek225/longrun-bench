# Invoice summary

Analyze invoices.csv in the workspace. Rules: deduplicate by invoice_id keeping the first row; negative amounts are credit notes and count as negative revenue; rows with a missing tax_rate are excluded from the tax total only. For the {{segment}} segment, write report.md with the total revenue billed, the total tax, the top {{top_n}} clients by billed amount, and the data quality issues (duplicate, credit, missing tax).
