"""Summarize log lines as (level, message) pairs."""


def summarize(lines):
    out = []
    for line in lines:
        parts = line.split(' ', 1)
        out.append((parts[0], parts[1]))
    return out
