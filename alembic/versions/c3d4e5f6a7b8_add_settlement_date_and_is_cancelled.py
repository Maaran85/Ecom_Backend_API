"""add_settlement_date_and_is_cancelled

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-23 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add columns with nullable=True / default
    op.add_column('settlements', sa.Column('settlement_date', sa.Date(), nullable=True))
    op.add_column('settlement_items', sa.Column('is_cancelled', sa.Boolean(), server_default='false', nullable=False))

    # 2. Backfill historical settlement_date with period_end
    op.execute("UPDATE settlements SET settlement_date = period_end")

    # 3. Backfill historical is_cancelled for items of CANCELLED settlements
    op.execute("""
        UPDATE settlement_items 
        SET is_cancelled = true 
        WHERE settlement_id IN (SELECT id FROM settlements WHERE status = 'CANCELLED')
    """)

    # 4. Create indices
    op.create_index('ix_settlements_settlement_date', 'settlements', ['settlement_date'], unique=False)
    op.create_index('ix_settlement_items_is_cancelled', 'settlement_items', ['is_cancelled'], unique=False)

    # 5. Drop old index
    op.execute("DROP INDEX IF EXISTS uq_active_settlement_order_item")

    # 6. Create new index that filters by is_cancelled = false
    op.execute("""
        CREATE UNIQUE INDEX uq_active_settlement_order_item 
        ON settlement_items (order_item_id) 
        WHERE (order_item_id IS NOT NULL AND is_cancelled = false)
    """)

def downgrade() -> None:
    # 1. Drop new index
    op.execute("DROP INDEX IF EXISTS uq_active_settlement_order_item")

    # 2. Re-create old index
    op.execute("""
        CREATE UNIQUE INDEX uq_active_settlement_order_item 
        ON settlement_items (order_item_id) 
        WHERE order_item_id IS NOT NULL
    """)

    # 3. Drop indices
    op.drop_index('ix_settlement_items_is_cancelled', table_name='settlement_items')
    op.drop_index('ix_settlements_settlement_date', table_name='settlements')

    # 4. Drop columns
    op.drop_column('settlement_items', 'is_cancelled')
    op.drop_column('settlements', 'settlement_date')
