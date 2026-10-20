from inventory_api import Inventory


def test_add_accumulates():
    inv = Inventory()
    inv.add("A", 5)
    inv.add("A", 3)
    assert inv.stock["A"] == 8


def test_decrement_refuses_insufficient_stock():
    inv = Inventory()
    inv.add("A", 2)
    assert inv.decrement("A", 5) is False
    assert inv.stock["A"] == 2


def test_decrement_ok():
    inv = Inventory()
    inv.add("A", 5)
    assert inv.decrement("A", 2) is True
    assert inv.stock["A"] == 3


def test_low_stock_includes_at_threshold():
    inv = Inventory()
    inv.add("A", 5)
    inv.add("B", 9)
    assert inv.low_stock(5) == ["A"]
