from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.time import ensure_utc
from app.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    refresh_expiry,
    validate_password_strength,
    verify_password,
)
from app.models.entities import RefreshToken, User
from app.schemas import TokenOut
from app.services.audit import write_audit
from app.services.catalog import _clean_email, user_out
from app.services.inventory import reject


def issue_tokens(session: Session, user: User, ip: str | None, user_agent: str | None) -> TokenOut:
    raw = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw),
            expires_at=refresh_expiry(),
            ip=ip,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    session.flush()
    access = create_access_token(user_id=user.id, role=user.role, customer_id=user.customer_id)
    return TokenOut(
        access_token=access,
        refresh_token=raw,
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=user_out(user),
    )


def login(session: Session, email: str, password: str, ip: str | None, user_agent: str | None) -> TokenOut:
    normalized = _clean_email(email)
    user = session.scalar(select(User).where(User.email == normalized))
    if user is None or not user.active or not verify_password(password, user.password_hash):
        reject(
            session,
            AppError("Invalid email or password", 401, "invalid_credentials"),
            user=None,
            action="auth.login_failed",
            entity_type="user",
            ip=ip,
            new={"email": normalized},
        )
    write_audit(session, user=user, action="auth.login", entity_type="user", entity_id=user.id, ip=ip)
    return issue_tokens(session, user, ip, user_agent)


def rotate_refresh(session: Session, raw_token: str, ip: str | None, user_agent: str | None) -> TokenOut:
    token_hash = hash_refresh_token(raw_token)
    row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if row is None:
        raise AppError("Invalid refresh token", 401, "unauthorized")
    now = datetime.now(UTC)
    if row.revoked_at is not None:
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        raise AppError("Refresh token reuse detected", 401, "token_reuse")
    if ensure_utc(row.expires_at) < now:
        raise AppError("Refresh token expired", 401, "unauthorized")
    user = session.get(User, row.user_id)
    if user is None or not user.active:
        raise AppError("Invalid refresh token", 401, "unauthorized")
    row.revoked_at = now
    issued = issue_tokens(session, user, ip, user_agent)
    session.flush()
    replacement = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .order_by(RefreshToken.created_at.desc())
    )
    if replacement is not None:
        row.replaced_by = replacement.id
    write_audit(session, user=user, action="auth.refresh", entity_type="user", entity_id=user.id, ip=ip)
    return issued


def logout(session: Session, user: User, raw_token: str | None, ip: str | None) -> None:
    now = datetime.now(UTC)
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        row = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.user_id == user.id))
        if row is not None and row.revoked_at is None:
            row.revoked_at = now
    else:
        session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    write_audit(session, user=user, action="auth.logout", entity_type="user", entity_id=user.id, ip=ip)


def change_password(session: Session, user: User, current: str, new_password: str, ip: str | None) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError("Current password is wrong", 400, "invalid_credentials")
    validate_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    now = datetime.now(UTC)
    session.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now)
    )
    write_audit(session, user=user, action="auth.password_change", entity_type="user", entity_id=user.id, ip=ip)
