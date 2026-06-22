import asyncio
from core.database import async_session
from models.product import Product
from sqlalchemy import select

async def main():
    async with async_session() as db:
        res = await db.execute(select(Product.id, Product.stock).limit(5))
        print("Stocks:", res.all())

asyncio.run(main())
