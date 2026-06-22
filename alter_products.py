import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def alter_columns():
    async with engine.begin() as conn:
        try:
            await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS parent_product_id INTEGER REFERENCES products(id);"))
            print("Successfully added parent_product_id column")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(alter_columns())
