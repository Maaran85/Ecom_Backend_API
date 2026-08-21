"""add_unique_index_settlement_items

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-17 19:07:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create partial unique index on settlement_items(order_item_id)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_settlement_order_item "
        "ON settlement_items (order_item_id) "
        "WHERE order_item_id IS NOT NULL"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_settlement_order_item")
