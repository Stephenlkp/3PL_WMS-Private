import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.tenant import ensure_access, require_customer_id, scoped_customer_id
from app.domain.enums import Role, TxType
from app.domain.ledger import LedgerError, compact_location, parse_location_code
from app.models.entities import Customer, InventoryTransaction, Location, Product, RateCard, User
from app.schemas import (
    CustomerIn,
    CustomerOut,
    CustomerPatch,
    LocationIn,
    LocationOut,
    ProductIn,
    ProductOut,
    ProductPatch,
    RateCardIn,
    RateCardOut,
    UserCreate,
    UserOut,
)
from app.services.audit import write_audit
from app.core.security import hash_password, validate_password_strength


def _clean_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@") or " " in value:
        raise AppError("Enter a valid email", 400, "invalid_email")
    return value


def normalize_sku(sku: str) -> str:
    cleaned = "".join(ch for ch in sku.strip().upper() if ch.isalnum() or ch in "-_")
    if not cleaned:
        raise AppError("SKU is required", 400, "invalid_sku")
    return cleaned[:64]


def normalize_barcode(value: str) -> str:
    cleaned = "".join(ch for ch in value.strip().upper() if ch.isalnum() or ch == "-")
    if not cleaned:
        raise AppError("Barcode is empty", 400, "invalid_barcode")
    return cleaned[:48]


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        customer_id=user.customer_id,
        customer_name=user.customer.name if user.customer else None,
        active=user.active,
    )


def customer_out(customer: Customer) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        code=customer.code,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        active=customer.active,
        created_at=customer.created_at,
    )


def product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        customer_id=product.customer_id,
        customer_name=product.customer.name,
        sku=product.sku,
        barcode=product.barcode,
        model=product.model,
        name=product.name,
        description=product.description,
        length_cm=product.length_cm,
        width_cm=product.width_cm,
        height_cm=product.height_cm,
        weight_kg=product.weight_kg,
        reorder_point=product.reorder_point,
        active=product.active,
    )


def location_out(location: Location) -> LocationOut:
    return LocationOut(
        id=location.id,
        location_code=location.location_code,
        compact_location=compact_location(location.location_code),
        zone=location.zone,
        rack=location.rack,
        level=location.level,
        active=location.active,
        photo_file_id=location.photo_file_id,
    )


def create_user(session: Session, actor: User, payload: UserCreate, ip: str | None) -> User:
    email = _clean_email(payload.email)
    validate_password_strength(payload.password)
    if session.scalar(select(User).where(User.email == email)):
        raise AppError("A user with that email already exists", 409, "duplicate_email")
    if payload.role == Role.CUSTOMER:
        if payload.customer_id is None:
            raise AppError("Customer users must belong to a customer", 400, "customer_required")
        customer = session.get(Customer, payload.customer_id)
        if customer is None:
            raise AppError("Customer not found", 404, "not_found")
        customer_id = customer.id
    else:
        if payload.customer_id is not None:
            raise AppError("Warehouse roles are not tied to a customer", 400, "customer_forbidden")
        customer_id = None
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role.value,
        customer_id=customer_id,
        active=True,
    )
    session.add(user)
    session.flush()
    write_audit(
        session,
        user=actor,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        ip=ip,
        customer_id=customer_id,
        new={"email": email, "role": user.role},
    )
    return user


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.full_name)).all())


def create_customer(session: Session, actor: User, payload: CustomerIn, ip: str | None) -> Customer:
    code = "".join(ch for ch in payload.code.upper() if ch.isalnum())
    if len(code) < 2:
        raise AppError("Customer code must be at least 2 letters or digits", 400, "invalid_code")
    if session.scalar(select(Customer).where(Customer.code == code)):
        raise AppError("Customer code already exists", 409, "duplicate_code")
    customer = Customer(
        code=code,
        name=payload.name.strip(),
        email=_clean_email(payload.email) if payload.email else None,
        phone=payload.phone,
        active=True,
    )
    session.add(customer)
    session.flush()
    write_audit(
        session,
        user=actor,
        action="customer.create",
        entity_type="customer",
        entity_id=customer.id,
        ip=ip,
        customer_id=customer.id,
        new={"code": code, "name": customer.name},
    )
    return customer


def update_customer(session: Session, actor: User, customer_id: uuid.UUID, payload: CustomerPatch, ip: str | None) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise AppError("Customer not found", 404, "not_found")
    ensure_access(actor, customer.id)
    old = {"name": customer.name, "active": customer.active}
    if payload.name is not None:
        customer.name = payload.name.strip()
    if payload.email is not None:
        customer.email = _clean_email(payload.email) if payload.email else None
    if payload.phone is not None:
        customer.phone = payload.phone
    if payload.active is not None:
        if actor.role == Role.CUSTOMER:
            raise AppError("Forbidden", 403, "forbidden")
        customer.active = payload.active
    write_audit(
        session,
        user=actor,
        action="customer.update",
        entity_type="customer",
        entity_id=customer.id,
        ip=ip,
        customer_id=customer.id,
        old=old,
        new={"name": customer.name, "active": customer.active},
    )
    return customer


def list_customers(session: Session, user: User) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.name)
    if user.role == Role.CUSTOMER:
        stmt = stmt.where(Customer.id == user.customer_id)
    return list(session.scalars(stmt).all())


def get_customer(session: Session, user: User, customer_id: uuid.UUID) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise AppError("Customer not found", 404, "not_found")
    ensure_access(user, customer.id)
    return customer


def upsert_rate_card(session: Session, actor: User, customer_id: uuid.UUID, payload: RateCardIn, ip: str | None) -> RateCard:
    customer = get_customer(session, actor, customer_id)
    if actor.role == Role.CUSTOMER:
        raise AppError("Forbidden", 403, "forbidden")
    card = session.scalar(select(RateCard).where(RateCard.customer_id == customer.id))
    if card is None:
        card = RateCard(customer_id=customer.id)
        session.add(card)
    card.currency = payload.currency.upper()
    card.storage_fee_per_unit_day = payload.storage_fee_per_unit_day
    card.inbound_fee_per_unit = payload.inbound_fee_per_unit
    card.pick_pack_fee_per_order = payload.pick_pack_fee_per_order
    card.pick_pack_fee_per_unit = payload.pick_pack_fee_per_unit
    session.flush()
    write_audit(
        session,
        user=actor,
        action="rate_card.update",
        entity_type="rate_card",
        entity_id=card.id,
        ip=ip,
        customer_id=customer.id,
        new={"currency": card.currency},
    )
    return card


def rate_card_out(card: RateCard) -> RateCardOut:
    return RateCardOut(
        customer_id=card.customer_id,
        currency=card.currency,
        storage_fee_per_unit_day=card.storage_fee_per_unit_day,
        inbound_fee_per_unit=card.inbound_fee_per_unit,
        pick_pack_fee_per_order=card.pick_pack_fee_per_order,
        pick_pack_fee_per_unit=card.pick_pack_fee_per_unit,
    )


def _unique_barcode(session: Session, customer_code: str, sku: str, requested: str | None) -> str:
    if requested:
        barcode = normalize_barcode(requested)
        if session.scalar(select(Product.id).where(Product.barcode == barcode)):
            raise AppError("Barcode already exists", 409, "duplicate_barcode")
        return barcode
    base = normalize_barcode(sku)[:40] or "SKU"
    candidate = base
    while session.scalar(select(Product.id).where(Product.barcode == candidate)):
        candidate = f"{base[:40]}{uuid.uuid4().hex[:4].upper()}"
    return candidate


def create_product(session: Session, actor: User, payload: ProductIn, ip: str | None) -> Product:
    customer_id = require_customer_id(actor, payload.customer_id)
    customer = session.get(Customer, customer_id)
    if customer is None or not customer.active:
        raise AppError("Customer not found", 404, "not_found")
    sku = normalize_sku(payload.sku)
    if session.scalar(select(Product).where(Product.customer_id == customer.id, Product.sku == sku)):
        raise AppError("SKU already exists for this customer", 409, "duplicate_sku")
    product = Product(
        customer_id=customer.id,
        sku=sku,
        barcode=_unique_barcode(session, customer.code, sku, payload.barcode),
        model=payload.model,
        name=payload.name.strip(),
        description=payload.description,
        length_cm=payload.length_cm,
        width_cm=payload.width_cm,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        reorder_point=payload.reorder_point,
        active=True,
    )
    session.add(product)
    session.flush()
    write_audit(
        session,
        user=actor,
        action="product.create",
        entity_type="product",
        entity_id=product.id,
        ip=ip,
        customer_id=customer.id,
        new={"sku": sku, "barcode": product.barcode},
    )
    return product


def update_product(session: Session, actor: User, product_id: uuid.UUID, payload: ProductPatch, ip: str | None) -> Product:
    product = get_product(session, actor, product_id)
    old = {"name": product.name, "barcode": product.barcode, "reorder_point": product.reorder_point, "active": product.active}
    if payload.barcode is not None:
        barcode = normalize_barcode(payload.barcode)
        taken = session.scalar(select(Product.id).where(Product.barcode == barcode, Product.id != product.id))
        if taken is not None:
            raise AppError("That barcode already points at another SKU", 409, "duplicate_barcode")
        product.barcode = barcode
    for field in ("model", "name", "description", "length_cm", "width_cm", "height_cm", "weight_kg", "reorder_point", "active"):
        value = getattr(payload, field)
        if value is not None:
            setattr(product, field, value.strip() if field == "name" else value)
    write_audit(
        session,
        user=actor,
        action="product.update",
        entity_type="product",
        entity_id=product.id,
        ip=ip,
        customer_id=product.customer_id,
        old=old,
        new={"name": product.name, "barcode": product.barcode, "reorder_point": product.reorder_point, "active": product.active},
    )
    return product


def get_product(session: Session, user: User, product_id: uuid.UUID) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise AppError("Product not found", 404, "not_found")
    ensure_access(user, product.customer_id)
    return product


def list_products(session: Session, user: User, customer_id: uuid.UUID | None, q: str | None) -> list[Product]:
    scoped = scoped_customer_id(user, customer_id)
    stmt = select(Product).join(Customer).order_by(Product.sku)
    if scoped is not None:
        stmt = stmt.where(Product.customer_id == scoped)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.sku.ilike(like), Product.name.ilike(like), Product.barcode.ilike(like)))
    return list(session.scalars(stmt).all())


def resolve_product(
    session: Session,
    user: User,
    *,
    product_id: uuid.UUID | None = None,
    barcode: str | None = None,
    sku: str | None = None,
    customer_id: uuid.UUID | None = None,
) -> Product:
    if product_id is not None:
        return get_product(session, user, product_id)
    if barcode:
        normalized = normalize_barcode(barcode)
        product = session.scalar(select(Product).where(Product.barcode == normalized))
        if product is None:
            matches = [
                item
                for item in session.scalars(select(Product).where(Product.sku == normalize_sku(barcode))).all()
                if user.role != Role.CUSTOMER or user.customer_id == item.customer_id
            ]
            if len(matches) > 1:
                raise AppError("More than one SKU uses that code", 409, "ambiguous_sku")
            product = matches[0] if matches else None
        if product is None:
            raise AppError("That code is not a catalog SKU. Add the product before scanning it in.", 404, "unknown_sku")
        ensure_access(user, product.customer_id)
        return product
    if sku:
        scoped = require_customer_id(user, customer_id)
        product = session.scalar(
            select(Product).where(Product.customer_id == scoped, Product.sku == normalize_sku(sku))
        )
        if product is None:
            raise AppError("Product not found", 404, "not_found")
        return product
    raise AppError("Product identifier required", 400, "product_required")


def create_location(session: Session, actor: User, payload: LocationIn, ip: str | None) -> Location:
    try:
        zone, rack, level = parse_location_code(payload.location_code)
    except LedgerError as exc:
        raise AppError(exc.message, 400, exc.code) from exc
    code = f"{zone}-{rack}-{level}"
    if session.scalar(select(Location).where(Location.location_code == code)):
        raise AppError("Location already exists", 409, "duplicate_location")
    location = Location(location_code=code, zone=zone, rack=rack, level=level, active=True)
    session.add(location)
    session.flush()
    write_audit(
        session,
        user=actor,
        action="location.create",
        entity_type="location",
        entity_id=location.id,
        ip=ip,
        new={"location_code": code},
    )
    return location


def location_on_hand(session: Session, location_id: uuid.UUID) -> int:
    qty = session.scalar(
        select(func.coalesce(func.sum(InventoryTransaction.quantity), 0)).where(
            InventoryTransaction.location_id == location_id,
            InventoryTransaction.transaction_type != TxType.RESERVED,
        )
    )
    return int(qty or 0)


def update_location(session: Session, actor: User, location_id: uuid.UUID, active: bool, ip: str | None) -> Location:
    location = session.get(Location, location_id)
    if location is None:
        raise AppError("Location not found", 404, "not_found")
    if not active and location_on_hand(session, location.id) != 0:
        raise AppError("Move the stock out before deactivating this location", 409, "location_has_stock")
    old = location.active
    location.active = active
    write_audit(
        session,
        user=actor,
        action="location.update",
        entity_type="location",
        entity_id=location.id,
        ip=ip,
        old={"active": old},
        new={"active": active},
    )
    return location


def get_location(session: Session, location_id: uuid.UUID | None = None, code: str | None = None) -> Location:
    if location_id is not None:
        location = session.get(Location, location_id)
    elif code:
        try:
            zone, rack, level = parse_location_code(code)
        except LedgerError as exc:
            raise AppError(exc.message, 400, exc.code) from exc
        location = session.scalar(select(Location).where(Location.location_code == f"{zone}-{rack}-{level}"))
    else:
        raise AppError("Location is required", 400, "location_required")
    if location is None:
        raise AppError("Location not found", 404, "not_found")
    return location


def list_locations(session: Session, q: str | None, zone: str | None) -> list[Location]:
    stmt = select(Location).order_by(Location.zone, Location.rack, Location.level)
    if zone:
        stmt = stmt.where(Location.zone == zone.strip().upper())
    if q:
        stmt = stmt.where(Location.location_code.ilike(f"%{q.strip()}%"))
    return list(session.scalars(stmt).all())
