"""add_resolved_by_user_id_to_support_tickets

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-03 20:05:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE support_tickets 
        ADD COLUMN IF NOT EXISTS resolved_by_user_id INTEGER REFERENCES users(id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_support_tickets_resolved_by_user_id ON support_tickets (resolved_by_user_id);
    """)
    op.execute("""
        UPDATE support_tickets 
        SET resolved_by_user_id = 105 
        WHERE ticket_number = 'TKT-BPD82P' AND status = 'RESOLVED';
    """)

def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS ix_support_tickets_resolved_by_user_id;
    """)
    op.execute("""
        ALTER TABLE support_tickets 
        DROP COLUMN IF EXISTS resolved_by_user_id;
    """)
