import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb"

async def run_migration():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        print("Step 1: Dropping old FK constraint...")
        await conn.execute(text("ALTER TABLE recharge_transactions DROP CONSTRAINT IF EXISTS recharge_transactions_user_id_fkey"))
        
        print("Step 2: Renaming user_id to customer_id...")
        await conn.execute(text("ALTER TABLE recharge_transactions RENAME COLUMN user_id TO customer_id"))
        
        print("Step 3: Adding new FK constraint to customer_users...")
        await conn.execute(text("""
            ALTER TABLE recharge_transactions 
            ADD CONSTRAINT recharge_transactions_customer_id_fkey 
            FOREIGN KEY (customer_id) REFERENCES customer_users(id) 
            ON DELETE CASCADE
        """))
        
        print("Step 4: Renaming index if exists...")
        await conn.execute(text("""
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
        """))
        
    print("Migration completed successfully.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migration())
