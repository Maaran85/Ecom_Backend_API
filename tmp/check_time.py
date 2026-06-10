import asyncio
from sqlalchemy import select
from core.database import engine
from models.cart import Order
from datetime import datetime, timezone

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(select(Order.id, Order.created_at).order_by(Order.id.desc()).limit(1))
        row = res.fetchone()
        if row:
            print(f"Order ID: {row[0]}")
            print(f"Created At (DB): {row[1]}")
            print(f"Current Time (Python UTC): {datetime.now(timezone.utc)}")

if __name__ == "__main__":
    asyncio.run(check())
