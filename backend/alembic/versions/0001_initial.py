"""Initial schema and inventory balance views.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-11
"""

from alembic import op
from sqlalchemy import text

from app.core.database import Base
from app.dbviews import INVENTORY_BALANCES, INVENTORY_BALANCES_BY_SKU
import app.models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    bind.execute(text(INVENTORY_BALANCES))
    bind.execute(text(INVENTORY_BALANCES_BY_SKU))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP VIEW IF EXISTS inventory_balances_by_sku"))
    bind.execute(text("DROP VIEW IF EXISTS inventory_balances"))
    Base.metadata.drop_all(bind=bind)
