import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from sqlalchemy import text

async def main():
    async with SessionLocal() as db:
        result = await db.execute(text("SELECT tgname, tgtype FROM pg_trigger WHERE tgrelid = 'categories'::regclass;"))
        for row in result:
            print(row)

asyncio.run(main())
