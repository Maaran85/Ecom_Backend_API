import asyncio
import sys
import os
import json

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models.product import Category
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        result = await db.execute(select(Category))
        cats = result.scalars().all()
        data = [{"id": c.id, "name": c.name, "parent_id": c.parent_id} for c in cats]
        with open("categories.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

asyncio.run(main())
