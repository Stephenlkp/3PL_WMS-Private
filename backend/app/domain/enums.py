from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "warehouse_supervisor"
    PICKER = "picker"
    PACKER = "packer"
    CUSTOMER = "customer"


class TxType(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"
    MOVE = "MOVE"
    ADJUSTMENT = "ADJUSTMENT"
    RESERVED = "RESERVED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PICKING = "PICKING"
    PICKED = "PICKED"
    PACKING = "PACKING"
    READY_TO_SHIP = "READY_TO_SHIP"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class PickStatus(str, Enum):
    PENDING = "PENDING"
    PICKING = "PICKING"
    PICKED = "PICKED"
    CANCELLED = "CANCELLED"


class ShipmentStatus(str, Enum):
    READY_TO_SHIP = "READY_TO_SHIP"
    SHIPPED = "SHIPPED"


PHYSICAL_TYPES = {TxType.INBOUND, TxType.OUTBOUND, TxType.MOVE, TxType.ADJUSTMENT}

STAFF_ROLES = {Role.ADMIN, Role.SUPERVISOR, Role.PICKER, Role.PACKER}
MANAGER_ROLES = {Role.ADMIN, Role.SUPERVISOR}
