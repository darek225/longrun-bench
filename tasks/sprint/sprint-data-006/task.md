# Traffic analysis

Analyze sessions.csv in the workspace. Rules: rows sharing a date and channel are a tracking double-fire and must be summed; rows with conversions above sessions are invalid and excluded. For the month {{month}}, write report.md with the total conversions, the overall conversion rate as a percent, the top {{top_n}} channels by conversions, and the data quality issues (duplicate rows, invalid rows, channel gaps).
