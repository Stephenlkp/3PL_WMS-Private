import uuid

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, require_roles
from app.core.database import get_db
from app.core.limiter import limiter
from app.domain.enums import MANAGER_ROLES, STAFF_ROLES, Role
from app.models.entities import AuditLog, User
from app.schemas import (
    AdjustIn,
    AuditOut,
    CustomerDashboard,
    CustomerIn,
    CustomerOut,
    CustomerPatch,
    DispatchIn,
    FileOut,
    LocationIn,
    LocationOut,
    LocationPatch,
    LocationStockRow,
    LoginIn,
    LogoutIn,
    MoveIn,
    OrderCreate,
    OrderOut,
    PasswordChangeIn,
    PickCreate,
    PickListOut,
    PostingOut,
    ProductIn,
    ProductOut,
    ProductPatch,
    RackMapOut,
    RateCardIn,
    RateCardOut,
    ReceiveIn,
    RefreshIn,
    ScanIn,
    SearchOut,
    ShipmentOut,
    SkuFindHit,
    TokenOut,
    UserCreate,
    UserOut,
    WarehouseDashboard,
    BalanceRow,
    TransactionOut,
)
from app.services import catalog, files, fulfillment, identity, queries, reports, search, stock
from app.services.barcode_img import render_label
from app.services.catalog import customer_out, location_out, product_out, rate_card_out, user_out
from app.services.fulfillment import order_out, picklist_out, shipment_out

router = APIRouter(prefix="/api/v1")
managers = require_roles(*MANAGER_ROLES)
staff = require_roles(*STAFF_ROLES)
pickers = require_roles(Role.ADMIN, Role.SUPERVISOR, Role.PICKER)
packers = require_roles(Role.ADMIN, Role.SUPERVISOR, Role.PACKER)
order_writers = require_roles(Role.ADMIN, Role.SUPERVISOR, Role.CUSTOMER)
catalog_writers = require_roles(Role.ADMIN, Role.SUPERVISOR, Role.CUSTOMER)


@router.post("/auth/login", response_model=TokenOut, tags=["auth"])
@limiter.limit("10/minute")
def login(request: Request, payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    # slowapi writes rate-limit headers onto this Response. Returning the token body is unchanged.
    return identity.login(db, payload.email, payload.password, client_ip(request), request.headers.get("user-agent"))


@router.post("/auth/refresh", response_model=TokenOut, tags=["auth"])
def refresh(payload: RefreshIn, request: Request, db: Session = Depends(get_db)):
    return identity.rotate_refresh(db, payload.refresh_token, client_ip(request), request.headers.get("user-agent"))


@router.post("/auth/logout", tags=["auth"])
def logout(payload: LogoutIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    identity.logout(db, user, payload.refresh_token, client_ip(request))
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.post("/auth/change-password", tags=["auth"])
def change_password(payload: PasswordChangeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    identity.change_password(db, user, payload.current_password, payload.new_password, client_ip(request))
    return {"ok": True}


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(user: User = Depends(managers), db: Session = Depends(get_db)):
    return [user_out(row) for row in catalog.list_users(db)]


@router.post("/users", response_model=UserOut, status_code=201, tags=["users"])
def create_user(payload: UserCreate, request: Request, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return user_out(catalog.create_user(db, user, payload, client_ip(request)))


@router.get("/customers", response_model=list[CustomerOut], tags=["customers"])
def list_customers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [customer_out(row) for row in catalog.list_customers(db, user)]


@router.post("/customers", response_model=CustomerOut, status_code=201, tags=["customers"])
def create_customer(payload: CustomerIn, request: Request, user: User = Depends(managers), db: Session = Depends(get_db)):
    return customer_out(catalog.create_customer(db, user, payload, client_ip(request)))


@router.get("/customers/{customer_id}", response_model=CustomerOut, tags=["customers"])
def get_customer(customer_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return customer_out(catalog.get_customer(db, user, customer_id))


@router.patch("/customers/{customer_id}", response_model=CustomerOut, tags=["customers"])
def patch_customer(
    customer_id: uuid.UUID,
    payload: CustomerPatch,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return customer_out(catalog.update_customer(db, user, customer_id, payload, client_ip(request)))


@router.get("/customers/{customer_id}/rate-card", response_model=RateCardOut, tags=["customers"])
def get_rate_card(customer_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    customer = catalog.get_customer(db, user, customer_id)
    from app.models.entities import RateCard

    card = db.scalar(select(RateCard).where(RateCard.customer_id == customer.id))
    if card is None:
        from app.core.errors import AppError

        raise AppError("No rate card yet", 404, "not_found")
    return rate_card_out(card)


@router.put("/customers/{customer_id}/rate-card", response_model=RateCardOut, tags=["customers"])
def put_rate_card(
    customer_id: uuid.UUID,
    payload: RateCardIn,
    request: Request,
    user: User = Depends(managers),
    db: Session = Depends(get_db),
):
    return rate_card_out(catalog.upsert_rate_card(db, user, customer_id, payload, client_ip(request)))


@router.get("/products", response_model=list[ProductOut], tags=["products"])
def list_products(
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [product_out(row) for row in catalog.list_products(db, user, customer_id, q)]


@router.post("/products", response_model=ProductOut, status_code=201, tags=["products"])
def create_product(payload: ProductIn, request: Request, user: User = Depends(catalog_writers), db: Session = Depends(get_db)):
    return product_out(catalog.create_product(db, user, payload, client_ip(request)))


@router.get("/products/lookup", response_model=ProductOut, tags=["products"])
def lookup_product(
    code: str = Query(min_length=1, max_length=64),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return product_out(catalog.resolve_product(db, user, barcode=code))


@router.get("/products/{product_id}", response_model=ProductOut, tags=["products"])
def get_product(product_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return product_out(catalog.get_product(db, user, product_id))


@router.patch("/products/{product_id}", response_model=ProductOut, tags=["products"])
def patch_product(
    product_id: uuid.UUID,
    payload: ProductPatch,
    request: Request,
    user: User = Depends(catalog_writers),
    db: Session = Depends(get_db),
):
    return product_out(catalog.update_product(db, user, product_id, payload, client_ip(request)))


@router.get("/products/{product_id}/barcode", tags=["products"])
def product_barcode(
    product_id: uuid.UUID,
    style: str = Query(default="code128", pattern="^(code128|qr)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = catalog.get_product(db, user, product_id)
    png = render_label(product.barcode, style)
    return Response(content=png, media_type="image/png", headers={"Content-Disposition": f'inline; filename="{product.sku}.png"'})


@router.get("/locations", response_model=list[LocationOut], tags=["locations"])
def list_locations(q: str | None = None, zone: str | None = None, _: User = Depends(staff), db: Session = Depends(get_db)):
    return [location_out(row) for row in catalog.list_locations(db, q, zone)]


@router.post("/locations", response_model=LocationOut, status_code=201, tags=["locations"])
def create_location(payload: LocationIn, request: Request, user: User = Depends(managers), db: Session = Depends(get_db)):
    return location_out(catalog.create_location(db, user, payload, client_ip(request)))


@router.patch("/locations/{location_id}", response_model=LocationOut, tags=["locations"])
def patch_location(
    location_id: uuid.UUID,
    payload: LocationPatch,
    request: Request,
    user: User = Depends(managers),
    db: Session = Depends(get_db),
):
    return location_out(catalog.update_location(db, user, location_id, payload.active, client_ip(request)))


@router.get("/locations/map", response_model=RackMapOut, tags=["locations"])
def location_map(customer_id: uuid.UUID | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return queries.rack_map(db, user, customer_id)


@router.get("/locations/find-sku", response_model=list[SkuFindHit], tags=["locations"])
def find_sku(q: str = Query(min_length=1, max_length=80), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return queries.find_sku(db, user, q)


@router.get("/locations/{location_id}/stock", response_model=list[LocationStockRow], tags=["locations"])
def location_contents(location_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return queries.location_stock(db, user, location_id)


@router.get("/locations/{location_id}/barcode", tags=["locations"])
def location_barcode(
    location_id: uuid.UUID,
    style: str = Query(default="qr", pattern="^(code128|qr)$"),
    _: User = Depends(staff),
    db: Session = Depends(get_db),
):
    location = catalog.get_location(db, location_id, None)
    png = render_label(location.location_code, style)
    return Response(content=png, media_type="image/png")


@router.post("/locations/{location_id}/photo", response_model=LocationOut, tags=["locations"])
def location_photo(
    location_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(managers),
    db: Session = Depends(get_db),
):
    location = catalog.get_location(db, location_id, None)
    stored = files.store_bytes(
        db,
        user,
        filename=file.filename or "rack.jpg",
        declared_type=file.content_type,
        data=file.file.read(10 * 1024 * 1024 + 1),
        customer_id=None,
        ip=client_ip(request),
    )
    if not stored.content_type.startswith("image/"):
        from app.core.errors import AppError

        raise AppError("Rack photos must be JPEG or PNG", 400, "unsupported_file")
    location.photo_file_id = stored.id
    return location_out(location)


@router.get("/inventory/balances", response_model=list[BalanceRow], tags=["inventory"])
def balances(
    customer_id: uuid.UUID | None = None,
    q: str | None = None,
    view: str = Query(default="sku", pattern="^(sku|location)$"),
    low_stock: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return queries.balance_rows(db, user, customer_id=customer_id, q=q, view=view, low_stock=low_stock)


@router.get("/inventory/transactions", response_model=list[TransactionOut], tags=["inventory"])
def transactions(
    customer_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    tx_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return queries.transaction_rows(
        db, user, customer_id=customer_id, product_id=product_id, tx_type=tx_type, limit=limit, offset=offset
    )


@router.post("/inventory/receive", response_model=PostingOut, tags=["inventory"])
def receive(payload: ReceiveIn, request: Request, user: User = Depends(pickers), db: Session = Depends(get_db)):
    return stock.receive(db, user, payload, client_ip(request))


@router.post("/inventory/move", response_model=PostingOut, tags=["inventory"])
def move(payload: MoveIn, request: Request, user: User = Depends(managers), db: Session = Depends(get_db)):
    return stock.move_stock(db, user, payload, client_ip(request))


@router.post("/inventory/adjust", response_model=PostingOut, tags=["inventory"])
def adjust(payload: AdjustIn, request: Request, user: User = Depends(managers), db: Session = Depends(get_db)):
    return stock.adjust_stock(db, user, payload, client_ip(request))


@router.get("/orders", response_model=list[OrderOut], tags=["orders"])
def list_orders(
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [order_out(row) for row in fulfillment.list_orders(db, user, status, customer_id)]


@router.post("/orders", response_model=OrderOut, status_code=201, tags=["orders"])
def create_order(payload: OrderCreate, request: Request, user: User = Depends(order_writers), db: Session = Depends(get_db)):
    return order_out(fulfillment.create_order(db, user, payload, client_ip(request)))


@router.get("/orders/{order_id}", response_model=OrderOut, tags=["orders"])
def get_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return order_out(fulfillment.get_order(db, user, order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderOut, tags=["orders"])
def cancel_order(order_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {Role.ADMIN, Role.SUPERVISOR, Role.CUSTOMER}:
        from app.core.errors import AppError

        raise AppError("Forbidden", 403, "forbidden")
    return order_out(fulfillment.cancel_order(db, user, order_id, client_ip(request)))


@router.post("/orders/{order_id}/airway-bill", response_model=OrderOut, tags=["orders"])
def upload_airway_bill(
    order_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(order_writers),
    db: Session = Depends(get_db),
):
    order = fulfillment.get_order(db, user, order_id)
    stored = files.store_bytes(
        db,
        user,
        filename=file.filename or "airwaybill",
        declared_type=file.content_type,
        data=file.file.read(10 * 1024 * 1024 + 1),
        customer_id=order.customer_id,
        ip=client_ip(request),
    )
    return order_out(fulfillment.attach_airway_bill(db, user, order_id, stored, client_ip(request)))


@router.post("/orders/{order_id}/picklist", response_model=PickListOut, tags=["picklists"])
def generate_picklist(order_id: uuid.UUID, request: Request, user: User = Depends(pickers), db: Session = Depends(get_db)):
    return picklist_out(fulfillment.generate_picklist(db, user, order_id, client_ip(request)))


@router.get("/picklists", response_model=list[PickListOut], tags=["picklists"])
def list_picklists(status: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [picklist_out(row) for row in fulfillment.list_picklists(db, user, status)]


@router.post("/picklists", response_model=PickListOut, tags=["picklists"])
def create_picklist(payload: PickCreate, request: Request, user: User = Depends(pickers), db: Session = Depends(get_db)):
    return picklist_out(fulfillment.generate_picklist(db, user, payload.order_id, client_ip(request)))


@router.get("/picklists/{picklist_id}", response_model=PickListOut, tags=["picklists"])
def get_picklist(picklist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return picklist_out(fulfillment.get_picklist(db, user, picklist_id))


@router.post("/picklists/{picklist_id}/scan", response_model=PickListOut, tags=["picklists"])
def scan_pick(
    picklist_id: uuid.UUID,
    payload: ScanIn,
    request: Request,
    user: User = Depends(pickers),
    db: Session = Depends(get_db),
):
    return picklist_out(fulfillment.scan_pick(db, user, picklist_id, payload.barcode, payload.quantity, client_ip(request)))


@router.post("/picklists/{picklist_id}/complete", response_model=PickListOut, tags=["picklists"])
def complete_pick(picklist_id: uuid.UUID, request: Request, user: User = Depends(pickers), db: Session = Depends(get_db)):
    return picklist_out(fulfillment.complete_pick(db, user, picklist_id, client_ip(request)))


@router.post("/orders/{order_id}/pack-scan", response_model=OrderOut, tags=["shipments"])
def pack_scan(
    order_id: uuid.UUID,
    payload: ScanIn,
    request: Request,
    user: User = Depends(packers),
    db: Session = Depends(get_db),
):
    return order_out(fulfillment.scan_pack(db, user, order_id, payload.barcode, payload.quantity, client_ip(request)))


@router.post("/orders/{order_id}/pack-complete", response_model=ShipmentOut, tags=["shipments"])
def pack_complete(order_id: uuid.UUID, request: Request, user: User = Depends(packers), db: Session = Depends(get_db)):
    return shipment_out(fulfillment.complete_pack(db, user, order_id, client_ip(request)))


@router.get("/shipments", response_model=list[ShipmentOut], tags=["shipments"])
def list_shipments(
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [shipment_out(row) for row in fulfillment.list_shipments(db, user, status, customer_id)]


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut, tags=["shipments"])
def get_shipment(shipment_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return shipment_out(fulfillment.get_shipment(db, user, shipment_id))


@router.post("/shipments/{shipment_id}/dispatch", response_model=ShipmentOut, tags=["shipments"])
def dispatch_shipment(
    shipment_id: uuid.UUID,
    payload: DispatchIn,
    request: Request,
    user: User = Depends(packers),
    db: Session = Depends(get_db),
):
    return shipment_out(fulfillment.dispatch(db, user, shipment_id, payload, client_ip(request)))


@router.post("/files", response_model=FileOut, tags=["files"])
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    customer_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.core.tenant import require_customer_id

    scoped = require_customer_id(user, customer_id)
    stored = files.store_bytes(
        db,
        user,
        filename=file.filename or "upload",
        declared_type=file.content_type,
        data=file.file.read(10 * 1024 * 1024 + 1),
        customer_id=scoped,
        ip=client_ip(request),
    )
    return FileOut(
        id=stored.id,
        customer_id=stored.customer_id,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        created_at=stored.created_at,
    )


@router.get("/files/{file_id}", response_model=FileOut, tags=["files"])
def file_meta(file_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stored, _data = files.read_file(db, user, file_id)
    return FileOut(
        id=stored.id,
        customer_id=stored.customer_id,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        created_at=stored.created_at,
    )


@router.get("/files/{file_id}/content", tags=["files"])
def file_content(
    file_id: uuid.UUID,
    download: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stored, data = files.read_file(db, user, file_id)
    disposition = "attachment" if download else "inline"
    return Response(
        content=data,
        media_type=stored.content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{stored.filename}"'},
    )


@router.get("/search", response_model=SearchOut, tags=["search"])
def search_all(q: str = Query(min_length=1, max_length=80), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return search.search(db, user, q)


def _maybe_export(title: str, rows: list[dict], fmt: str | None):
    if fmt:
        return reports.export_table(title, rows, fmt)
    return rows


@router.get("/reports/warehouse-dashboard", response_model=WarehouseDashboard, tags=["reports"])
def warehouse_dashboard(_: User = Depends(staff), db: Session = Depends(get_db)):
    return reports.warehouse_dashboard(db)


@router.get("/reports/customer-dashboard", response_model=CustomerDashboard, tags=["reports"])
def customer_dashboard(user: User = Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return reports.customer_dashboard(db, user)


@router.get("/reports/inventory", tags=["reports"])
def inventory_report(
    customer_id: uuid.UUID | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _maybe_export("inventory-report", reports.inventory_dicts(db, user, customer_id), format)


@router.get("/reports/aging", tags=["reports"])
def aging_report(
    customer_id: uuid.UUID | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _maybe_export("stock-aging", reports.aging_rows(db, user, customer_id), format)


@router.get("/reports/movements", tags=["reports"])
def movement_report(
    customer_id: uuid.UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = _dates(date_from, date_to)
    return _maybe_export("inventory-movements", reports.movement_dicts(db, user, customer_id, start, end), format)


@router.get("/reports/fulfillment", tags=["reports"])
def fulfillment_report(
    customer_id: uuid.UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = _dates(date_from, date_to)
    return _maybe_export("order-fulfillment", reports.fulfillment_rows(db, user, customer_id, start, end), format)


@router.get("/reports/shipments", tags=["reports"])
def shipment_report(
    customer_id: uuid.UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end = _dates(date_from, date_to)
    return _maybe_export("shipments", reports.shipment_rows(db, user, customer_id, start, end), format)


@router.get("/reports/billing", tags=["reports"])
def billing_report(
    customer_id: uuid.UUID | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    format: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in {Role.ADMIN, Role.SUPERVISOR, Role.CUSTOMER}:
        from app.core.errors import AppError

        raise AppError("Forbidden", 403, "forbidden")
    start, end = _dates(date_from, date_to)
    report = reports.billing_report(db, user, customer_id, start, end)
    if not format:
        return report
    rows = [line.model_dump() for line in report.lines]
    rows.append({"description": "Total", "quantity": "", "rate": report.currency, "amount": report.total})
    return reports.export_table("customer-billing", rows, format)


@router.get("/audit", response_model=list[AuditOut], tags=["audit"])
def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role not in {Role.ADMIN, Role.SUPERVISOR, Role.CUSTOMER}:
        from app.core.errors import AppError

        raise AppError("Forbidden", 403, "forbidden")
    stmt = select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id).order_by(AuditLog.created_at.desc())
    if user.role == Role.CUSTOMER:
        stmt = stmt.where(AuditLog.customer_id == user.customer_id)
    stmt = stmt.limit(limit).offset(offset)
    rows = []
    for entry, actor in db.execute(stmt).all():
        rows.append(
            AuditOut(
                id=entry.id,
                created_at=entry.created_at,
                user_id=entry.user_id,
                user_email=actor.email if actor else None,
                customer_id=entry.customer_id,
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                ip=entry.ip,
                old_value=entry.old_value,
                new_value=entry.new_value,
            )
        )
    return rows


def _dates(date_from: str | None, date_to: str | None):
    from datetime import date

    from app.core.errors import AppError

    try:
        start = date.fromisoformat(date_from) if date_from else None
        end = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise AppError("Dates must be YYYY-MM-DD", 400, "invalid_date") from exc
    return start, end
