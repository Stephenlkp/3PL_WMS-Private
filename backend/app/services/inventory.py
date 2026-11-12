"""The only writer of inventory_transactions.

Routes for receive, move, adjust, reserve, release, and shipment all come
through post_entries. There is no endpoint that edits a balance row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domain.enums import TxType
from app.domain.ledger import LedgerError, apply_entry, assert_balances
from app.models.entities import InventoryTransaction, Location, Product, User
from app.services.audit import write_audit
from app.services.numbering import next_number


@dataclass
class LedgerEntry:
    customer_id: uuid.UUID
    product_id: uuid.UUID
    location_id: uuid.UUID | None
    tx_type: TxType
    quantity: int
    reference_no: str
    reference_type: str | None = None
    reference_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None


def load_physical(session: Session, customer_id: uuid.UUID, product_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(InventoryTransaction.location_id, func.coalesce(func.sum(InventoryTransaction.quantity), 0))
        .where(
            InventoryTransaction.customer_id == customer_id,
            InventoryTransaction.product_id == product_id,
            InventoryTransaction.transaction_type != TxType.RESERVED,
            InventoryTransaction.location_id.is_not(None),
        )
        .group_by(InventoryTransaction.location_id)
    ).all()
    return {location_id: int(qty) for location_id, qty in rows if location_id is not None and int(qty) != 0}


def load_reserved(session: Session, customer_id: uuid.UUID, product_id: uuid.UUID) -> int:
    qty = session.scalar(
        select(func.coalesce(func.sum(InventoryTransaction.quantity), 0)).where(
            InventoryTransaction.customer_id == customer_id,
            InventoryTransaction.product_id == product_id,
            InventoryTransaction.transaction_type == TxType.RESERVED,
        )
    )
    return int(qty or 0)


def product_position(session: Session, product: Product) -> tuple[int, int, int]:
    physical = load_physical(session, product.customer_id, product.id)
    reserved = load_reserved(session, product.customer_id, product.id)
    on_hand = sum(physical.values())
    return on_hand, reserved, on_hand - reserved


def post_entries(
    session: Session,
    entries: list[LedgerEntry],
    user: User,
    *,
    audit_action: str,
    ip: str | None = None,
    entity_type: str = "inventory",
    entity_id: str | uuid.UUID | None = None,
) -> None:
    if not entries:
        return
    grouped: dict[uuid.UUID, list[LedgerEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.product_id, []).append(entry)

    for product_id, group in grouped.items():
        stmt = select(Product).where(Product.id == product_id)
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        product = session.scalar(stmt)
        if product is None:
            raise AppError("Product not found", 404, "not_found")
        physical = load_physical(session, product.customer_id, product.id)
        reserved = load_reserved(session, product.customer_id, product.id)
        # Release reservations before outbound postings so other orders'
        # reservations are not treated as still covering units we are shipping.
        group.sort(key=lambda entry: 0 if entry.tx_type == TxType.RESERVED else 1)
        for entry in group:
            if entry.customer_id != product.customer_id:
                raise AppError("Product does not belong to this customer", 403, "tenant_mismatch")
            if entry.tx_type == TxType.RESERVED:
                entry.location_id = None
            else:
                location = session.get(Location, entry.location_id)
                if location is None or not location.active:
                    raise AppError("Location is not available", 400, "invalid_location")
            try:
                physical, reserved = apply_entry(
                    physical, reserved, entry.tx_type, entry.location_id, entry.quantity, check=False
                )
            except LedgerError as exc:
                raise AppError(exc.message, 409, exc.code) from exc
            row = InventoryTransaction(
                customer_id=entry.customer_id,
                product_id=entry.product_id,
                location_id=entry.location_id,
                transaction_type=entry.tx_type.value,
                quantity=entry.quantity,
                reference_no=entry.reference_no,
                reference_type=entry.reference_type,
                reference_id=entry.reference_id,
                correlation_id=entry.correlation_id,
                notes=entry.notes,
                created_by=user.id,
            )
            if entry.created_at is not None:
                row.created_at = entry.created_at
            session.add(row)
        try:
            assert_balances(physical, reserved)
        except LedgerError as exc:
            raise AppError(exc.message, 409, exc.code) from exc
    session.flush()
    write_audit(
        session,
        user=user,
        action=audit_action,
        entity_type=entity_type,
        entity_id=entity_id or entries[0].reference_no,
        ip=ip,
        customer_id=entries[0].customer_id,
        new={
            "reference_no": entries[0].reference_no,
            "lines": [
                {
                    "type": entry.tx_type.value,
                    "quantity": entry.quantity,
                    "product_id": str(entry.product_id),
                    "location_id": str(entry.location_id) if entry.location_id else None,
                }
                for entry in entries
            ],
        },
    )


def reject(session: Session, error: AppError, **audit_kwargs) -> None:
    write_audit(session, **audit_kwargs)
    session.commit()
    raise error
