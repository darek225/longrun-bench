"""Analyze plain-text log files."""


def count_level(lines, level):
    return sum(1 for line in lines if level in line)


def first_error(lines):
    for line in reversed(lines):
        if "ERROR" in line:
            return line
    return None


def summarize(path):
    count = 0
    with open(path) as handle:
        for line in handle:
            count += 1
    return count
