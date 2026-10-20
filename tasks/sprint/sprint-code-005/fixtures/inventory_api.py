"""A tiny in-memory inventory."""


class Inventory:
    def __init__(self):
        self.stock = {}

    def add(self, sku, qty):
        self.stock[sku] = qty

    def decrement(self, sku, qty):
        self.stock[sku] = self.stock.get(sku, 0) - qty
        return True

    def low_stock(self, threshold):
        return [sku for sku, qty in self.stock.items() if qty < threshold]
