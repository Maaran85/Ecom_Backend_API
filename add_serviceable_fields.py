import asyncio
from sqlalchemy import text
from core.database import engine, Base
import models

async def migrate():
    async with engine.begin() as conn:
        print("Creating new tables...")
        await conn.run_sync(Base.metadata.create_all)
        
        print("Adding max_delivery_radius to delivery_hubs...")
        try:
            await conn.execute(text("ALTER TABLE delivery_hubs ADD COLUMN max_delivery_radius FLOAT"))
            print("Added max_delivery_radius.")
        except Exception as e:
            print(f"Error (maybe already exists): {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
