from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import DocumentSequence


def next_number(session: Session, prefix: str) -> str:
    day = datetime.now(UTC).strftime("%Y%m%d")
    key = f"{prefix}-{day}"
    stmt = select(DocumentSequence).where(DocumentSequence.name == key)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    row = session.scalar(stmt)
    if row is None:
        row = DocumentSequence(name=key, last_value=0)
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            row = session.scalar(stmt)
            if row is None:
                raise
    row.last_value += 1
    session.flush()
    return f"{prefix}-{day}-{row.last_value:04d}"
