# Support ticket analysis

Analyze tickets.csv in the workspace. Rules: tickets with a negative resolved_h are data errors and are excluded from hour totals but still counted in total tickets; a missing category is bucketed as unknown. For the {{queue}} queue, write report.md with the total tickets, the top {{top_n}} categories by total resolution hours, and the data quality issues (negative times, missing categories).
