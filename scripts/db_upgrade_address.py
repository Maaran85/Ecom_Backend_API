import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal, engine, Base
import models
from sqlalchemy import text

async def main():
    print("Creating new tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created.")
        
    print("Altering addresses table...")
    async with SessionLocal() as db:
        # Check if columns exist
        try:
            await db.execute(text("ALTER TABLE addresses ADD COLUMN latitude VARCHAR"))
            print("Added latitude")
        except Exception as e:
            print("latitude exists or error:", e)
            
        try:
            await db.execute(text("ALTER TABLE addresses ADD COLUMN longitude VARCHAR"))
            print("Added longitude")
        except Exception as e:
            print("longitude exists or error:", e)
            
        await db.commit()
    print("Done")

if __name__ == "__main__":
    asyncio.run(main())
