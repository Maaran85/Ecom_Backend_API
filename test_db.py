import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from core.database import SessionLocal
from sqlalchemy import text

async def main():
    async with SessionLocal() as db:
        res = await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'dealers';"))
        print([r[0] for r in res.fetchall()])

if __name__ == "__main__":
    asyncio.run(main())
