"""Inventory ledger rules.

Stock is never stored as an editable quantity. Every change is a signed
transaction, and balances are projections of those rows.

Sign convention
- INBOUND     quantity > 0 at a location
- OUTBOUND    quantity < 0 at a location
- MOVE        one negative row at the source and one positive row at the destination
- ADJUSTMENT  signed quantity at a location (a ledger posting, not a balance edit)
- RESERVED    signed quantity with no location (pool reservation)

Available = physical stock − reserved.
Physical stock changes only on INBOUND, OUTBOUND, MOVE, and ADJUSTMENT.
A reservation reduces available stock and leaves physical stock untouched.
Shipment posts OUTBOUND and releases the matching reservation together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import TxType


class LedgerError(Exception):
    def __init__(self, message: str, code: str = "ledger_rejected"):
        super().__init__(message)
        self.message = message
        self.code = code


_LOCATION = re.compile(r"^([A-Z]{1,3})-(\d{2})-(\d{2})$")


def parse_location_code(code: str) -> tuple[str, str, str]:
    match = _LOCATION.fullmatch(code.strip().upper())
    if not match:
        raise LedgerError("Location code must look like A-01-01", "invalid_location")
    return match.group(1), match.group(2), match.group(3)


def compact_location(code: str) -> str:
    """A-02-03 becomes A02-03, the rack label pickers read on the floor."""
    zone, rack, level = parse_location_code(code)
    return f"{zone}{rack}-{level}"


def validate_entry(tx_type: TxType, quantity: int, location_id: UUID | None) -> None:
    if quantity == 0:
        raise LedgerError("Quantity cannot be zero", "zero_quantity")
    if tx_type == TxType.INBOUND and quantity <= 0:
        raise LedgerError("Inbound quantity must be positive", "invalid_quantity")
    if tx_type == TxType.OUTBOUND and quantity >= 0:
        raise LedgerError("Outbound quantity must be negative", "invalid_quantity")
    if tx_type == TxType.RESERVED:
        return
    if location_id is None:
        raise LedgerError("A location is required for this transaction", "location_required")


def assert_balances(physical: dict[UUID, int], reserved: int) -> None:
    for qty in physical.values():
        if qty < 0:
            raise LedgerError("Location stock would go negative", "negative_stock")
    if reserved < 0:
        raise LedgerError("Reserved quantity would go negative", "negative_reservation")
    if sum(physical.values()) < reserved:
        raise LedgerError("Available stock would go negative", "insufficient_available")


def apply_entry(
    physical: dict[UUID, int],
    reserved: int,
    tx_type: TxType,
    location_id: UUID | None,
    quantity: int,
    *,
    check: bool = True,
) -> tuple[dict[UUID, int], int]:
    validate_entry(tx_type, quantity, location_id)
    physical = dict(physical)
    if tx_type == TxType.RESERVED:
        reserved += quantity
    else:
        assert location_id is not None
        physical[location_id] = physical.get(location_id, 0) + quantity
        if physical[location_id] == 0:
            del physical[location_id]
    if check:
        assert_balances(physical, reserved)
    return physical, reserved


def available_qty(physical: dict[UUID, int], reserved: int) -> int:
    return sum(physical.values()) - reserved


@dataclass(frozen=True)
class StockPosition:
    location_id: UUID
    location_code: str
    zone: str
    rack: str
    level: str
    free_qty: int


@dataclass(frozen=True)
class Allocation:
    location_id: UUID
    location_code: str
    zone: str
    rack: str
    level: str
    quantity: int


def route_sort_key(zone: str, rack: str, level: str, code: str) -> tuple[str, str, str, str]:
    """Same zone first, then nearest rack, then level."""
    return (zone, rack, level, code)


def allocate(stocks: list[StockPosition], quantity: int) -> list[Allocation]:
    if quantity <= 0:
        raise LedgerError("Pick quantity must be positive", "invalid_quantity")
    remaining = quantity
    plan: list[Allocation] = []
    ordered = sorted(stocks, key=lambda s: route_sort_key(s.zone, s.rack, s.level, s.location_code))
    for stock in ordered:
        if stock.free_qty <= 0 or remaining <= 0:
            continue
        take = min(stock.free_qty, remaining)
        plan.append(
            Allocation(
                location_id=stock.location_id,
                location_code=stock.location_code,
                zone=stock.zone,
                rack=stock.rack,
                level=stock.level,
                quantity=take,
            )
        )
        remaining -= take
    if remaining:
        raise LedgerError("Not enough stock in locations to build a pick", "insufficient_stock")
    return plan


def age_bucket(days: int) -> str:
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"
