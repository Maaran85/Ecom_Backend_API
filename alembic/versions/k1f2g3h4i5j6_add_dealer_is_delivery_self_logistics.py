"""add_dealer_is_delivery_self_logistics

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2026-10-17 17:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'k1f2g3h4i5j6'
down_revision: Union[str, None] = 'j0e1f2g3h4i5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE dealers ADD COLUMN IF NOT EXISTS is_delivery_self_logistics BOOLEAN DEFAULT FALSE;")


def downgrade() -> None:
    op.execute("ALTER TABLE dealers DROP COLUMN IF EXISTS is_delivery_self_logistics;")
