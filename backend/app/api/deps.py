import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.domain.enums import Role
from app.models.entities import User

bearer_scheme = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host
    return None


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials if creds is not None else None
    if token is None and (request.url.path.endswith("/content") or request.url.path.endswith("/barcode")):
        token = request.query_params.get("access_token")
    if not token:
        raise AppError("Not authenticated", 401, "unauthorized")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise AppError("Not authenticated", 401, "unauthorized")
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AppError("Not authenticated", 401, "unauthorized") from exc
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise AppError("Not authenticated", 401, "unauthorized")
    return user


def require_roles(*roles: Role):
    allowed = {role.value if isinstance(role, Role) else role for role in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise AppError("Forbidden", 403, "forbidden")
        return user

    return dependency
