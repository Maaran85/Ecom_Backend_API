import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def add_decor():
    async with engine.begin() as conn:
        try:
            from sqlalchemy import text
            result = await conn.execute(text("SELECT id FROM categories WHERE name = 'Decor'"))
            if result.fetchone():
                print("Decor category already exists.")
            else:
                await conn.execute(text("INSERT INTO categories (name, is_active) VALUES ('Decor', true)"))
                print("Successfully added Decor category.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_decor())
