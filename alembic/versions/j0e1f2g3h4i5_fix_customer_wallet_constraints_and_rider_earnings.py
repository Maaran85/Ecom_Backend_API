"""fix_customer_wallet_constraints_and_rider_earnings

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-10-17 11:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'j0e1f2g3h4i5'
down_revision: Union[str, None] = 'i9d0e1f2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure customer_wallets columns exist
    op.execute("""
        ALTER TABLE customer_wallets
        ADD COLUMN IF NOT EXISTS order_delivered_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS order_placed_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS order_canceled_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS order_returned_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS available_points DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS available_amount DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS on_hold_points DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS on_hold_amount DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS redeemed_points DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS redeemed_amount DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS lifetime_earned_points DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS lifetime_earned_amount DOUBLE PRECISION DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS ref_com_status VARCHAR(50) DEFAULT 'pending';
    """)

    # 2. Update ref_com_status check constraint to support all CommissionStatus values (including 'na' and 'paid')
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'customer_wallets_ref_com_status_check'
            ) THEN
                ALTER TABLE customer_wallets DROP CONSTRAINT customer_wallets_ref_com_status_check;
            END IF;
            
            ALTER TABLE customer_wallets ADD CONSTRAINT customer_wallets_ref_com_status_check 
            CHECK (ref_com_status IN (
                'pending', 'on_hold', 'credited', 'cancelled', 'refund', 'redeemed', 'paid', 'na',
                'PENDING', 'ON_HOLD', 'CREDITED', 'CANCELLED', 'REFUND', 'REDEEMED', 'PAID', 'NA'
            ));
        END $$;
    """)

    # 3. Ensure delivery_riders balance columns default to 0.0 and contain no NULLs
    op.execute("UPDATE delivery_riders SET current_balance = 0.0 WHERE current_balance IS NULL;")
    op.execute("UPDATE delivery_riders SET total_earnings = 0.0 WHERE total_earnings IS NULL;")
    op.execute("ALTER TABLE delivery_riders ALTER COLUMN current_balance SET DEFAULT 0.0;")
    op.execute("ALTER TABLE delivery_riders ALTER COLUMN total_earnings SET DEFAULT 0.0;")

    # 4. Ensure order_items has rider_payment_method
    op.execute("""
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS rider_payment_method VARCHAR(50);
    """)

    # 5. Check for duplicate delivery earnings and safely create partial unique index
    op.execute("""
        DO $$
        DECLARE
            dup_count INTEGER;
            dup_details TEXT;
        BEGIN
            SELECT COUNT(*) INTO dup_count
            FROM (
                SELECT order_item_id
                FROM rider_earnings
                WHERE type = 'delivery' AND order_item_id IS NOT NULL
                GROUP BY order_item_id
                HAVING COUNT(*) > 1
            ) d;
            
            IF dup_count > 0 THEN
                SELECT STRING_AGG(order_item_id::text || ' (' || c::text || ' records)', ', ') INTO dup_details
                FROM (
                    SELECT order_item_id, COUNT(*) as c
                    FROM rider_earnings
                    WHERE type = 'delivery' AND order_item_id IS NOT NULL
                    GROUP BY order_item_id
                    HAVING COUNT(*) > 1
                    ORDER BY order_item_id
                    LIMIT 20
                ) sub;
                
                RAISE EXCEPTION 'Cannot create partial unique index uq_rider_earnings_delivery_order_item: found % order item(s) with duplicate delivery earnings in rider_earnings. Sample affected order_item_ids: [%]. Manual financial reconciliation is required before this migration can be applied.', dup_count, dup_details;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = 'uq_rider_earnings_delivery_order_item'
            ) THEN
                CREATE UNIQUE INDEX uq_rider_earnings_delivery_order_item
                ON rider_earnings (order_item_id)
                WHERE type = 'delivery' AND order_item_id IS NOT NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Retain columns to avoid destructive data loss, but restore previous check constraint and drop unique index
    op.execute("DROP INDEX IF EXISTS uq_rider_earnings_delivery_order_item;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'customer_wallets_ref_com_status_check'
            ) THEN
                ALTER TABLE customer_wallets DROP CONSTRAINT customer_wallets_ref_com_status_check;
            END IF;
        END $$;
    """)
