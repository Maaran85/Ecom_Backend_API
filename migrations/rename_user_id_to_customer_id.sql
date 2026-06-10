-- Migration: Rename user_id → customer_id and change FK to customer_users
-- Generated: 2026-03-23
-- Run this script against your PostgreSQL database.

BEGIN;

-- Step 1: Drop old FK constraint (users.id)
ALTER TABLE recharge_transactions
    DROP CONSTRAINT IF EXISTS recharge_transactions_user_id_fkey;

-- Step 2: Rename the column
ALTER TABLE recharge_transactions
    RENAME COLUMN user_id TO customer_id;

-- Step 3: Add new FK constraint pointing to customer_users.id
ALTER TABLE recharge_transactions
    ADD CONSTRAINT recharge_transactions_customer_id_fkey
    FOREIGN KEY (customer_id) REFERENCES customer_users(id)
    ON DELETE CASCADE;

-- Step 4: Rename the index
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'recharge_transactions'
          AND indexname = 'ix_recharge_transactions_user_id'
    ) THEN
        ALTER INDEX ix_recharge_transactions_user_id
            RENAME TO ix_recharge_transactions_customer_id;
    END IF;
END $$;

COMMIT;
