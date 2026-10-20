# Spec: report scheduler

`next_run(schedule, after)` where schedule is a dict: kind 'daily' or 'weekly', hour (default 9), minute (default 0), utc_offset in hours (default 0), and weekday (0=Monday) for weekly. Return the next timezone-aware datetime strictly after `after`, in the schedule's offset zone. `backoff(attempt)` returns seconds: 60 * 2**attempt capped at 3600.
