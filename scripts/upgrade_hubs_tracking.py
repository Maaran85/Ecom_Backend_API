
import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_hubs_tracking_fields():
    async with engine.begin() as conn:
        print("Checking for created_by and updated_by columns in delivery_hubs table...")
        
        # Add created_by column
        await conn.execute(text("""
            ALTER TABLE delivery_hubs 
            ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL
        """))
        print("Column 'created_by' ensured.")
        
        # Add updated_by column
        await conn.execute(text("""
            ALTER TABLE delivery_hubs 
            ADD COLUMN IF NOT EXISTS updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
        """))
        print("Column 'updated_by' ensured.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_hubs_tracking_fields())
