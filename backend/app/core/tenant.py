import uuid

from app.core.errors import AppError
from app.domain.enums import Role
from app.models.entities import User


def ensure_access(user: User, customer_id: uuid.UUID) -> None:
    """Customer users are confined to their own tenant. Missing rows stay 404."""
    if user.role == Role.CUSTOMER and user.customer_id != customer_id:
        raise AppError("Not found", 404, "not_found")


def scoped_customer_id(user: User, requested: uuid.UUID | None) -> uuid.UUID | None:
    if user.role == Role.CUSTOMER:
        if requested is not None and requested != user.customer_id:
            raise AppError("Not found", 404, "not_found")
        return user.customer_id
    return requested


def require_customer_id(user: User, requested: uuid.UUID | None) -> uuid.UUID:
    customer_id = scoped_customer_id(user, requested)
    if customer_id is None:
        raise AppError("customer_id is required", 400, "customer_required")
    return customer_id
