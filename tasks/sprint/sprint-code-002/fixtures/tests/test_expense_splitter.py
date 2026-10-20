from expense_splitter import parse_amount, split_evenly, split_weighted


def test_split_evenly_exact():
    assert split_evenly(100, 4) == [25, 25, 25, 25]


def test_split_evenly_remainder_is_distributed():
    parts = split_evenly(100, 3)
    assert sum(parts) == 100
    assert max(parts) - min(parts) <= 1


def test_parse_amount_with_commas():
    assert parse_amount("$1,200.50") == 1200.50


def test_parse_amount_plain():
    assert parse_amount("42") == 42.0


def test_split_weighted_does_not_mutate_weights():
    weights = [1, 1]
    split_weighted(100, weights)
    assert weights == [1, 1]


def test_split_weighted_values():
    assert split_weighted(100, [3, 1]) == [75, 25]
