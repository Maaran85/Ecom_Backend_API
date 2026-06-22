import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models.product import Category
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        result = await db.execute(select(Category))
        cats = result.scalars().all()
        for c in cats:
            print(f"{c.id}: {c.name} (parent: {c.parent_id})")

asyncio.run(main())
