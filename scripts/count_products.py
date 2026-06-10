import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import func, select
from models import Product

async def count():
    async with SessionLocal() as db:
        res = await db.execute(select(func.count(Product.id)))
        print(f"Total Products: {res.scalar()}")

if __name__ == "__main__":
    asyncio.run(count())
