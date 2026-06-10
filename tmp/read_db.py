import asyncio
import os
import sys

# Change directory to the root of the Backend API so .env can be found
os.chdir(r"f:\My Project\OnlineshopApp\Ecom_Backend_API")
sys.path.append(os.getcwd())

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import SessionLocal
from models import Category, Dealer

# Fix asyncio in windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def read_data():
    try:
        async with SessionLocal() as db:
            cats_res = await db.execute(select(Category))
            cats = cats_res.scalars().all()
            print("Categories:")
            for c in cats:
                print(f"ID: {c.id}, Name: {c.name}, ParentID: {c.parent_id}")

            dealers_res = await db.execute(select(Dealer))
            dealers = dealers_res.scalars().all()
            print("Dealers:")
            for d in dealers:
                print(f"ID: {d.id}, Business: {d.business_name}, UserID: {d.user_id}")
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(read_data())
