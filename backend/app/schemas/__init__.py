import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Role


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    customer_id: uuid.UUID | None
    customer_name: str | None
    active: bool


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class LoginIn(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class RefreshIn(APIModel):
    refresh_token: str


class LogoutIn(APIModel):
    refresh_token: str | None = None


class PasswordChangeIn(APIModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class UserCreate(APIModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=160)
    role: Role
    customer_id: uuid.UUID | None = None


class CustomerIn(APIModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)


class CustomerPatch(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: str | None = None
    phone: str | None = None
    active: bool | None = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    email: str | None
    phone: str | None
    active: bool
    created_at: datetime


class RateCardIn(APIModel):
    currency: str = Field(default="USD", min_length=3, max_length=8)
    storage_fee_per_unit_day: Decimal = Field(default=Decimal("0"), ge=0)
    inbound_fee_per_unit: Decimal = Field(default=Decimal("0"), ge=0)
    pick_pack_fee_per_order: Decimal = Field(default=Decimal("0"), ge=0)
    pick_pack_fee_per_unit: Decimal = Field(default=Decimal("0"), ge=0)


class RateCardOut(BaseModel):
    customer_id: uuid.UUID
    currency: str
    storage_fee_per_unit_day: Decimal
    inbound_fee_per_unit: Decimal
    pick_pack_fee_per_order: Decimal
    pick_pack_fee_per_unit: Decimal


class ProductIn(APIModel):
    customer_id: uuid.UUID | None = None
    sku: str = Field(min_length=1, max_length=64)
    barcode: str | None = Field(default=None, max_length=48)
    model: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    length_cm: Decimal | None = Field(default=None, ge=0)
    width_cm: Decimal | None = Field(default=None, ge=0)
    height_cm: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    reorder_point: int = Field(default=0, ge=0)


class ProductPatch(APIModel):
    barcode: str | None = Field(default=None, min_length=1, max_length=48)
    model: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    length_cm: Decimal | None = Field(default=None, ge=0)
    width_cm: Decimal | None = Field(default=None, ge=0)
    height_cm: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    active: bool | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    sku: str
    barcode: str
    model: str | None
    name: str
    description: str | None
    length_cm: Decimal | None
    width_cm: Decimal | None
    height_cm: Decimal | None
    weight_kg: Decimal | None
    reorder_point: int
    active: bool


class LocationIn(APIModel):
    location_code: str = Field(min_length=4, max_length=16)


class LocationPatch(APIModel):
    active: bool


class LocationOut(BaseModel):
    id: uuid.UUID
    location_code: str
    compact_location: str
    zone: str
    rack: str
    level: str
    active: bool
    photo_file_id: uuid.UUID | None


class MapCell(BaseModel):
    id: uuid.UUID
    location_code: str
    compact_location: str
    zone: str
    rack: str
    level: str
    active: bool
    physical_qty: int
    sku_count: int
    photo_file_id: uuid.UUID | None


class MapRack(BaseModel):
    rack: str
    cells: list[MapCell]


class MapZone(BaseModel):
    zone: str
    racks: list[MapRack]


class RackMapOut(BaseModel):
    zones: list[MapZone]


class LocationStockRow(BaseModel):
    product_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    sku: str
    product_name: str
    barcode: str
    physical_qty: int


class PlacementOut(BaseModel):
    location_id: uuid.UUID
    location_code: str
    compact_location: str
    zone: str
    rack: str
    level: str
    physical_qty: int
    photo_file_id: uuid.UUID | None


class SkuFindHit(BaseModel):
    product_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    sku: str
    name: str
    barcode: str
    on_hand_qty: int
    reserved_qty: int
    available_qty: int
    placements: list[PlacementOut]


class ReceiveLine(APIModel):
    barcode: str | None = None
    product_id: uuid.UUID | None = None
    quantity: int = Field(gt=0, le=100000)


class ReceiveIn(APIModel):
    customer_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    location_code: str | None = None
    notes: str | None = Field(default=None, max_length=500)
    lines: list[ReceiveLine] = Field(min_length=1, max_length=100)


class MoveIn(APIModel):
    barcode: str | None = None
    product_id: uuid.UUID | None = None
    from_location_id: uuid.UUID | None = None
    to_location_id: uuid.UUID | None = None
    from_location_code: str | None = None
    to_location_code: str | None = None
    quantity: int = Field(gt=0, le=100000)
    notes: str | None = Field(default=None, max_length=500)


class AdjustIn(APIModel):
    product_id: uuid.UUID
    location_id: uuid.UUID
    quantity: int = Field(ge=-100000, le=100000)
    notes: str = Field(min_length=3, max_length=500)


class PostingOut(BaseModel):
    reference_no: str
    product_id: uuid.UUID
    sku: str
    on_hand_qty: int
    reserved_qty: int
    available_qty: int


class BalanceRow(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    product_id: uuid.UUID
    sku: str
    barcode: str
    product_name: str
    location_id: uuid.UUID | None = None
    location_code: str | None = None
    compact_location: str | None = None
    on_hand_qty: int
    reserved_qty: int
    available_qty: int
    location_qty: int | None = None


class TransactionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    customer_id: uuid.UUID
    customer_name: str
    product_id: uuid.UUID
    sku: str
    product_name: str
    location_code: str | None
    transaction_type: str
    quantity: int
    reference_no: str
    reference_type: str | None
    notes: str | None
    created_by_name: str | None


class OrderItemIn(APIModel):
    product_id: uuid.UUID | None = None
    sku: str | None = None
    quantity: int = Field(gt=0, le=100000)


class OrderCreate(APIModel):
    customer_id: uuid.UUID | None = None
    receiver_name: str = Field(min_length=1, max_length=160)
    receiver_phone: str = Field(min_length=3, max_length=40)
    receiver_address: str = Field(min_length=3, max_length=500)
    courier: str = Field(min_length=1, max_length=80)
    tracking_number: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=40)
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)


class OrderItemOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    sku: str
    barcode: str
    product_name: str
    quantity: int
    picked_qty: int
    packed_qty: int


class OrderOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    order_number: str
    status: str
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    courier: str
    tracking_number: str | None
    notes: str | None
    airway_bill_file_id: uuid.UUID | None
    created_at: datetime
    items: list[OrderItemOut]
    picklist_id: uuid.UUID | None
    shipment_id: uuid.UUID | None


class PickLineOut(BaseModel):
    id: uuid.UUID
    sku: str
    barcode: str
    product_name: str
    location_code: str
    compact_location: str
    quantity: int
    picked_qty: int
    sequence: int


class PickListOut(BaseModel):
    id: uuid.UUID
    pick_number: str
    order_id: uuid.UUID
    order_number: str
    customer_id: uuid.UUID
    customer_name: str
    status: str
    lines: list[PickLineOut]


class ScanIn(APIModel):
    barcode: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, gt=0, le=100000)


class PickCreate(APIModel):
    order_id: uuid.UUID


class ShipmentOut(BaseModel):
    id: uuid.UUID
    shipment_number: str
    order_id: uuid.UUID
    order_number: str
    customer_id: uuid.UUID
    customer_name: str
    status: str
    courier: str
    tracking_number: str | None
    airway_bill_file_id: uuid.UUID | None
    receiver_name: str
    item_count: int
    shipped_at: datetime | None
    created_at: datetime


class DispatchIn(APIModel):
    tracking_number: str | None = Field(default=None, max_length=80)


class FileOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class SearchHit(BaseModel):
    kind: str
    label: str
    detail: str
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    product_id: uuid.UUID | None = None
    sku: str | None = None
    barcode: str | None = None
    location_code: str | None = None
    order_id: uuid.UUID | None = None
    order_number: str | None = None
    tracking_number: str | None = None
    on_hand_qty: int | None = None
    reserved_qty: int | None = None
    available_qty: int | None = None


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]


class LowStockRow(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    product_id: uuid.UUID
    sku: str
    product_name: str
    on_hand_qty: int
    reserved_qty: int
    available_qty: int
    reorder_point: int


class FastMoveRow(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    customer_name: str
    outbound_qty: int


class DeadStockRow(BaseModel):
    product_id: uuid.UUID
    sku: str
    product_name: str
    customer_name: str
    on_hand_qty: int
    last_movement_at: datetime


class WarehouseDashboard(BaseModel):
    total_sku: int
    total_stock: int
    orders_awaiting_picking: int
    orders_awaiting_packing: int
    ready_to_ship: int
    shipments_today: int
    low_inventory: list[LowStockRow]
    fast_moving: list[FastMoveRow]
    dead_stock: list[DeadStockRow]


class CustomerDashboard(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    total_sku: int
    total_stock: int
    reserved_stock: int
    available_stock: int
    open_orders: int
    shipments_today: int
    low_inventory: list[LowStockRow]
    recent_movements: list[TransactionOut]


class AuditOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    user_id: uuid.UUID | None
    user_email: str | None
    customer_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    ip: str | None
    old_value: dict | None
    new_value: dict | None


class BillingLine(BaseModel):
    description: str
    quantity: str
    rate: str
    amount: str


class BillingReport(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    currency: str
    date_from: str
    date_to: str
    method: str
    lines: list[BillingLine]
    total: str
