import pytest

from handlers import OrderAPI

TOKEN = "s3cret"


def test_create_and_total():
    api = OrderAPI(TOKEN)
    oid = api.create_order(TOKEN, "SKU1", 3, 10.0)
    assert api.order_total(TOKEN, oid) == 30.0
    assert api.get_order(TOKEN, oid)["sku"] == "SKU1"


def test_auth_required():
    api = OrderAPI(TOKEN)
    with pytest.raises(PermissionError):
        api.create_order("nope", "SKU1", 1, 1.0)
    oid = api.create_order(TOKEN, "SKU1", 1, 1.0)
    with pytest.raises(PermissionError):
        api.get_order("nope", oid)


def test_missing_order_total_is_zero():
    api = OrderAPI(TOKEN)
    assert api.order_total(TOKEN, 999) == 0.0
