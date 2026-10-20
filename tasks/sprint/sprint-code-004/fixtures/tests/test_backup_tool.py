from datetime import datetime

from backup_tool import manifest_name, plan_backup, verify_copy


def test_manifest_name_is_a_valid_filename():
    name = manifest_name(datetime(2026, 1, 2, 3, 4, 5))
    assert " " not in name and ":" not in name
    assert name.endswith(".json")


def test_plan_backup_skips_excluded():
    assert plan_backup(["a.txt", "b.tmp", "c.log"], ["b.tmp"]) == ["a.txt", "c.log"]


def test_verify_copy_detects_mismatch():
    assert verify_copy("abc", "xyz") is False
    assert verify_copy("abc", "abc") is True
