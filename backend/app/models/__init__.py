"""Importing this package registers every table on Base.metadata."""

from app.core.database import Base
from app.models.entities import (
    AuditLog,
    Customer,
    DocumentSequence,
    IdempotencyKey,
    InventoryTransaction,
    Location,
    Order,
    OrderItem,
    PickList,
    PickListItem,
    Product,
    RateCard,
    RefreshToken,
    Shipment,
    StoredFile,
    User,
)

__all__ = [
    "AuditLog",
    "Base",
    "Customer",
    "DocumentSequence",
    "IdempotencyKey",
    "InventoryTransaction",
    "Location",
    "Order",
    "OrderItem",
    "PickList",
    "PickListItem",
    "Product",
    "RateCard",
    "RefreshToken",
    "Shipment",
    "StoredFile",
    "User",
]
