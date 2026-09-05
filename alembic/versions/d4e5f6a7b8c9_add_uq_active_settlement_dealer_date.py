"""add_uq_active_settlement_dealer_date

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-23 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Check for existing duplicate active settlements before creating index
    connection = op.get_bind()
    res = connection.execute(sa.text("""
        SELECT dealer_id, settlement_date, COUNT(*) 
        FROM settlements 
        WHERE status != 'CANCELLED' AND settlement_date IS NOT NULL
        GROUP BY dealer_id, settlement_date
        HAVING COUNT(*) > 1;
    """)).fetchall()

    if res:
        conflicts = [f"Dealer ID: {row[0]}, Date: {row[1]}, Count: {row[2]}" for row in res]
        raise Exception(
            "Migration halted: Conflicting duplicate active settlements found. "
            "Cannot create unique index 'uq_active_settlement_dealer_date' on settlements without violating uniqueness. "
            f"Conflicting rows: {', '.join(conflicts)}"
        )

    op.execute("""
        CREATE UNIQUE INDEX uq_active_settlement_dealer_date 
        ON settlements (dealer_id, settlement_date) 
        WHERE (status != 'CANCELLED')
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_active_settlement_dealer_date")
