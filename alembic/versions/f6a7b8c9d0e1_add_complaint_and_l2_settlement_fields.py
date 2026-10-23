"""add_complaint_and_l2_settlement_fields

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-29 17:52:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE support_tickets 
        ADD COLUMN IF NOT EXISTS order_item_id INTEGER REFERENCES order_items(id),
        ADD COLUMN IF NOT EXISTS complaint_reason VARCHAR(255),
        ADD COLUMN IF NOT EXISTS assigned_department VARCHAR(50),
        ADD COLUMN IF NOT EXISTS root_cause_analysis TEXT,
        ADD COLUMN IF NOT EXISTS action_taken TEXT,
        ADD COLUMN IF NOT EXISTS device_info JSON,
        ADD COLUMN IF NOT EXISTS exceptional_refund_approved BOOLEAN DEFAULT FALSE;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_support_tickets_order_item_id ON support_tickets (order_item_id);
    """)
    op.execute("""
        ALTER TABLE settlements
        ADD COLUMN IF NOT EXISTS is_l2_approved BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS l2_approved_by INTEGER REFERENCES users(id),
        ADD COLUMN IF NOT EXISTS l2_approved_at TIMESTAMP WITH TIME ZONE;
    """)

def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_support_tickets_order_item_id;
    """)
    op.execute("""
        ALTER TABLE support_tickets 
        DROP COLUMN IF EXISTS order_item_id,
        DROP COLUMN IF EXISTS complaint_reason,
        DROP COLUMN IF EXISTS assigned_department,
        DROP COLUMN IF EXISTS root_cause_analysis,
        DROP COLUMN IF EXISTS action_taken,
        DROP COLUMN IF EXISTS device_info,
        DROP COLUMN IF EXISTS exceptional_refund_approved;
    """)
    op.execute("""
        ALTER TABLE settlements
        DROP COLUMN IF EXISTS is_l2_approved,
        DROP COLUMN IF EXISTS l2_approved_by,
        DROP COLUMN IF EXISTS l2_approved_at;
    """)
