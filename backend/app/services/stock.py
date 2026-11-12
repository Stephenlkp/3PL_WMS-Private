import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.tenant import ensure_access, scoped_customer_id
from app.domain.enums import TxType
from app.models.entities import Product, User
from app.schemas import AdjustIn, MoveIn, PostingOut, ReceiveIn
from app.services.catalog import get_location, resolve_product
from app.services.inventory import LedgerEntry, post_entries, product_position
from app.services.numbering import next_number


def _posting(session: Session, product: Product, reference_no: str) -> PostingOut:
    on_hand, reserved, available = product_position(session, product)
    return PostingOut(
        reference_no=reference_no,
        product_id=product.id,
        sku=product.sku,
        on_hand_qty=on_hand,
        reserved_qty=reserved,
        available_qty=available,
    )


def receive(session: Session, user: User, payload: ReceiveIn, ip: str | None) -> PostingOut:
    location = get_location(session, payload.location_id, payload.location_code)
    if not location.active:
        raise AppError("Location is not available", 400, "invalid_location")
    resolved: list[tuple[Product, int]] = []
    for line in payload.lines:
        product = resolve_product(session, user, product_id=line.product_id, barcode=line.barcode)
        if not product.active:
            raise AppError(f"{product.sku} is inactive", 400, "inactive_product")
        resolved.append((product, line.quantity))
    customer_ids = {product.customer_id for product, _qty in resolved}
    if len(customer_ids) != 1:
        raise AppError("Receive one customer at a time", 400, "mixed_customer")
    customer_id = customer_ids.pop()
    if payload.customer_id is not None and payload.customer_id != customer_id:
        raise AppError("Scanned products belong to a different customer", 409, "tenant_mismatch")
    ensure_access(user, customer_id)
    reference = next_number(session, "RCV")
    entries = [
        LedgerEntry(
            customer_id=customer_id,
            product_id=product.id,
            location_id=location.id,
            tx_type=TxType.INBOUND,
            quantity=qty,
            reference_no=reference,
            reference_type="receipt",
            notes=payload.notes,
        )
        for product, qty in resolved
    ]
    post_entries(
        session,
        entries,
        user,
        audit_action="inventory.receive",
        ip=ip,
        entity_type="receipt",
        entity_id=reference,
    )
    return _posting(session, resolved[0][0], reference)


def move_stock(session: Session, user: User, payload: MoveIn, ip: str | None) -> PostingOut:
    product = resolve_product(session, user, product_id=payload.product_id, barcode=payload.barcode)
    source = get_location(session, payload.from_location_id, payload.from_location_code)
    destination = get_location(session, payload.to_location_id, payload.to_location_code)
    if source.id == destination.id:
        raise AppError("Source and destination are the same location", 400, "same_location")
    if not destination.active:
        raise AppError("Destination location is not available", 400, "invalid_location")
    reference = next_number(session, "MOV")
    correlation = uuid.uuid4()
    note = payload.notes
    entries = [
        LedgerEntry(
            customer_id=product.customer_id,
            product_id=product.id,
            location_id=source.id,
            tx_type=TxType.MOVE,
            quantity=-payload.quantity,
            reference_no=reference,
            reference_type="move",
            correlation_id=correlation,
            notes=note,
        ),
        LedgerEntry(
            customer_id=product.customer_id,
            product_id=product.id,
            location_id=destination.id,
            tx_type=TxType.MOVE,
            quantity=payload.quantity,
            reference_no=reference,
            reference_type="move",
            correlation_id=correlation,
            notes=note,
        ),
    ]
    post_entries(session, entries, user, audit_action="inventory.move", ip=ip, entity_type="move", entity_id=reference)
    return _posting(session, product, reference)


def adjust_stock(session: Session, user: User, payload: AdjustIn, ip: str | None) -> PostingOut:
    if payload.quantity == 0:
        raise AppError("Quantity cannot be zero", 400, "zero_quantity")
    product = resolve_product(session, user, product_id=payload.product_id)
    location = get_location(session, payload.location_id, None)
    reference = next_number(session, "ADJ")
    tx_type = TxType.ADJUSTMENT
    post_entries(
        session,
        [
            LedgerEntry(
                customer_id=product.customer_id,
                product_id=product.id,
                location_id=location.id,
                tx_type=tx_type,
                quantity=payload.quantity,
                reference_no=reference,
                reference_type="adjustment",
                notes=payload.notes,
            )
        ],
        user,
        audit_action="inventory.adjust",
        ip=ip,
        entity_type="adjustment",
        entity_id=reference,
    )
    return _posting(session, product, reference)


def customer_filter(user: User, requested: uuid.UUID | None) -> uuid.UUID | None:
    return scoped_customer_id(user, requested)
