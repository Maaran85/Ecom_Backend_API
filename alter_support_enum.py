import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def alter_enum():
    async with engine.begin() as conn:
        try:
            # tickettype values to add
            tickettype_values = ["ORDER_ISSUE", "REFUND", "PRODUCT_QUERY", "TECHNICAL"]
            for val in tickettype_values:
                await conn.execute(text(f"ALTER TYPE tickettype ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Added {val} to tickettype")
            
            # ticketstatus values to add
            ticketstatus_values = ["WAITING_ON_CUSTOMER"]
            for val in ticketstatus_values:
                await conn.execute(text(f"ALTER TYPE ticketstatus ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Added {val} to ticketstatus")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(alter_enum())
