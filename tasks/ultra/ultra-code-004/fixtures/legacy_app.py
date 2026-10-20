"""Legacy order handlers (function style, no auth)."""

ORDERS = {}


def create_order(sku, qty, unit_price):
    oid = len(ORDERS) + 1
    ORDERS[oid] = {"id": oid, "sku": sku, "qty": qty, "unit_price": unit_price, "total": round(qty * unit_price, 2)}
    return oid


def get_order(order_id):
    return ORDERS.get(order_id)
