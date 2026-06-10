import asyncio
from sqlalchemy import text
from core.database import SessionLocal, engine

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'order_returns'"))
        cols = [r[0] for r in res.fetchall()]
        print(f"order_returns columns: {cols}")

if __name__ == "__main__":
    asyncio.run(check())
