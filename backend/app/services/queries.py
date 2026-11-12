import uuid
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.tenant import ensure_access, scoped_customer_id
from app.domain.enums import Role, TxType
from app.domain.ledger import compact_location
from app.models.entities import Customer, InventoryTransaction, Location, Product, User
from app.schemas import (
    BalanceRow,
    LocationStockRow,
    MapCell,
    MapRack,
    MapZone,
    PlacementOut,
    RackMapOut,
    SkuFindHit,
    TransactionOut,
)
from app.services.catalog import get_product


def _products(session: Session, customer_id: uuid.UUID | None) -> list[Product]:
    stmt = select(Product).join(Customer)
    if customer_id is not None:
        stmt = stmt.where(Product.customer_id == customer_id)
    return list(session.scalars(stmt).all())


def _physical_pairs(session: Session, customer_id: uuid.UUID | None) -> list[tuple[uuid.UUID, uuid.UUID, int]]:
    stmt = (
        select(
            InventoryTransaction.product_id,
            InventoryTransaction.location_id,
            func.coalesce(func.sum(InventoryTransaction.quantity), 0),
        )
        .where(
            InventoryTransaction.transaction_type != TxType.RESERVED,
            InventoryTransaction.location_id.is_not(None),
        )
        .group_by(InventoryTransaction.product_id, InventoryTransaction.location_id)
    )
    if customer_id is not None:
        stmt = stmt.where(InventoryTransaction.customer_id == customer_id)
    return [(product_id, location_id, int(qty)) for product_id, location_id, qty in session.execute(stmt).all() if int(qty) != 0]


def _reserved_map(session: Session, customer_id: uuid.UUID | None) -> dict[uuid.UUID, int]:
    stmt = (
        select(InventoryTransaction.product_id, func.coalesce(func.sum(InventoryTransaction.quantity), 0))
        .where(InventoryTransaction.transaction_type == TxType.RESERVED)
        .group_by(InventoryTransaction.product_id)
    )
    if customer_id is not None:
        stmt = stmt.where(InventoryTransaction.customer_id == customer_id)
    return {product_id: int(qty) for product_id, qty in session.execute(stmt).all()}


def balance_rows(
    session: Session,
    user: User,
    *,
    customer_id: uuid.UUID | None,
    q: str | None,
    view: str,
    low_stock: bool,
) -> list[BalanceRow]:
    scoped = scoped_customer_id(user, customer_id)
    products = {product.id: product for product in _products(session, scoped)}
    locations = {location.id: location for location in session.scalars(select(Location)).all()}
    reserved = _reserved_map(session, scoped)
    per_location: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = defaultdict(list)
    on_hand: dict[uuid.UUID, int] = defaultdict(int)
    for product_id, location_id, qty in _physical_pairs(session, scoped):
        if product_id not in products:
            continue
        per_location[product_id].append((location_id, qty))
        on_hand[product_id] += qty
    rows: list[BalanceRow] = []
    needle = (q or "").strip().lower()
    for product_id, product in products.items():
        held = on_hand.get(product_id, 0)
        held_reserved = reserved.get(product_id, 0)
        if held == 0 and held_reserved == 0:
            continue
        available = held - held_reserved
        if low_stock and not (product.reorder_point > 0 and available <= product.reorder_point):
            continue
        placements = per_location.get(product_id, [])
        if view == "location" and placements:
            for location_id, qty in sorted(placements, key=lambda pair: locations[pair[0]].location_code):
                location = locations[location_id]
                if needle and needle not in " ".join(
                    [product.sku, product.name, product.barcode, location.location_code]
                ).lower():
                    continue
                rows.append(
                    BalanceRow(
                        customer_id=product.customer_id,
                        customer_name=product.customer.name,
                        product_id=product.id,
                        sku=product.sku,
                        barcode=product.barcode,
                        product_name=product.name,
                        location_id=location.id,
                        location_code=location.location_code,
                        compact_location=compact_location(location.location_code),
                        on_hand_qty=held,
                        reserved_qty=held_reserved,
                        available_qty=available,
                        location_qty=qty,
                    )
                )
            continue
        codes = [locations[location_id].location_code for location_id, _qty in placements if location_id in locations]
        blob = " ".join([product.sku, product.name, product.barcode, *codes]).lower()
        if needle and needle not in blob:
            continue
        rows.append(
            BalanceRow(
                customer_id=product.customer_id,
                customer_name=product.customer.name,
                product_id=product.id,
                sku=product.sku,
                barcode=product.barcode,
                product_name=product.name,
                location_code=", ".join(codes) or None,
                compact_location=compact_location(codes[0]) if len(codes) == 1 else None,
                on_hand_qty=held,
                reserved_qty=held_reserved,
                available_qty=available,
                location_qty=None,
            )
        )
    rows.sort(key=lambda row: (row.customer_name, row.sku, row.location_code or ""))
    return rows


def transaction_rows(
    session: Session,
    user: User,
    *,
    customer_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    tx_type: str | None,
    limit: int,
    offset: int,
) -> list[TransactionOut]:
    scoped = scoped_customer_id(user, customer_id)
    if product_id is not None:
        get_product(session, user, product_id)
    stmt = (
        select(InventoryTransaction, Product, Customer, Location, User)
        .join(Product, Product.id == InventoryTransaction.product_id)
        .join(Customer, Customer.id == InventoryTransaction.customer_id)
        .outerjoin(Location, Location.id == InventoryTransaction.location_id)
        .outerjoin(User, User.id == InventoryTransaction.created_by)
        .order_by(InventoryTransaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if scoped is not None:
        stmt = stmt.where(InventoryTransaction.customer_id == scoped)
    if product_id is not None:
        stmt = stmt.where(InventoryTransaction.product_id == product_id)
    if tx_type:
        stmt = stmt.where(InventoryTransaction.transaction_type == tx_type)
    rows = []
    for tx, product, customer, location, actor in session.execute(stmt).all():
        rows.append(
            TransactionOut(
                id=tx.id,
                created_at=tx.created_at,
                customer_id=customer.id,
                customer_name=customer.name,
                product_id=product.id,
                sku=product.sku,
                product_name=product.name,
                location_code=location.location_code if location else None,
                transaction_type=tx.transaction_type,
                quantity=tx.quantity,
                reference_no=tx.reference_no,
                reference_type=tx.reference_type,
                notes=tx.notes,
                created_by_name=actor.full_name if actor else None,
            )
        )
    return rows


def rack_map(session: Session, user: User, customer_id: uuid.UUID | None) -> RackMapOut:
    scoped = scoped_customer_id(user, customer_id)
    totals: dict[uuid.UUID, int] = defaultdict(int)
    skus: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for product_id, location_id, qty in _physical_pairs(session, scoped):
        if qty > 0:
            totals[location_id] += qty
            skus[location_id].add(product_id)
    zones: dict[str, dict[str, list[MapCell]]] = defaultdict(lambda: defaultdict(list))
    locations = session.scalars(select(Location).order_by(Location.zone, Location.rack, Location.level)).all()
    for location in locations:
        qty = totals.get(location.id, 0)
        if user.role == Role.CUSTOMER and qty <= 0:
            continue
        zones[location.zone][location.rack].append(
            MapCell(
                id=location.id,
                location_code=location.location_code,
                compact_location=compact_location(location.location_code),
                zone=location.zone,
                rack=location.rack,
                level=location.level,
                active=location.active,
                physical_qty=totals.get(location.id, 0),
                sku_count=len(skus.get(location.id, set())),
                photo_file_id=location.photo_file_id,
            )
        )
    return RackMapOut(
        zones=[
            MapZone(
                zone=zone,
                racks=[MapRack(rack=rack, cells=cells) for rack, cells in sorted(racks.items())],
            )
            for zone, racks in sorted(zones.items())
        ]
    )


def location_stock(session: Session, user: User, location_id: uuid.UUID) -> list[LocationStockRow]:
    location = session.get(Location, location_id)
    if location is None:
        from app.core.errors import AppError

        raise AppError("Location not found", 404, "not_found")
    scoped = user.customer_id if user.role == Role.CUSTOMER else None
    products = {product.id: product for product in _products(session, scoped)}
    rows = []
    for product_id, loc_id, qty in _physical_pairs(session, scoped):
        if loc_id != location.id or qty <= 0 or product_id not in products:
            continue
        product = products[product_id]
        rows.append(
            LocationStockRow(
                product_id=product.id,
                customer_id=product.customer_id,
                customer_name=product.customer.name,
                sku=product.sku,
                product_name=product.name,
                barcode=product.barcode,
                physical_qty=qty,
            )
        )
    rows.sort(key=lambda row: row.sku)
    return rows


def find_sku(session: Session, user: User, q: str) -> list[SkuFindHit]:
    scoped = scoped_customer_id(user, None)
    term = q.strip()
    if not term:
        return []
    like = f"%{term}%"
    stmt = select(Product).join(Customer).where(
        or_(Product.sku.ilike(like), Product.barcode.ilike(like), Product.name.ilike(like))
    )
    if scoped is not None:
        stmt = stmt.where(Product.customer_id == scoped)
    products = list(session.scalars(stmt.limit(12)).all())
    products.sort(key=lambda product: (0 if product.sku.lower() == term.lower() or product.barcode.lower() == term.lower() else 1, product.sku))
    reserved = _reserved_map(session, scoped)
    locations = {location.id: location for location in session.scalars(select(Location)).all()}
    by_product: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = defaultdict(list)
    for product_id, location_id, qty in _physical_pairs(session, scoped):
        if qty > 0:
            by_product[product_id].append((location_id, qty))
    hits = []
    for product in products:
        ensure_access(user, product.customer_id)
        placements = []
        held = 0
        for location_id, qty in sorted(by_product.get(product.id, []), key=lambda pair: locations[pair[0]].location_code):
            location = locations[location_id]
            held += qty
            placements.append(
                PlacementOut(
                    location_id=location.id,
                    location_code=location.location_code,
                    compact_location=compact_location(location.location_code),
                    zone=location.zone,
                    rack=location.rack,
                    level=location.level,
                    physical_qty=qty,
                    photo_file_id=location.photo_file_id,
                )
            )
        held_reserved = reserved.get(product.id, 0)
        hits.append(
            SkuFindHit(
                product_id=product.id,
                customer_id=product.customer_id,
                customer_name=product.customer.name,
                sku=product.sku,
                name=product.name,
                barcode=product.barcode,
                on_hand_qty=held,
                reserved_qty=held_reserved,
                available_qty=held - held_reserved,
                placements=placements,
            )
        )
    return hits
