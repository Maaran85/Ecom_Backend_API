import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import select
from models import Product

async def check_prices():
    async with SessionLocal() as db:
        result = await db.execute(select(Product).limit(5))
        products = result.scalars().all()
        for p in products:
            print(f"ID {p.id}: Price {p.price}, Discount {p.discount_price}")

if __name__ == "__main__":
    asyncio.run(check_prices())
