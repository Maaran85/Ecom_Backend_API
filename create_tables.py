import asyncio
from core.database import engine, Base
import models

async def create_tables():
    async with engine.begin() as conn:
        # Create all tables that don't exist yet
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created.")

if __name__ == "__main__":
    asyncio.run(create_tables())
