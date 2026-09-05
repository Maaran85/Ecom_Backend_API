"""add_marketing_customer_charge_to_order_items

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26 10:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE order_items 
        ADD COLUMN IF NOT EXISTS marketing_customer_charge DOUBLE PRECISION DEFAULT 0.0;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE order_items 
        DROP COLUMN IF EXISTS marketing_customer_charge;
    """)
