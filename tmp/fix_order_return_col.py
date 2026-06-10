import asyncio
from sqlalchemy import text
from core.database import SessionLocal, engine

async def migrate():
    async with engine.connect() as conn:
        print("Renaming user_id to customer_id in order_returns...")
        try:
            await conn.execute(text("ALTER TABLE order_returns RENAME COLUMN user_id TO customer_id"))
            await conn.commit()
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
