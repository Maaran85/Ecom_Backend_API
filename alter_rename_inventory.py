import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def rename_table():
    async with engine.begin() as conn:
        try:
            # Rename the table
            await conn.execute(text("ALTER TABLE IF EXISTS hub_inventories RENAME TO product_inventories;"))
            
            # Optionally rename sequence and index if needed, but PostgreSQL handles table rename fine.
            # We can also rename the constraint if it exists.
            
            print("Successfully renamed hub_inventories to product_inventories")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(rename_table())
