"""Load service configuration."""


def load_config(raw):
    return {
        "host": raw["host"],
        "port": raw["port"],
        "timeout": raw["timeout"],
        "retries": raw["retries"],
    }
