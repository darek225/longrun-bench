from datetime import datetime, timezone

from scheduler import backoff, next_run


def test_daily_later_today():
    after = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    nxt = next_run({"kind": "daily", "hour": 9}, after)
    assert nxt == datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


def test_daily_rolls_to_tomorrow():
    after = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    nxt = next_run({"kind": "daily", "hour": 9}, after)
    assert nxt == datetime(2026, 1, 6, 9, 0, tzinfo=timezone.utc)


def test_weekly_same_week():
    after = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)  # Monday
    nxt = next_run({"kind": "weekly", "weekday": 2, "hour": 9}, after)  # Wednesday
    assert nxt == datetime(2026, 1, 7, 9, 0, tzinfo=timezone.utc)


def test_weekly_rolls_a_week():
    after = datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc)  # Wednesday, past 9am
    nxt = next_run({"kind": "weekly", "weekday": 2, "hour": 9}, after)
    assert nxt == datetime(2026, 1, 14, 9, 0, tzinfo=timezone.utc)


def test_utc_offset_schedule():
    after = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)  # 08:00 at UTC-5
    nxt = next_run({"kind": "daily", "hour": 9, "utc_offset": -5}, after)
    assert nxt == datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)


def test_backoff_grows_and_caps():
    assert backoff(0) == 60
    assert backoff(1) == 120
    assert backoff(20) == 3600
