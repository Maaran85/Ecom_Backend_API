
import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_riders_dob():
    async with engine.begin() as conn:
        print("Adding dob column to delivery_riders table...")
        
        # Check existing columns
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'delivery_riders'"))
        columns = [row[0] for row in result.fetchall()]
        
        if 'dob' not in columns:
            print("Adding column dob...")
            await conn.execute(text("ALTER TABLE delivery_riders ADD COLUMN dob VARCHAR"))
            print("Column dob added successfully.")
        else:
            print("Column dob already exists.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_riders_dob())
