import base64

from sqlalchemy import select, text

from app.core.database import SessionLocal, engine
from app.dbviews import INVENTORY_BALANCES_BY_SKU
from app.models.entities import InventoryTransaction
from tests.conftest import PASSWORD, auth_header

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _world(client, admin):
    customer = client.post("/api/v1/customers", headers=admin, json={"code": "ACME", "name": "Acme Outdoor"}).json()
    other = client.post("/api/v1/customers", headers=admin, json={"code": "NWND", "name": "Northwind Gadgets"}).json()
    location = client.post("/api/v1/locations", headers=admin, json={"location_code": "A-01-02"}).json()
    other_location = client.post("/api/v1/locations", headers=admin, json={"location_code": "B-03-01"}).json()
    near = client.post("/api/v1/locations", headers=admin, json={"location_code": "A-01-01"}).json()
    product = client.post(
        "/api/v1/products",
        headers=admin,
        json={"customer_id": customer["id"], "sku": "WS-01", "name": "Stainless Bottle", "reorder_point": 5},
    ).json()
    second = client.post(
        "/api/v1/products",
        headers=admin,
        json={"customer_id": customer["id"], "sku": "WS-05", "name": "Camp Mug", "reorder_point": 2},
    ).json()
    hidden = client.post(
        "/api/v1/products",
        headers=admin,
        json={"customer_id": other["id"], "sku": "NW-LAMP", "name": "Desk Lamp", "barcode": "NWNDLAMP"},
    ).json()
    client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "picker@test.local",
            "password": PASSWORD,
            "full_name": "Pat Picker",
            "role": "picker",
        },
    )
    client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "packer@test.local",
            "password": PASSWORD,
            "full_name": "Paige Packer",
            "role": "packer",
        },
    )
    client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "acme@test.local",
            "password": PASSWORD,
            "full_name": "Avery Acme",
            "role": "customer",
            "customer_id": customer["id"],
        },
    )
    client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "email": "northwind@test.local",
            "password": PASSWORD,
            "full_name": "Nora North",
            "role": "customer",
            "customer_id": other["id"],
        },
    )
    return {
        "customer": customer,
        "other": other,
        "location": location,
        "other_location": other_location,
        "near": near,
        "product": product,
        "second": second,
        "hidden": hidden,
    }


def test_stock_is_derived_and_customers_are_isolated(client, admin):
    world = _world(client, admin)
    picker = auth_header(client, "picker@test.local")
    acme = auth_header(client, "acme@test.local")
    northwind = auth_header(client, "northwind@test.local")

    received = client.post(
        "/api/v1/inventory/receive",
        headers=picker,
        json={
            "location_code": "A-01-02",
            "lines": [{"barcode": world["product"]["barcode"], "quantity": 10}],
        },
    )
    assert received.status_code == 200, received.text
    assert received.json()["on_hand_qty"] == 10
    assert received.json()["available_qty"] == 10

    denied = client.post(
        "/api/v1/inventory/receive",
        headers=acme,
        json={"location_code": "A-01-02", "lines": [{"barcode": world["product"]["barcode"], "quantity": 1}]},
    )
    assert denied.status_code == 403

    order = client.post(
        "/api/v1/orders",
        headers=acme,
        json={
            "receiver_name": "Jamie Lee",
            "receiver_phone": "555-0100",
            "receiver_address": "12 Harbor Road",
            "courier": "J&T Express",
            "idempotency_key": "order-key-1",
            "items": [{"sku": "WS-01", "quantity": 4}],
        },
    )
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["status"] == "PENDING"
    again = client.post(
        "/api/v1/orders",
        headers=acme,
        json={
            "receiver_name": "Jamie Lee",
            "receiver_phone": "555-0100",
            "receiver_address": "12 Harbor Road",
            "courier": "J&T Express",
            "idempotency_key": "order-key-1",
            "items": [{"sku": "WS-01", "quantity": 4}],
        },
    )
    assert again.json()["id"] == body["id"]

    balances = client.get("/api/v1/inventory/balances", headers=acme).json()
    assert balances[0]["on_hand_qty"] == 10
    assert balances[0]["reserved_qty"] == 4
    assert balances[0]["available_qty"] == 6

    leaked = client.get(f"/api/v1/products/{world['hidden']['id']}", headers=acme)
    assert leaked.status_code == 404
    assert client.get("/api/v1/inventory/balances", headers=northwind).json() == []
    assert client.get("/api/v1/orders", headers=northwind).json() == []

    edited = client.patch(
        f"/api/v1/products/{world['product']['id']}",
        headers=admin,
        json={"quantity": 999},
    )
    assert edited.status_code == 422
    missing = client.post("/api/v1/inventory/transactions", headers=admin, json={"quantity": 5})
    assert missing.status_code == 405

    over = client.post(
        "/api/v1/orders",
        headers=acme,
        json={
            "receiver_name": "Too Much",
            "receiver_phone": "555-0101",
            "receiver_address": "1 Dock Street",
            "courier": "Ninja Van",
            "items": [{"product_id": world["product"]["id"], "quantity": 7}],
        },
    )
    assert over.status_code == 409

    with engine.begin() as connection:
        connection.execute(text(INVENTORY_BALANCES_BY_SKU))
        row = connection.execute(text("SELECT physical_qty, reserved_qty, available_qty FROM inventory_balances_by_sku")).one()
    assert (row.physical_qty, row.reserved_qty, row.available_qty) == (10, 4, 6)


def test_pick_pack_ship_reduces_stock_only_at_dispatch(client, admin):
    world = _world(client, admin)
    picker = auth_header(client, "picker@test.local")
    packer = auth_header(client, "packer@test.local")
    acme = auth_header(client, "acme@test.local")
    client.post(
        "/api/v1/inventory/receive",
        headers=picker,
        json={"location_code": "A-01-01", "lines": [{"barcode": world["product"]["barcode"], "quantity": 3}]},
    )
    client.post(
        "/api/v1/inventory/receive",
        headers=picker,
        json={"location_code": "A-01-02", "lines": [{"barcode": world["product"]["barcode"], "quantity": 8}]},
    )
    client.post(
        "/api/v1/inventory/receive",
        headers=picker,
        json={"location_code": "B-03-01", "lines": [{"barcode": world["second"]["barcode"], "quantity": 6}]},
    )
    order = client.post(
        "/api/v1/orders",
        headers=acme,
        json={
            "receiver_name": "Jamie Lee",
            "receiver_phone": "555-0100",
            "receiver_address": "12 Harbor Road",
            "courier": "J&T Express",
            "tracking_number": "JT1001",
            "items": [
                {"sku": "WS-01", "quantity": 5},
                {"sku": "WS-05", "quantity": 2},
            ],
        },
    ).json()
    pick = client.post(f"/api/v1/orders/{order['id']}/picklist", headers=picker)
    assert pick.status_code == 200, pick.text
    lines = pick.json()["lines"]
    assert [(line["sku"], line["quantity"], line["location_code"]) for line in lines] == [
        ("WS-01", 3, "A-01-01"),
        ("WS-01", 2, "A-01-02"),
        ("WS-05", 2, "B-03-01"),
    ]
    wrong = client.post(
        f"/api/v1/picklists/{pick.json()['id']}/scan",
        headers=picker,
        json={"barcode": world["hidden"]["barcode"]},
    )
    assert wrong.status_code == 409
    assert wrong.json()["code"] == "wrong_sku"
    still = client.get(f"/api/v1/picklists/{pick.json()['id']}", headers=picker).json()
    assert all(line["picked_qty"] == 0 for line in still["lines"])

    for line in lines:
        scanned = client.post(
            f"/api/v1/picklists/{pick.json()['id']}/scan",
            headers=picker,
            json={"barcode": line["barcode"], "quantity": line["quantity"]},
        )
        assert scanned.status_code == 200, scanned.text
    done = client.post(f"/api/v1/picklists/{pick.json()['id']}/complete", headers=picker)
    assert done.status_code == 200, done.text

    early = client.post(f"/api/v1/orders/{order['id']}/pack-complete", headers=packer)
    assert early.status_code == 409
    for line in lines:
        packed = client.post(
            f"/api/v1/orders/{order['id']}/pack-scan",
            headers=packer,
            json={"barcode": line["barcode"], "quantity": line["quantity"]},
        )
        assert packed.status_code == 200, packed.text
    bill = client.post(
        f"/api/v1/orders/{order['id']}/airway-bill",
        headers=acme,
        files={"file": ("airwaybill.png", PNG, "image/png")},
    )
    assert bill.status_code == 200, bill.text
    shipment = client.post(f"/api/v1/orders/{order['id']}/pack-complete", headers=packer)
    assert shipment.status_code == 200, shipment.text
    assert shipment.json()["status"] == "READY_TO_SHIP"
    assert shipment.json()["airway_bill_file_id"]

    before = client.get("/api/v1/inventory/balances?view=sku", headers=acme).json()
    bottle = next(row for row in before if row["sku"] == "WS-01")
    assert bottle["on_hand_qty"] == 11
    assert bottle["reserved_qty"] == 5

    dispatched = client.post(
        f"/api/v1/shipments/{shipment.json()['id']}/dispatch",
        headers=packer,
        json={"tracking_number": "JT1001"},
    )
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["status"] == "SHIPPED"
    after = client.get("/api/v1/inventory/balances?view=sku", headers=acme).json()
    bottle = next(row for row in after if row["sku"] == "WS-01")
    mug = next(row for row in after if row["sku"] == "WS-05")
    assert (bottle["on_hand_qty"], bottle["reserved_qty"], bottle["available_qty"]) == (6, 0, 6)
    assert (mug["on_hand_qty"], mug["reserved_qty"], mug["available_qty"]) == (4, 0, 4)
    twice = client.post(f"/api/v1/shipments/{shipment.json()['id']}/dispatch", headers=packer, json={})
    assert twice.status_code == 409

    found = client.get("/api/v1/locations/find-sku", headers=admin, params={"q": "WS-01"}).json()
    assert found[0]["sku"] == "WS-01"
    assert found[0]["placements"][0]["compact_location"] == "A01-02"
    assert found[0]["placements"][0]["physical_qty"] == 6
    search = client.get("/api/v1/search", headers=acme, params={"q": "JT1001"}).json()
    assert any(hit["tracking_number"] == "JT1001" for hit in search["hits"])
    preview = client.get(
        f"/api/v1/files/{bill.json()['airway_bill_file_id']}/content",
        headers=acme,
    )
    assert preview.status_code == 200
    assert preview.content.startswith(b"\x89PNG")
    hidden_file = client.get(f"/api/v1/files/{bill.json()['airway_bill_file_id']}/content", headers=auth_header(client, "northwind@test.local"))
    assert hidden_file.status_code == 404


def test_move_conserves_stock_and_adjustment_cannot_break_reservations(client, admin):
    world = _world(client, admin)
    client.post(
        "/api/v1/inventory/receive",
        headers=admin,
        json={"location_code": "A-01-02", "lines": [{"product_id": world["product"]["id"], "quantity": 10}]},
    )
    client.post(
        "/api/v1/orders",
        headers=admin,
        json={
            "customer_id": world["customer"]["id"],
            "receiver_name": "Jamie Lee",
            "receiver_phone": "555-0100",
            "receiver_address": "12 Harbor Road",
            "courier": "J&T Express",
            "items": [{"product_id": world["product"]["id"], "quantity": 8}],
        },
    )
    blocked = client.post(
        "/api/v1/inventory/adjust",
        headers=admin,
        json={
            "product_id": world["product"]["id"],
            "location_id": world["location"]["id"],
            "quantity": -5,
            "notes": "cycle count short",
        },
    )
    assert blocked.status_code == 409
    moved = client.post(
        "/api/v1/inventory/move",
        headers=admin,
        json={
            "product_id": world["product"]["id"],
            "from_location_code": "A-01-02",
            "to_location_code": "B-03-01",
            "quantity": 4,
        },
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["on_hand_qty"] == 10
    rows = client.get("/api/v1/inventory/balances?view=location", headers=admin).json()
    qty = {row["location_code"]: row["location_qty"] for row in rows if row["sku"] == "WS-01"}
    assert qty == {"A-01-02": 6, "B-03-01": 4}


def test_transactions_are_append_only(client, admin):
    world = _world(client, admin)
    client.post(
        "/api/v1/inventory/receive",
        headers=admin,
        json={"location_code": "A-01-02", "lines": [{"barcode": world["product"]["barcode"], "quantity": 2}]},
    )
    db = SessionLocal()
    try:
        row = db.scalar(select(InventoryTransaction))
        row.quantity = 99
        try:
            db.flush()
            raised = False
        except RuntimeError:
            raised = True
        assert raised
    finally:
        db.rollback()
        db.close()


def test_refresh_token_rotation_rejects_reuse(client, admin):
    first = client.post("/api/v1/auth/login", json={"email": "admin@test.local", "password": PASSWORD})
    refresh = first.json()["refresh_token"]
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != refresh
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reused.status_code == 401
    assert reused.json()["code"] == "token_reuse"


def test_reports_export_csv(client, admin):
    world = _world(client, admin)
    client.post(
        "/api/v1/inventory/receive",
        headers=admin,
        json={"location_code": "A-01-02", "lines": [{"barcode": world["product"]["barcode"], "quantity": 2}]},
    )
    exported = client.get("/api/v1/reports/inventory", headers=admin, params={"format": "csv"})
    assert exported.status_code == 200
    assert "WS-01" in exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    dashboard = client.get("/api/v1/reports/warehouse-dashboard", headers=admin)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["total_stock"] == 2
    barcode = client.get(f"/api/v1/products/{world['product']['id']}/barcode", headers=admin)
    assert barcode.status_code == 200
    assert barcode.content.startswith(b"\x89PNG")
    qr = client.get(f"/api/v1/products/{world['product']['id']}/barcode", headers=admin, params={"style": "qr"})
    assert qr.status_code == 200
    assert qr.content.startswith(b"\x89PNG")
    assert qr.content != barcode.content
