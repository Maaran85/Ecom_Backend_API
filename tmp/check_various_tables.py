import asyncio
from sqlalchemy import text
from core.database import SessionLocal, engine

async def check():
    async with engine.connect() as conn:
        for table in ['orders', 'order_items', 'cart_items']:
            res = await conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'"))
            cols = [r[0] for r in res.fetchall()]
            print(f"{table} columns: {cols}")

if __name__ == "__main__":
    asyncio.run(check())
