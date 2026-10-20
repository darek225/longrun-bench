# Spec: migrate the order API

Migrate legacy_app.py (in the workspace) to a class-based layout in handlers.py: class `OrderAPI(token)` with methods create_order(auth, sku, qty, unit_price) returning an id (order total is qty times unit_price, rounded to 2 decimals), get_order(auth, order_id) returning the order dict or None, and order_total(auth, order_id) returning the total or 0.0 for missing orders. CHANGE.md in the workspace adds a requirement that applies to every method.
