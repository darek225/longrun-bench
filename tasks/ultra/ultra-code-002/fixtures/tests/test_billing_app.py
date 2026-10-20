from billing_app import init_db, invoice_total, monthly_usage, record_event


def _setup(tmp_path):
    return init_db(str(tmp_path / "billing.db"))


def test_usage_sums_units(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 40)
    record_event(conn, "acme", "2026-10", 2)
    record_event(conn, "acme", "2026-11", 5)
    assert monthly_usage(conn, "acme", "2026-10") == 42


def test_free_tier_costs_nothing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 1000)
    assert invoice_total(conn, "acme", "2026-10") == 0.0


def test_tier1_pricing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 1500)
    assert invoice_total(conn, "acme", "2026-10") == 5.0


def test_tier2_pricing(tmp_path):
    conn = _setup(tmp_path)
    record_event(conn, "acme", "2026-10", 11000)
    # 9000 events at 0.01 + 1000 events at 0.008 = 90 + 8 = 98
    assert invoice_total(conn, "acme", "2026-10") == 98.0
