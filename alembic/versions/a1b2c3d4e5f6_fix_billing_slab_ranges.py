"""fix_billing_slab_ranges

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-08-17 18:42:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. MARKETPLACE SLABS
    op.execute("UPDATE billing_slabs SET min_price = 500.01, max_price = 1000.0, is_active = true WHERE id = 13")
    op.execute("UPDATE billing_slabs SET min_price = 1000.01, max_price = 5000.0, is_active = true WHERE id = 14")
    op.execute("UPDATE billing_slabs SET min_price = 5000.01, max_price = 10000.0, is_active = true WHERE id = 17")
    op.execute("UPDATE billing_slabs SET min_price = 10000.01, max_price = 20000.0, dealer_percentage = 0.07, customer_percentage = 0.018, is_active = true WHERE id = 18")
    op.execute("UPDATE billing_slabs SET min_price = 20000.01, max_price = 30000.0, dealer_percentage = 0.07, customer_percentage = 0.018, is_active = true WHERE id = 19")
    op.execute("UPDATE billing_slabs SET min_price = 30000.01, max_price = 35000.0, dealer_percentage = 0.055, customer_percentage = 0.012, is_active = true WHERE id = 22")
    op.execute("UPDATE billing_slabs SET min_price = 35000.01, max_price = 45000.0, dealer_percentage = 0.05, customer_percentage = 0.01, is_active = true WHERE id = 28")
    op.execute("UPDATE billing_slabs SET min_price = 45000.01, max_price = NULL, dealer_percentage = 0.055, customer_percentage = 0.012, is_active = true WHERE id = 25")

    # 2. MARKETING SLABS
    op.execute("UPDATE billing_slabs SET min_price = 500.01, max_price = 1000.0, is_active = true WHERE id = 34")
    op.execute("UPDATE billing_slabs SET min_price = 1000.01, max_price = 2000.0, is_active = true WHERE id = 35")
    op.execute("UPDATE billing_slabs SET min_price = 2000.01, max_price = 5000.0, dealer_percentage = 0.08, is_active = true WHERE id = 20")
    op.execute("UPDATE billing_slabs SET min_price = 5000.01, max_price = 10000.0, dealer_percentage = 0.075, is_active = true WHERE id = 23")
    op.execute("UPDATE billing_slabs SET min_price = 10000.01, max_price = 25000.0, dealer_percentage = 0.07, is_active = true WHERE id = 29")
    op.execute("UPDATE billing_slabs SET min_price = 25000.01, max_price = NULL, dealer_percentage = 0.05, is_active = true WHERE id = 45")
    op.execute("UPDATE billing_slabs SET is_active = false WHERE id IN (46, 47)")

    # 3. LOGISTICS SLABS
    op.execute("UPDATE billing_slabs SET min_price = 500.01, max_price = 1000.0, is_active = true WHERE id = 36")
    op.execute("UPDATE billing_slabs SET min_price = 1000.01, max_price = 2000.0, is_active = true WHERE id = 37")
    op.execute("UPDATE billing_slabs SET min_price = 2000.01, max_price = 5000.0, dealer_percentage = 0.06, is_active = true WHERE id = 21")
    op.execute("UPDATE billing_slabs SET min_price = 5000.01, max_price = 10000.0, dealer_percentage = 0.065, is_active = true WHERE id = 24")
    op.execute("UPDATE billing_slabs SET min_price = 10000.01, max_price = NULL, dealer_percentage = 0.06, is_active = true WHERE id = 30")

    # 4. AUCTION, REFERRAL, SPIN & WIN SLABS
    op.execute("UPDATE billing_slabs SET min_price = 500.01, max_price = 1000.0, is_active = true WHERE id IN (32, 40, 43)")
    op.execute("UPDATE billing_slabs SET min_price = 1000.01, max_price = NULL, is_active = true WHERE id IN (33, 41, 44)")

def downgrade() -> None:
    # Revert min_price boundaries to .0 integer values and deactivate added upper slabs
    op.execute("UPDATE billing_slabs SET min_price = 501.0 WHERE id IN (13, 34, 36, 32, 40, 43)")
    op.execute("UPDATE billing_slabs SET min_price = 1001.0 WHERE id IN (14, 35, 37, 33, 41, 44)")
    op.execute("UPDATE billing_slabs SET min_price = 2001.0 WHERE id IN (20, 21)")
    op.execute("UPDATE billing_slabs SET min_price = 5001.0 WHERE id IN (17, 23, 24)")
    op.execute("UPDATE billing_slabs SET min_price = 10001.0 WHERE id IN (18, 29, 30)")
    op.execute("UPDATE billing_slabs SET min_price = 20001.0 WHERE id = 19")
    op.execute("UPDATE billing_slabs SET min_price = 25001.0 WHERE id = 45")
    op.execute("UPDATE billing_slabs SET min_price = 30001.0 WHERE id = 22")
    op.execute("UPDATE billing_slabs SET min_price = 35001.0 WHERE id = 28")
    op.execute("UPDATE billing_slabs SET min_price = 45001.0 WHERE id = 25")
    op.execute("UPDATE billing_slabs SET is_active = false WHERE id IN (18, 19, 20, 21, 22, 23, 24, 25)")
