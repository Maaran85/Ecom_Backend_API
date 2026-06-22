import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb"

async def main():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        print("Checking if attachments column exists...")
        try:
            await conn.execute(text("ALTER TABLE support_tickets ADD COLUMN attachments JSON;"))
            print("Successfully added attachments column.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("Column 'attachments' already exists.")
            else:
                print(f"Error: {e}")
                
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
