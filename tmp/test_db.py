import asyncio
from sqlalchemy import select
from core.database import SessionLocal
from models.order_return import OrderReturn

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(OrderReturn).limit(1))
        print(res.fetchall())

if __name__ == "__main__":
    asyncio.run(main())
