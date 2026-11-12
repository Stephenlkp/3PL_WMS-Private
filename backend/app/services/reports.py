from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi.responses import Response
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.redis import redis_client
from app.core.tenant import require_customer_id, scoped_customer_id
from app.core.time import ensure_utc
from app.domain.enums import OrderStatus, ShipmentStatus, TxType
from app.domain.ledger import age_bucket
from app.models.entities import Customer, InventoryTransaction, Order, Product, RateCard, Shipment, User  # Customer used by billing
from app.schemas import (
    BillingLine,
    BillingReport,
    CustomerDashboard,
    DeadStockRow,
    FastMoveRow,
    LowStockRow,
    WarehouseDashboard,
)
from app.services.queries import balance_rows, transaction_rows

logger = logging.getLogger(__name__)


def _range(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime, date, date]:
    today = datetime.now(UTC).date()
    end = date_to or today
    start = date_from or (end - timedelta(days=30))
    if start > end:
        raise AppError("date_from is after date_to", 400, "invalid_range")
    if (end - start).days > 366:
        raise AppError("Date range cannot exceed 366 days", 400, "invalid_range")
    return (
        datetime.combine(start, time.min, tzinfo=UTC),
        datetime.combine(end, time.max, tzinfo=UTC),
        start,
        end,
    )


def low_stock_rows(session: Session, customer_id: uuid.UUID | None = None) -> list[LowStockRow]:
    rows = []
    for row in balance_rows(session, _staff_view(), customer_id=customer_id, q=None, view="sku", low_stock=True):
        product = session.get(Product, row.product_id)
        rows.append(
            LowStockRow(
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                product_id=row.product_id,
                sku=row.sku,
                product_name=row.product_name,
                on_hand_qty=row.on_hand_qty,
                reserved_qty=row.reserved_qty,
                available_qty=row.available_qty,
                reorder_point=product.reorder_point if product else 0,
            )
        )
    return rows


def _staff_view() -> User:
    """Balance queries scope a customer only when the user is a customer."""
    return User(
        email="system@local",
        password_hash="x",
        full_name="System",
        role="admin",
        active=True,
    )


def remember_low_stock(rows: list[LowStockRow]) -> None:
    client = redis_client()
    if client is None:
        return
    try:
        payload = json.dumps([row.model_dump(mode="json") for row in rows])
        client.set("wms:low_stock", payload, ex=3600)
    except Exception:
        logger.warning("Could not refresh the low-stock Redis snapshot", exc_info=True)
    finally:
        client.close()


def warehouse_dashboard(session: Session) -> WarehouseDashboard:
    balances = balance_rows(session, _staff_view(), customer_id=None, q=None, view="sku", low_stock=False)
    low = low_stock_rows(session, None)
    remember_low_stock(low)
    cutoff = datetime.now(UTC) - timedelta(days=settings.FAST_MOVE_DAYS)
    fast_rows = session.execute(
        select(InventoryTransaction.product_id, func.coalesce(-func.sum(InventoryTransaction.quantity), 0).label("qty"))
        .where(InventoryTransaction.transaction_type == TxType.OUTBOUND, InventoryTransaction.created_at >= cutoff)
        .group_by(InventoryTransaction.product_id)
        .order_by(func.coalesce(-func.sum(InventoryTransaction.quantity), 0).desc())
        .limit(8)
    ).all()
    dead_cutoff = datetime.now(UTC) - timedelta(days=settings.DEAD_STOCK_DAYS)
    dead_source = session.execute(
        select(
            InventoryTransaction.product_id,
            func.max(InventoryTransaction.created_at),
            func.coalesce(func.sum(InventoryTransaction.quantity), 0),
        )
        .where(InventoryTransaction.transaction_type != TxType.RESERVED)
        .group_by(InventoryTransaction.product_id)
    ).all()
    dead: list[DeadStockRow] = []
    for product_id, last_at, physical in dead_source:
        if int(physical) <= 0 or last_at is None:
            continue
        if ensure_utc(last_at) >= dead_cutoff:
            continue
        product = session.get(Product, product_id)
        if product is None:
            continue
        dead.append(
            DeadStockRow(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                customer_name=product.customer.name,
                on_hand_qty=int(physical),
                last_movement_at=last_at,
            )
        )
    today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    shipments_today = session.scalar(
        select(func.count()).select_from(Shipment).where(Shipment.status == ShipmentStatus.SHIPPED, Shipment.shipped_at >= today_start)
    )
    return WarehouseDashboard(
        total_sku=sum(1 for row in balances if row.on_hand_qty > 0),
        total_stock=sum(row.on_hand_qty for row in balances),
        orders_awaiting_picking=int(
            session.scalar(
                select(func.count()).select_from(Order).where(Order.status.in_([OrderStatus.PENDING, OrderStatus.PICKING]))
            )
            or 0
        ),
        orders_awaiting_packing=int(
            session.scalar(
                select(func.count()).select_from(Order).where(Order.status.in_([OrderStatus.PICKED, OrderStatus.PACKING]))
            )
            or 0
        ),
        ready_to_ship=int(
            session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.READY_TO_SHIP)) or 0
        ),
        shipments_today=int(shipments_today or 0),
        low_inventory=low[:8],
        fast_moving=[
            FastMoveRow(
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                customer_name=product.customer.name,
                outbound_qty=int(qty),
            )
            for product_id, qty in fast_rows
            if int(qty) > 0 and (product := session.get(Product, product_id)) is not None
        ],
        dead_stock=dead[:8],
    )


def customer_dashboard(session: Session, user: User) -> CustomerDashboard:
    customer_id = require_customer_id(user, None)
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise AppError("Customer not found", 404, "not_found")
    balances = balance_rows(session, user, customer_id=customer_id, q=None, view="sku", low_stock=False)
    low = [row for row in low_stock_rows(session, customer_id)]
    today_start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    open_orders = session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.customer_id == customer_id, Order.status.notin_([OrderStatus.SHIPPED, OrderStatus.CANCELLED]))
    )
    shipped_today = session.scalar(
        select(func.count())
        .select_from(Shipment)
        .where(Shipment.customer_id == customer_id, Shipment.status == ShipmentStatus.SHIPPED, Shipment.shipped_at >= today_start)
    )
    return CustomerDashboard(
        customer_id=customer.id,
        customer_name=customer.name,
        total_sku=sum(1 for row in balances if row.on_hand_qty > 0),
        total_stock=sum(row.on_hand_qty for row in balances),
        reserved_stock=sum(row.reserved_qty for row in balances),
        available_stock=sum(row.available_qty for row in balances),
        open_orders=int(open_orders or 0),
        shipments_today=int(shipped_today or 0),
        low_inventory=low,
        recent_movements=transaction_rows(session, user, customer_id=customer_id, product_id=None, tx_type=None, limit=12, offset=0),
    )


def aging_rows(session: Session, user: User, customer_id: uuid.UUID | None) -> list[dict]:
    scoped = scoped_customer_id(user, customer_id)
    stmt = (
        select(InventoryTransaction)
        .where(InventoryTransaction.transaction_type.in_([TxType.INBOUND, TxType.OUTBOUND, TxType.ADJUSTMENT]))
        .order_by(InventoryTransaction.created_at, InventoryTransaction.id)
    )
    if scoped is not None:
        stmt = stmt.where(InventoryTransaction.customer_id == scoped)
    layers: dict[uuid_mod.UUID, list[list]] = defaultdict(list)
    for tx in session.scalars(stmt).all():
        bucket = layers[tx.product_id]
        if tx.transaction_type == TxType.INBOUND or (tx.transaction_type == TxType.ADJUSTMENT and tx.quantity > 0):
            bucket.append([tx.created_at, tx.quantity])
            continue
        need = -tx.quantity if tx.quantity < 0 else 0
        while need > 0 and bucket:
            take = min(bucket[0][1], need)
            bucket[0][1] -= take
            need -= take
            if bucket[0][1] == 0:
                bucket.pop(0)
    now = datetime.now(UTC)
    grouped: dict[tuple, int] = defaultdict(int)
    products: dict = {}
    for product_id, remaining in layers.items():
        product = session.get(Product, product_id)
        if product is None:
            continue
        products[product_id] = product
        for received_at, qty in remaining:
            if qty <= 0:
                continue
            days = (now - ensure_utc(received_at)).days
            grouped[(product_id, age_bucket(days))] += qty
    rows = []
    for (product_id, bucket_name), qty in sorted(grouped.items(), key=lambda item: (products[item[0][0]].sku, item[0][1])):
        product = products[product_id]
        rows.append(
            {
                "customer": product.customer.name,
                "sku": product.sku,
                "product": product.name,
                "age_bucket": bucket_name,
                "quantity": qty,
            }
        )
    return rows


def fulfillment_rows(session: Session, user: User, customer_id: uuid.UUID | None, date_from: date | None, date_to: date | None) -> list[dict]:
    scoped = scoped_customer_id(user, customer_id)
    start, end, _, _ = _range(date_from, date_to)
    stmt = select(Order).where(Order.created_at >= start, Order.created_at <= end).order_by(Order.created_at.desc())
    if scoped is not None:
        stmt = stmt.where(Order.customer_id == scoped)
    rows = []
    for order in session.scalars(stmt).all():
        units = sum(item.quantity for item in order.items)
        shipped_at = order.shipment.shipped_at if order.shipment else None
        cycle = ""
        if shipped_at is not None:
            cycle = str(round((ensure_utc(shipped_at) - ensure_utc(order.created_at)).total_seconds() / 3600, 2))
        rows.append(
            {
                "order_number": order.order_number,
                "customer": order.customer.name,
                "status": order.status,
                "created_at": order.created_at.isoformat(),
                "shipped_at": shipped_at.isoformat() if shipped_at else "",
                "cycle_hours": cycle,
                "lines": len(order.items),
                "units": units,
            }
        )
    return rows


def shipment_rows(session: Session, user: User, customer_id: uuid.UUID | None, date_from: date | None, date_to: date | None) -> list[dict]:
    scoped = scoped_customer_id(user, customer_id)
    start, end, _, _ = _range(date_from, date_to)
    stmt = select(Shipment).where(Shipment.created_at >= start, Shipment.created_at <= end).order_by(Shipment.created_at.desc())
    if scoped is not None:
        stmt = stmt.where(Shipment.customer_id == scoped)
    rows = []
    for shipment in session.scalars(stmt).all():
        rows.append(
            {
                "shipment_number": shipment.shipment_number,
                "order_number": shipment.order.order_number,
                "customer": shipment.order.customer.name,
                "status": shipment.status,
                "courier": shipment.courier,
                "tracking_number": shipment.tracking_number or "",
                "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else "",
            }
        )
    return rows


def movement_dicts(session: Session, user: User, customer_id: uuid.UUID | None, date_from: date | None, date_to: date | None) -> list[dict]:
    start, end, _, _ = _range(date_from, date_to)
    scoped = scoped_customer_id(user, customer_id)
    rows = transaction_rows(session, user, customer_id=scoped, product_id=None, tx_type=None, limit=5000, offset=0)
    filtered = []
    for row in rows:
        created = ensure_utc(row.created_at)
        if start <= created <= end:
            filtered.append(
                {
                    "created_at": created.isoformat(),
                    "customer": row.customer_name,
                    "sku": row.sku,
                    "location": row.location_code or "",
                    "type": row.transaction_type,
                    "quantity": row.quantity,
                    "reference_no": row.reference_no,
                    "notes": row.notes or "",
                    "user": row.created_by_name or "",
                }
            )
    return filtered


def billing_report(session: Session, user: User, customer_id: uuid.UUID | None, date_from: date | None, date_to: date | None) -> BillingReport:
    scoped = require_customer_id(user, customer_id)
    customer = session.get(Customer, scoped)
    if customer is None:
        raise AppError("Customer not found", 404, "not_found")
    start, end, start_day, end_day = _range(date_from, date_to)
    card = session.scalar(select(RateCard).where(RateCard.customer_id == customer.id))
    currency = card.currency if card else "USD"
    storage_rate = card.storage_fee_per_unit_day if card else Decimal("0")
    inbound_rate = card.inbound_fee_per_unit if card else Decimal("0")
    order_rate = card.pick_pack_fee_per_order if card else Decimal("0")
    unit_rate = card.pick_pack_fee_per_unit if card else Decimal("0")
    inbound_units = int(
        session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity), 0)).where(
                InventoryTransaction.customer_id == customer.id,
                InventoryTransaction.transaction_type == TxType.INBOUND,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at <= end,
            )
        )
        or 0
    )
    shipped_orders = int(
        session.scalar(
            select(func.count()).select_from(Shipment).where(
                Shipment.customer_id == customer.id,
                Shipment.status == ShipmentStatus.SHIPPED,
                Shipment.shipped_at >= start,
                Shipment.shipped_at <= end,
            )
        )
        or 0
    )
    shipped_units = int(
        session.scalar(
            select(func.coalesce(-func.sum(InventoryTransaction.quantity), 0)).where(
                InventoryTransaction.customer_id == customer.id,
                InventoryTransaction.transaction_type == TxType.OUTBOUND,
                InventoryTransaction.created_at >= start,
                InventoryTransaction.created_at <= end,
            )
        )
        or 0
    )
    on_hand = sum(row.on_hand_qty for row in balance_rows(session, user, customer_id=customer.id, q=None, view="sku", low_stock=False))
    days = max((end_day - start_day).days, 1)
    storage_amount = (Decimal(on_hand) * storage_rate * Decimal(days)).quantize(Decimal("0.01"))
    inbound_amount = (Decimal(inbound_units) * inbound_rate).quantize(Decimal("0.01"))
    fulfillment_amount = (Decimal(shipped_orders) * order_rate + Decimal(shipped_units) * unit_rate).quantize(Decimal("0.01"))
    total = (storage_amount + inbound_amount + fulfillment_amount).quantize(Decimal("0.01"))
    return BillingReport(
        customer_id=customer.id,
        customer_name=customer.name,
        currency=currency,
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        method="Storage uses a snapshot of current on-hand units times the days in the range. Inbound and pick-pack use activity inside the range.",
        lines=[
            BillingLine(description="Storage", quantity=f"{on_hand} units x {days} days", rate=str(storage_rate), amount=str(storage_amount)),
            BillingLine(description="Inbound handling", quantity=str(inbound_units), rate=str(inbound_rate), amount=str(inbound_amount)),
            BillingLine(
                description="Pick and pack",
                quantity=f"{shipped_orders} orders / {shipped_units} units",
                rate=f"{order_rate} + {unit_rate}",
                amount=str(fulfillment_amount),
            ),
        ],
        total=str(total),
    )


def inventory_dicts(session: Session, user: User, customer_id: uuid.UUID | None) -> list[dict]:
    scoped = scoped_customer_id(user, customer_id)
    return [
        {
            "customer": row.customer_name,
            "sku": row.sku,
            "product": row.product_name,
            "barcode": row.barcode,
            "location": row.location_code or "",
            "on_hand": row.on_hand_qty,
            "reserved": row.reserved_qty,
            "available": row.available_qty,
            "at_location": "" if row.location_qty is None else row.location_qty,
        }
        for row in balance_rows(session, user, customer_id=scoped, q=None, view="location", low_stock=False)
    ]


def export_table(title: str, rows: list[dict], fmt: str) -> Response:
    columns = list(rows[0].keys()) if rows else ["empty"]
    if not rows:
        rows = [{"empty": "No rows"}]
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{title}.csv"'},
        )
    if fmt == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = title[:31]
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
        payload = io.BytesIO()
        workbook.save(payload)
        return Response(
            content=payload.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{title}.xlsx"'},
        )
    if fmt == "pdf":
        payload = io.BytesIO()
        doc = SimpleDocTemplate(payload, pagesize=landscape(letter), title=title)
        styles = getSampleStyleSheet()
        headers = list(rows[0].keys())
        data = [headers]
        for row in rows[:400]:
            data.append([str(row.get(header, ""))[:40] for header in headers])
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#171410")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2d9cc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3efe6")]),
                ]
            )
        )
        story = [Paragraph(title, styles["Title"]), Spacer(1, 12), table]
        doc.build(story)
        return Response(
            content=payload.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{title}.pdf"'},
        )
    raise AppError("format must be csv, xlsx, or pdf", 400, "invalid_format")

