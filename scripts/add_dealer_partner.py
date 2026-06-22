import asyncio
import os
import sys

# Add the Ecom_Backend_API directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import engine
from sqlalchemy import text

async def alter_dealers_table():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE dealers ADD COLUMN partner_id INTEGER REFERENCES partners(id)"))
            print("Added partner_id column to dealers")
        except Exception as e:
            print(f"Error adding partner_id: {e}")

if __name__ == "__main__":
    asyncio.run(alter_dealers_table())
