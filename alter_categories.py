import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def alter_table():
    async with engine.begin() as conn:
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE categories ADD COLUMN is_active BOOLEAN DEFAULT true NOT NULL;"))
            print("Successfully added is_active column")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(alter_table())
