from app.core.database import SessionLocal
from app.services.reports import low_stock_rows, remember_low_stock


def refresh_low_stock_snapshot() -> int:
    db = SessionLocal()
    try:
        rows = low_stock_rows(db, None)
        remember_low_stock(rows)
        return len(rows)
    finally:
        db.close()
