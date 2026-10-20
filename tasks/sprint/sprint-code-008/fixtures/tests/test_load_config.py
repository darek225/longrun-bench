from load_config import load_config


def test_full_config():
    cfg = load_config({"host": "h", "port": 80, "timeout": 5, "retries": 2})
    assert cfg == {"host": "h", "port": 80, "timeout": 5, "retries": 2}


def test_missing_optional_keys_use_defaults():
    cfg = load_config({"host": "h", "port": 80})
    assert cfg["timeout"] == 30
    assert cfg["retries"] == 3
