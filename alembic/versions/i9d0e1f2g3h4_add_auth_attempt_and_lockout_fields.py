"""add_auth_attempt_and_lockout_fields

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2026-10-03 21:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'i9d0e1f2g3h4'
down_revision: Union[str, None] = 'h8c9d0e1f2g3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
    """)
    op.execute("""
        ALTER TABLE users 
        ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;
    """)
    op.execute("""
        ALTER TABLE customer_users 
        ADD COLUMN IF NOT EXISTS otp_attempts INTEGER DEFAULT 0;
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE customer_users 
        DROP COLUMN IF EXISTS otp_attempts;
    """)
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS locked_until;
    """)
    op.execute("""
        ALTER TABLE users 
        DROP COLUMN IF EXISTS failed_login_attempts;
    """)
