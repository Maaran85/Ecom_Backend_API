import asyncio
import os
import sys

# Add the Ecom_Backend_API directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import engine
from sqlalchemy import text

async def alter_partners_table():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE partners ADD COLUMN pincode VARCHAR(20)"))
            print("Added pincode column")
        except Exception as e:
            print(f"Error adding pincode: {e}")
            
        try:
            await conn.execute(text("ALTER TABLE partners ADD COLUMN city VARCHAR(100)"))
            print("Added city column")
        except Exception as e:
            print(f"Error adding city: {e}")
            
        try:
            await conn.execute(text("ALTER TABLE partners ADD COLUMN state VARCHAR(100)"))
            print("Added state column")
        except Exception as e:
            print(f"Error adding state: {e}")

if __name__ == "__main__":
    asyncio.run(alter_partners_table())
