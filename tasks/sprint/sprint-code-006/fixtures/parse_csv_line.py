"""Parse one CSV line into fields."""


def parse_line(line):
    return [part.strip().strip(chr(34)) for part in line.split(",")]
