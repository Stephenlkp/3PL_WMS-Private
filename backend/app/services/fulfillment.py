"""Order, pick, pack, and ship workflow.

Creating an order posts RESERVED rows. Physical stock is unchanged until
dispatch, which posts OUTBOUND and releases the reservation in one ledger batch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.core.errors import AppError
from app.core.tenant import ensure_access, require_customer_id, scoped_customer_id
from app.domain.enums import OrderStatus, PickStatus, Role, ShipmentStatus, TxType
from app.domain.ledger import Allocation, LedgerError, StockPosition, allocate, compact_location, route_sort_key
from app.models.entities import (
    Location,
    Order,
    OrderItem,
    PickList,
    PickListItem,
    Product,
    Shipment,
    StoredFile,
    User,
)
from app.schemas import (
    DispatchIn,
    OrderCreate,
    OrderItemOut,
    OrderOut,
    PickLineOut,
    PickListOut,
    ShipmentOut,
)
from app.services.audit import write_audit
from app.services.catalog import normalize_barcode, resolve_product
from app.services.inventory import LedgerEntry, load_physical, post_entries, reject
from app.services.numbering import next_number


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _order_query():
    return select(Order).options(
        selectinload(Order.items).selectinload(OrderItem.product),
        selectinload(Order.customer),
        selectinload(Order.picklists),
        selectinload(Order.shipment),
    )


def lock_order(session: Session, order_id: uuid.UUID) -> Order:
    stmt = _order_query().where(Order.id == order_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    order = session.scalar(stmt)
    if order is None:
        raise AppError("Order not found", 404, "not_found")
    return order


def active_picklist(order: Order) -> PickList | None:
    session = object_session(order)
    if session is not None:
        return session.scalar(
            select(PickList)
            .where(PickList.order_id == order.id, PickList.status != PickStatus.CANCELLED)
            .order_by(PickList.created_at.desc())
            .limit(1)
        )
    for picklist in order.picklists:
        if picklist.status != PickStatus.CANCELLED:
            return picklist
    return None


def order_out(order: Order) -> OrderOut:
    picklist = active_picklist(order)
    return OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        customer_name=order.customer.name,
        order_number=order.order_number,
        status=order.status,
        receiver_name=order.receiver_name,
        receiver_phone=order.receiver_phone,
        receiver_address=order.receiver_address,
        courier=order.courier,
        tracking_number=order.tracking_number,
        notes=order.notes,
        airway_bill_file_id=order.airway_bill_file_id,
        created_at=order.created_at,
        items=[
            OrderItemOut(
                id=item.id,
                product_id=item.product_id,
                sku=item.product.sku,
                barcode=item.product.barcode,
                product_name=item.product.name,
                quantity=item.quantity,
                picked_qty=item.picked_qty,
                packed_qty=item.packed_qty,
            )
            for item in order.items
        ],
        picklist_id=picklist.id if picklist else None,
        shipment_id=order.shipment.id if order.shipment else None,
    )


def picklist_out(picklist: PickList) -> PickListOut:
    lines = sorted(picklist.lines, key=lambda line: line.sequence)
    return PickListOut(
        id=picklist.id,
        pick_number=picklist.pick_number,
        order_id=picklist.order_id,
        order_number=picklist.order.order_number,
        customer_id=picklist.order.customer_id,
        customer_name=picklist.order.customer.name,
        status=picklist.status,
        lines=[
            PickLineOut(
                id=line.id,
                sku=line.product.sku,
                barcode=line.product.barcode,
                product_name=line.product.name,
                location_code=line.location.location_code,
                compact_location=compact_location(line.location.location_code),
                quantity=line.quantity,
                picked_qty=line.picked_qty,
                sequence=line.sequence,
            )
            for line in lines
        ],
    )


def shipment_out(shipment: Shipment) -> ShipmentOut:
    return ShipmentOut(
        id=shipment.id,
        shipment_number=shipment.shipment_number,
        order_id=shipment.order_id,
        order_number=shipment.order.order_number,
        customer_id=shipment.customer_id,
        customer_name=shipment.order.customer.name,
        status=shipment.status,
        courier=shipment.courier,
        tracking_number=shipment.tracking_number,
        airway_bill_file_id=shipment.airway_bill_file_id,
        receiver_name=shipment.order.receiver_name,
        item_count=sum(item.quantity for item in shipment.order.items),
        shipped_at=shipment.shipped_at,
        created_at=shipment.created_at,
    )


def _load_pick(session: Session, picklist_id: uuid.UUID) -> PickList:
    picklist = session.scalar(
        select(PickList)
        .where(PickList.id == picklist_id)
        .options(
            selectinload(PickList.lines).selectinload(PickListItem.product),
            selectinload(PickList.lines).selectinload(PickListItem.location),
            selectinload(PickList.lines).selectinload(PickListItem.order_item),
            selectinload(PickList.order).selectinload(Order.customer),
            selectinload(PickList.order).selectinload(Order.items),
        )
    )
    if picklist is None:
        raise AppError("Pick list not found", 404, "not_found")
    return picklist


def _allocated(session: Session, product_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(PickListItem.location_id, func.coalesce(func.sum(PickListItem.quantity), 0))
        .join(PickList, PickList.id == PickListItem.picklist_id)
        .join(Order, Order.id == PickList.order_id)
        .where(
            PickListItem.product_id == product_id,
            PickList.status != PickStatus.CANCELLED,
            Order.status.notin_([OrderStatus.SHIPPED, OrderStatus.CANCELLED]),
        )
        .group_by(PickListItem.location_id)
    ).all()
    return {location_id: int(qty) for location_id, qty in rows}


def _free_positions(session: Session, product: Product) -> list[StockPosition]:
    physical = load_physical(session, product.customer_id, product.id)
    allocated = _allocated(session, product.id)
    positions: list[StockPosition] = []
    for location_id in set(physical) | set(allocated):
        free = physical.get(location_id, 0) - allocated.get(location_id, 0)
        if free <= 0:
            continue
        location = session.get(Location, location_id)
        if location is None or not location.active:
            continue
        positions.append(
            StockPosition(
                location_id=location.id,
                location_code=location.location_code,
                zone=location.zone,
                rack=location.rack,
                level=location.level,
                free_qty=free,
            )
        )
    return positions


def list_orders(session: Session, user: User, status: str | None, customer_id: uuid.UUID | None) -> list[Order]:
    scoped = scoped_customer_id(user, customer_id)
    stmt = _order_query().order_by(Order.created_at.desc())
    if scoped is not None:
        stmt = stmt.where(Order.customer_id == scoped)
    if status:
        stmt = stmt.where(Order.status == status)
    return list(session.scalars(stmt).all())


def get_order(session: Session, user: User, order_id: uuid.UUID) -> Order:
    order = session.scalar(_order_query().where(Order.id == order_id))
    if order is None:
        raise AppError("Order not found", 404, "not_found")
    ensure_access(user, order.customer_id)
    return order


def create_order(session: Session, user: User, payload: OrderCreate, ip: str | None) -> Order:
    customer_id = require_customer_id(user, payload.customer_id)
    stored_key = f"{user.id}:{payload.idempotency_key}" if payload.idempotency_key else None
    if stored_key:
        existing = session.scalar(_order_query().where(Order.idempotency_key == stored_key))
        if existing is not None:
            ensure_access(user, existing.customer_id)
            return existing
    seen: set[uuid.UUID] = set()
    resolved: list[tuple[Product, int]] = []
    for line in payload.items:
        product = resolve_product(
            session,
            user,
            product_id=line.product_id,
            sku=line.sku,
            customer_id=customer_id,
        )
        if product.customer_id != customer_id:
            raise AppError("Product is not in this customer catalog", 404, "not_found")
        if not product.active:
            raise AppError(f"{product.sku} is inactive", 400, "inactive_product")
        if product.id in seen:
            raise AppError(f"Duplicate SKU {product.sku}", 400, "duplicate_sku")
        seen.add(product.id)
        resolved.append((product, line.quantity))
    order = Order(
        customer_id=customer_id,
        order_number=next_number(session, "SO"),
        status=OrderStatus.PENDING,
        receiver_name=payload.receiver_name.strip(),
        receiver_phone=payload.receiver_phone.strip(),
        receiver_address=payload.receiver_address.strip(),
        courier=payload.courier.strip(),
        tracking_number=payload.tracking_number.strip() if payload.tracking_number else None,
        notes=payload.notes,
        idempotency_key=stored_key,
        created_by=user.id,
    )
    session.add(order)
    session.flush()
    for product, quantity in resolved:
        session.add(OrderItem(order_id=order.id, product_id=product.id, quantity=quantity, picked_qty=0, packed_qty=0))
    post_entries(
        session,
        [
            LedgerEntry(
                customer_id=customer_id,
                product_id=product.id,
                location_id=None,
                tx_type=TxType.RESERVED,
                quantity=quantity,
                reference_no=order.order_number,
                reference_type="order",
                reference_id=order.id,
                notes="Reserve for order",
            )
            for product, quantity in resolved
        ],
        user,
        audit_action="inventory.reserve",
        ip=ip,
        entity_type="order",
        entity_id=order.id,
    )
    write_audit(
        session,
        user=user,
        action="order.create",
        entity_type="order",
        entity_id=order.id,
        ip=ip,
        customer_id=customer_id,
        new={"order_number": order.order_number, "lines": len(resolved)},
    )
    return get_order(session, user, order.id)


def cancel_order(session: Session, user: User, order_id: uuid.UUID, ip: str | None) -> Order:
    order = lock_order(session, order_id)
    ensure_access(user, order.customer_id)
    if order.status == OrderStatus.CANCELLED:
        return order
    if order.status == OrderStatus.SHIPPED:
        raise AppError("Shipped orders cannot be cancelled", 409, "already_shipped")
    if user.role == Role.CUSTOMER and order.status != OrderStatus.PENDING:
        raise AppError("Customers can cancel only pending orders", 403, "forbidden")
    post_entries(
        session,
        [
            LedgerEntry(
                customer_id=order.customer_id,
                product_id=item.product_id,
                location_id=None,
                tx_type=TxType.RESERVED,
                quantity=-item.quantity,
                reference_no=order.order_number,
                reference_type="order",
                reference_id=order.id,
                notes="Release reservation",
            )
            for item in order.items
        ],
        user,
        audit_action="inventory.release",
        ip=ip,
        entity_type="order",
        entity_id=order.id,
    )
    for picklist in session.scalars(select(PickList).where(PickList.order_id == order.id)).all():
        if picklist.status != PickStatus.CANCELLED:
            picklist.status = PickStatus.CANCELLED
    order.status = OrderStatus.CANCELLED
    order.updated_at = _utcnow()
    write_audit(
        session,
        user=user,
        action="order.cancel",
        entity_type="order",
        entity_id=order.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"order_number": order.order_number},
    )
    return order


def generate_picklist(session: Session, user: User, order_id: uuid.UUID, ip: str | None) -> PickList:
    order = lock_order(session, order_id)
    ensure_access(user, order.customer_id)
    if order.status == OrderStatus.CANCELLED:
        raise AppError("Cancelled orders cannot be picked", 409, "cancelled")
    existing = active_picklist(order)
    if existing is not None:
        return _load_pick(session, existing.id)
    if order.status != OrderStatus.PENDING:
        raise AppError("Pick list can only be generated for a pending order", 409, "invalid_status")
    drafted: list[tuple[OrderItem, Allocation]] = []
    try:
        for item in order.items:
            plan = allocate(_free_positions(session, item.product), item.quantity)
            drafted.extend((item, allocation) for allocation in plan)
    except LedgerError as exc:
        raise AppError(exc.message, 409, exc.code) from exc
    drafted.sort(key=lambda pair: route_sort_key(pair[1].zone, pair[1].rack, pair[1].level, pair[1].location_code))
    picklist = PickList(order_id=order.id, pick_number=next_number(session, "PL"), status=PickStatus.PENDING)
    picklist.order = order
    session.add(picklist)
    session.flush()
    for sequence, (item, allocation) in enumerate(drafted, start=1):
        session.add(
            PickListItem(
                picklist_id=picklist.id,
                order_item_id=item.id,
                product_id=item.product_id,
                location_id=allocation.location_id,
                quantity=allocation.quantity,
                picked_qty=0,
                sequence=sequence,
            )
        )
    order.status = OrderStatus.PICKING
    order.updated_at = _utcnow()
    session.flush()
    write_audit(
        session,
        user=user,
        action="picklist.generate",
        entity_type="picklist",
        entity_id=picklist.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"order_number": order.order_number, "lines": len(drafted)},
    )
    return _load_pick(session, picklist.id)


def list_picklists(session: Session, user: User, status: str | None) -> list[PickList]:
    stmt = (
        select(PickList)
        .join(Order, Order.id == PickList.order_id)
        .options(
            selectinload(PickList.lines).selectinload(PickListItem.product),
            selectinload(PickList.lines).selectinload(PickListItem.location),
            selectinload(PickList.order).selectinload(Order.customer),
        )
        .order_by(PickList.created_at.desc())
    )
    if user.role == Role.CUSTOMER:
        stmt = stmt.where(Order.customer_id == user.customer_id)
    if status:
        stmt = stmt.where(PickList.status == status)
    else:
        stmt = stmt.where(PickList.status.in_([PickStatus.PENDING, PickStatus.PICKING]))
    return list(session.scalars(stmt).all())


def get_picklist(session: Session, user: User, picklist_id: uuid.UUID) -> PickList:
    picklist = _load_pick(session, picklist_id)
    ensure_access(user, picklist.order.customer_id)
    return picklist


def scan_pick(session: Session, user: User, picklist_id: uuid.UUID, barcode: str, quantity: int, ip: str | None) -> PickList:
    picklist = _load_pick(session, picklist_id)
    order = picklist.order
    ensure_access(user, order.customer_id)
    if picklist.status in {PickStatus.PICKED, PickStatus.CANCELLED} or order.status in {OrderStatus.CANCELLED, OrderStatus.SHIPPED}:
        raise AppError("This pick is not open", 409, "invalid_status")
    code = normalize_barcode(barcode)
    product = session.scalar(select(Product).where(Product.barcode == code))
    lines = sorted(picklist.lines, key=lambda line: line.sequence)
    wrong = product is None or product.customer_id != order.customer_id or all(line.product_id != product.id for line in lines)
    if wrong:
        label = product.sku if product is not None and product.customer_id == order.customer_id else code
        reject(
            session,
            AppError(f"Wrong SKU for this order ({label})", 409, "wrong_sku"),
            user=user,
            action="pick.scan_rejected",
            entity_type="picklist",
            entity_id=picklist.id,
            ip=ip,
            customer_id=order.customer_id,
            new={"barcode": code},
        )
    assert product is not None
    open_lines = [line for line in lines if line.product_id == product.id and line.picked_qty < line.quantity]
    if not open_lines:
        raise AppError(f"{product.sku} is already fully picked", 409, "quantity_exceeded")
    line = open_lines[0]
    if line.picked_qty + quantity > line.quantity:
        raise AppError(f"Quantity exceeds the remaining pick for {product.sku}", 409, "quantity_exceeded")
    line.picked_qty += quantity
    line.order_item.picked_qty += quantity
    if picklist.status == PickStatus.PENDING:
        picklist.status = PickStatus.PICKING
        picklist.started_at = _utcnow()
        picklist.picker_id = user.id
    write_audit(
        session,
        user=user,
        action="pick.scan",
        entity_type="picklist",
        entity_id=picklist.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"sku": product.sku, "quantity": quantity, "location": line.location.location_code},
    )
    return picklist


def complete_pick(session: Session, user: User, picklist_id: uuid.UUID, ip: str | None) -> PickList:
    picklist = _load_pick(session, picklist_id)
    order = picklist.order
    ensure_access(user, order.customer_id)
    if picklist.status == PickStatus.CANCELLED:
        raise AppError("This pick is cancelled", 409, "cancelled")
    remaining = [line for line in picklist.lines if line.picked_qty != line.quantity]
    if remaining:
        detail = ", ".join(f"{line.product.sku} {line.picked_qty}/{line.quantity}" for line in remaining)
        raise AppError(f"Pick incomplete: {detail}", 409, "pick_incomplete")
    picklist.status = PickStatus.PICKED
    picklist.completed_at = _utcnow()
    if picklist.picker_id is None:
        picklist.picker_id = user.id
    order.status = OrderStatus.PICKED
    order.updated_at = _utcnow()
    write_audit(
        session,
        user=user,
        action="pick.complete",
        entity_type="picklist",
        entity_id=picklist.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"order_number": order.order_number},
    )
    return picklist


def scan_pack(session: Session, user: User, order_id: uuid.UUID, barcode: str, quantity: int, ip: str | None) -> Order:
    order = lock_order(session, order_id)
    ensure_access(user, order.customer_id)
    if order.status not in {OrderStatus.PICKED, OrderStatus.PACKING}:
        raise AppError("Order is not ready to pack", 409, "invalid_status")
    code = normalize_barcode(barcode)
    product = session.scalar(select(Product).where(Product.barcode == code))
    item = next((row for row in order.items if product is not None and row.product_id == product.id), None)
    if product is None or product.customer_id != order.customer_id or item is None:
        reject(
            session,
            AppError("Wrong SKU for this order", 409, "wrong_sku"),
            user=user,
            action="pack.scan_rejected",
            entity_type="order",
            entity_id=order.id,
            ip=ip,
            customer_id=order.customer_id,
            new={"barcode": code},
        )
    assert item is not None and product is not None
    if item.packed_qty + quantity > item.picked_qty:
        raise AppError(
            f"Packed quantity cannot exceed picked quantity for {product.sku}",
            409,
            "pack_mismatch",
        )
    item.packed_qty += quantity
    if order.status == OrderStatus.PICKED:
        order.status = OrderStatus.PACKING
    order.updated_at = _utcnow()
    write_audit(
        session,
        user=user,
        action="pack.scan",
        entity_type="order",
        entity_id=order.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"sku": product.sku, "quantity": quantity},
    )
    return order


def complete_pack(session: Session, user: User, order_id: uuid.UUID, ip: str | None) -> Shipment:
    order = lock_order(session, order_id)
    ensure_access(user, order.customer_id)
    if order.shipment is not None and order.status == OrderStatus.READY_TO_SHIP:
        return _shipment(session, order.shipment.id)
    if order.status not in {OrderStatus.PICKED, OrderStatus.PACKING}:
        raise AppError("Order is not ready to pack", 409, "invalid_status")
    mismatches = [item for item in order.items if item.packed_qty != item.picked_qty or item.picked_qty != item.quantity]
    if mismatches:
        detail = ", ".join(f"{item.product.sku} picked {item.picked_qty} packed {item.packed_qty}" for item in mismatches)
        raise AppError(f"Picked SKU and packed SKU do not match: {detail}", 409, "pack_mismatch")
    shipment = Shipment(
        order_id=order.id,
        customer_id=order.customer_id,
        shipment_number=next_number(session, "SHP"),
        status=ShipmentStatus.READY_TO_SHIP,
        courier=order.courier,
        tracking_number=order.tracking_number,
        airway_bill_file_id=order.airway_bill_file_id,
    )
    session.add(shipment)
    order.status = OrderStatus.READY_TO_SHIP
    order.updated_at = _utcnow()
    session.flush()
    write_audit(
        session,
        user=user,
        action="pack.complete",
        entity_type="shipment",
        entity_id=shipment.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"shipment_number": shipment.shipment_number, "order_number": order.order_number},
    )
    return _shipment(session, shipment.id)


def attach_airway_bill(session: Session, user: User, order_id: uuid.UUID, stored: StoredFile, ip: str | None) -> Order:
    order = lock_order(session, order_id)
    ensure_access(user, order.customer_id)
    if order.status in {OrderStatus.SHIPPED, OrderStatus.CANCELLED}:
        raise AppError("This order cannot accept an airway bill", 409, "invalid_status")
    if stored.customer_id != order.customer_id:
        raise AppError("File belongs to another customer", 403, "tenant_mismatch")
    order.airway_bill_file_id = stored.id
    if order.shipment is not None:
        order.shipment.airway_bill_file_id = stored.id
    order.updated_at = _utcnow()
    write_audit(
        session,
        user=user,
        action="order.airway_bill",
        entity_type="order",
        entity_id=order.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"file_id": str(stored.id)},
    )
    return order


def list_shipments(session: Session, user: User, status: str | None, customer_id: uuid.UUID | None) -> list[Shipment]:
    scoped = scoped_customer_id(user, customer_id)
    stmt = (
        select(Shipment)
        .join(Order, Order.id == Shipment.order_id)
        .options(selectinload(Shipment.order).selectinload(Order.customer), selectinload(Shipment.order).selectinload(Order.items))
        .order_by(Shipment.created_at.desc())
    )
    if scoped is not None:
        stmt = stmt.where(Shipment.customer_id == scoped)
    if status:
        stmt = stmt.where(Shipment.status == status)
    return list(session.scalars(stmt).all())


def _shipment(session: Session, shipment_id: uuid.UUID) -> Shipment:
    shipment = session.scalar(
        select(Shipment)
        .where(Shipment.id == shipment_id)
        .options(selectinload(Shipment.order).selectinload(Order.customer), selectinload(Shipment.order).selectinload(Order.items))
    )
    if shipment is None:
        raise AppError("Shipment not found", 404, "not_found")
    return shipment


def get_shipment(session: Session, user: User, shipment_id: uuid.UUID) -> Shipment:
    shipment = _shipment(session, shipment_id)
    ensure_access(user, shipment.customer_id)
    return shipment


def dispatch(session: Session, user: User, shipment_id: uuid.UUID, payload: DispatchIn, ip: str | None) -> Shipment:
    shipment = _shipment(session, shipment_id)
    order = lock_order(session, shipment.order_id)
    ensure_access(user, order.customer_id)
    if shipment.status != ShipmentStatus.READY_TO_SHIP or order.status != OrderStatus.READY_TO_SHIP:
        raise AppError("Shipment is not ready to dispatch", 409, "invalid_status")
    picklist = active_picklist(order)
    if picklist is None or picklist.status != PickStatus.PICKED:
        raise AppError("Pick verification is missing", 409, "pick_missing")
    picklist = _load_pick(session, picklist.id)
    if payload.tracking_number:
        shipment.tracking_number = payload.tracking_number.strip()
        order.tracking_number = shipment.tracking_number
    entries: list[LedgerEntry] = []
    for item in order.items:
        entries.append(
            LedgerEntry(
                customer_id=order.customer_id,
                product_id=item.product_id,
                location_id=None,
                tx_type=TxType.RESERVED,
                quantity=-item.quantity,
                reference_no=shipment.shipment_number,
                reference_type="shipment",
                reference_id=shipment.id,
                notes="Release reservation on dispatch",
            )
        )
    for line in picklist.lines:
        entries.append(
            LedgerEntry(
                customer_id=order.customer_id,
                product_id=line.product_id,
                location_id=line.location_id,
                tx_type=TxType.OUTBOUND,
                quantity=-line.quantity,
                reference_no=shipment.shipment_number,
                reference_type="shipment",
                reference_id=shipment.id,
                notes="Ship",
            )
        )
    post_entries(
        session,
        entries,
        user,
        audit_action="inventory.ship",
        ip=ip,
        entity_type="shipment",
        entity_id=shipment.id,
    )
    shipment.status = ShipmentStatus.SHIPPED
    shipment.shipped_at = _utcnow()
    shipment.shipped_by = user.id
    order.status = OrderStatus.SHIPPED
    order.updated_at = _utcnow()
    write_audit(
        session,
        user=user,
        action="shipment.dispatch",
        entity_type="shipment",
        entity_id=shipment.id,
        ip=ip,
        customer_id=order.customer_id,
        new={"shipment_number": shipment.shipment_number, "order_number": order.order_number},
    )
    return _shipment(session, shipment.id)

