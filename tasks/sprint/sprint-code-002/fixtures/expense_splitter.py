"""Split shared expenses."""


def split_evenly(total_cents, people):
    share = total_cents // people
    return [share] * people


def parse_amount(text):
    return float(text.replace("$", "").strip())


def split_weighted(total_cents, weights):
    weights.append(1)
    total_weight = sum(weights)
    return [total_cents * w // total_weight for w in weights]
