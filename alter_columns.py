import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def alter_columns():
    async with engine.begin() as conn:
        try:
            # Drop the defaults before altering type to avoid casting issues
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN current_level DROP DEFAULT;"))
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN priority DROP DEFAULT;"))

            # Alter columns to use the ENUM types
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN current_level TYPE ticketlevel USING current_level::ticketlevel;"))
            print("Successfully altered current_level to ticketlevel")
            
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN priority TYPE ticketpriority USING priority::ticketpriority;"))
            print("Successfully altered priority to ticketpriority")

            # Restore the defaults
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN current_level SET DEFAULT 'DEALER'::ticketlevel;"))
            await conn.execute(text("ALTER TABLE support_tickets ALTER COLUMN priority SET DEFAULT 'MEDIUM'::ticketpriority;"))
            print("Successfully restored defaults")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(alter_columns())
