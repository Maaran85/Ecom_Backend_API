"""add_order_item_fee_and_slab_snapshots

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-10-26 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'm3h4i5j6k7l8'
down_revision: Union[str, None] = 'l2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketplace_dealer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketplace_customer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketplace_slab_id INTEGER;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketplace_fee_gst_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketplace_fee_gst_amount DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketing_dealer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketing_customer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketing_slab_id INTEGER;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketing_fee_gst_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS marketing_fee_gst_amount DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS logistics_dealer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS logistics_customer_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS logistics_slab_id INTEGER;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS logistics_fee_gst_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS logistics_fee_gst_amount DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS customer_delivery_gst_rate DOUBLE PRECISION;")
    op.execute("ALTER TABLE order_items ADD COLUMN IF NOT EXISTS customer_delivery_gst_amount DOUBLE PRECISION;")


def downgrade() -> None:
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS customer_delivery_gst_amount;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS customer_delivery_gst_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS logistics_fee_gst_amount;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS logistics_fee_gst_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS logistics_slab_id;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS logistics_customer_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS logistics_dealer_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketing_fee_gst_amount;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketing_fee_gst_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketing_slab_id;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketing_customer_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketing_dealer_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketplace_fee_gst_amount;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketplace_fee_gst_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketplace_slab_id;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketplace_customer_rate;")
    op.execute("ALTER TABLE order_items DROP COLUMN IF EXISTS marketplace_dealer_rate;")
