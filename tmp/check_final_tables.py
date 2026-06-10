import asyncio
from sqlalchemy import text
from core.database import SessionLocal, engine

async def check():
    async with engine.connect() as conn:
        for t in ['wishlist_items', 'reviews', 'notifications']:
            res = await conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}'"))
            cols = [r[0] for r in res.fetchall()]
            print(f"{t}: {cols}")

if __name__ == "__main__":
    asyncio.run(check())
