#!/usr/bin/env python3
"""Pricing freshness (docs/plan/15 §7, §9.5): warn when harness/pricing.json
is more than one quarter old. Stale pricing warns; it never fails the build
(unparseable pricing does).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUARTER = timedelta(days=92)


def main() -> int:
    path = REPO / "harness" / "pricing.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        updated = date.fromisoformat(str(data["updated"]))
    except Exception as exc:
        print(f"pricing freshness: cannot parse {path}: {exc}")
        return 1
    age = date.today() - updated
    if age > QUARTER:
        print(f"::warning::harness/pricing.json is stale: updated {updated} ({age.days} days ago, over one quarter). Refresh provider prices.")
    else:
        print(f"pricing fresh: updated {updated} ({age.days} days ago)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
