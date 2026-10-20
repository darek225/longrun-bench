# Spec: usage billing (sqlite)

Functions: `init_db(path)` creates an events(customer, month, units) table and returns a connection. `record_event(conn, customer, month, units=1)` stores usage units. `monthly_usage(conn, customer, month)` returns summed units (0 when none). `invoice_total(conn, customer, month)`: the first 1000 units are free; units 1001-10000 cost $0.01 each; units above 10000 cost $0.008 each; return the total rounded to 2 decimals. Work in stages and keep memory.md updated.
