"""add_customer_password_and_lockout

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2026-10-17 21:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'l2g3h4i5j6k7'
down_revision: Union[str, None] = 'k1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE customer_users ADD COLUMN IF NOT EXISTS password_hash VARCHAR;")
    op.execute("ALTER TABLE customer_users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;")
    op.execute("ALTER TABLE customer_users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE;")
    op.execute("ALTER TABLE customer_users ADD COLUMN IF NOT EXISTS otp_expires_at TIMESTAMP WITH TIME ZONE;")


def downgrade() -> None:
    op.execute("ALTER TABLE customer_users DROP COLUMN IF EXISTS otp_expires_at;")
    op.execute("ALTER TABLE customer_users DROP COLUMN IF EXISTS locked_until;")
    op.execute("ALTER TABLE customer_users DROP COLUMN IF EXISTS failed_login_attempts;")
    op.execute("ALTER TABLE customer_users DROP COLUMN IF EXISTS password_hash;")
