import uuid

import pytest

from app.domain.ledger import (
    Allocation,
    LedgerError,
    StockPosition,
    allocate,
    apply_entry,
    available_qty,
    compact_location,
    parse_location_code,
)
from app.domain.enums import TxType
from app.core.config import Settings, assert_production_safe


def test_location_code_and_compact_rack_label():
    assert parse_location_code("a-02-03") == ("A", "02", "03")
    assert compact_location("A-02-03") == "A02-03"
    with pytest.raises(LedgerError):
        parse_location_code("A-2-3")


def test_available_is_physical_minus_reserved():
    loc = uuid.uuid4()
    physical: dict = {}
    reserved = 0
    physical, reserved = apply_entry(physical, reserved, TxType.INBOUND, loc, 10)
    assert available_qty(physical, reserved) == 10
    physical, reserved = apply_entry(physical, reserved, TxType.RESERVED, None, 4)
    assert sum(physical.values()) == 10
    assert reserved == 4
    assert available_qty(physical, reserved) == 6
    physical, reserved = apply_entry(physical, reserved, TxType.RESERVED, None, -4)
    physical, reserved = apply_entry(physical, reserved, TxType.OUTBOUND, loc, -4)
    assert sum(physical.values()) == 6
    assert reserved == 0
    assert available_qty(physical, reserved) == 6


def test_cannot_reserve_more_than_physical_stock():
    loc = uuid.uuid4()
    physical, reserved = apply_entry({}, 0, TxType.INBOUND, loc, 3)
    with pytest.raises(LedgerError):
        apply_entry(physical, reserved, TxType.RESERVED, None, 4)


def test_shipping_releases_reservation_before_outbound_check():
    loc = uuid.uuid4()
    other = uuid.uuid4()
    physical, reserved = apply_entry({}, 0, TxType.INBOUND, loc, 10)
    physical, reserved = apply_entry(physical, reserved, TxType.RESERVED, None, 8)
    physical, reserved = apply_entry(physical, reserved, TxType.RESERVED, None, -5)
    physical, reserved = apply_entry(physical, reserved, TxType.OUTBOUND, loc, -5)
    assert sum(physical.values()) == 5
    assert reserved == 3
    with pytest.raises(LedgerError):
        apply_entry(physical, reserved, TxType.MOVE, other, -1)


def test_pick_route_takes_the_same_zone_before_the_next_zone():
    a1 = uuid.uuid4()
    a2 = uuid.uuid4()
    b1 = uuid.uuid4()
    stocks = [
        StockPosition(b1, "B-01-01", "B", "01", "01", 9),
        StockPosition(a2, "A-02-01", "A", "02", "01", 5),
        StockPosition(a1, "A-01-01", "A", "01", "01", 3),
    ]
    plan = allocate(stocks, 7)
    assert plan == [
        Allocation(a1, "A-01-01", "A", "01", "01", 3),
        Allocation(a2, "A-02-01", "A", "02", "01", 4),
    ]


def test_production_refuses_the_dev_secret():
    with pytest.raises(RuntimeError):
        assert_production_safe(Settings(ENV="production", JWT_SECRET="dev-only-change-me", STORAGE_BACKEND="local"))
