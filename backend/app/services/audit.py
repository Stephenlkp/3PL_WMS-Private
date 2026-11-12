import json
import uuid

from sqlalchemy.orm import Session

from app.models.entities import AuditLog, User


def _jsonable(value):
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str))


def write_audit(
    session: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    ip: str | None = None,
    customer_id: uuid.UUID | None = None,
    old: dict | None = None,
    new: dict | None = None,
) -> None:
    resolved_customer = customer_id
    if resolved_customer is None and user is not None:
        resolved_customer = user.customer_id
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            customer_id=resolved_customer,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            ip=ip,
            old_value=_jsonable(old),
            new_value=_jsonable(new),
        )
    )
