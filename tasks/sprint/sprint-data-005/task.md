# Inventory shrinkage

Analyze counts.csv in the workspace. Shrinkage is expected minus counted when positive, valued at unit_cost. Overages (counted above expected) are flagged, never netted. Rows with a missing count are excluded. For warehouse {{warehouse}}, write report.md with the total shrinkage value, the top {{top_n}} SKUs by shrinkage value, and the data quality issues (overage, missing count).
