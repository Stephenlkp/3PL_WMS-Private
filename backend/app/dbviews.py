"""Read models over the ledger. Available stock is physical minus reserved."""

INVENTORY_BALANCES = """
CREATE VIEW inventory_balances AS
SELECT
    customer_id,
    product_id,
    location_id,
    SUM(CASE WHEN transaction_type <> 'RESERVED' THEN quantity ELSE 0 END) AS physical_qty,
    SUM(CASE WHEN transaction_type = 'RESERVED' THEN quantity ELSE 0 END) AS reserved_qty,
    SUM(CASE WHEN transaction_type <> 'RESERVED' THEN quantity ELSE 0 END)
        - SUM(CASE WHEN transaction_type = 'RESERVED' THEN quantity ELSE 0 END) AS available_qty
FROM inventory_transactions
GROUP BY customer_id, product_id, location_id
"""

INVENTORY_BALANCES_BY_SKU = """
CREATE VIEW inventory_balances_by_sku AS
SELECT
    customer_id,
    product_id,
    SUM(CASE WHEN transaction_type <> 'RESERVED' THEN quantity ELSE 0 END) AS physical_qty,
    SUM(CASE WHEN transaction_type = 'RESERVED' THEN quantity ELSE 0 END) AS reserved_qty,
    SUM(CASE WHEN transaction_type <> 'RESERVED' THEN quantity ELSE 0 END)
        - SUM(CASE WHEN transaction_type = 'RESERVED' THEN quantity ELSE 0 END) AS available_qty
FROM inventory_transactions
GROUP BY customer_id, product_id
"""
