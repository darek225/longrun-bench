from dedupe import unique_preserve_order


def test_preserves_order_strings():
    assert unique_preserve_order(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_preserves_order_ints():
    assert unique_preserve_order([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_empty():
    assert unique_preserve_order([]) == []
