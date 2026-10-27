import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

from core.database import SessionLocal
from models import FeeConfiguration
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(FeeConfiguration))
        for fc in res.scalars():
            print(f"Key: '{fc.key}', value: {fc.value}, fee_type: {fc.fee_type}, gst_rate: {fc.gst_rate}, is_gst_applicable: {fc.is_gst_applicable}")

if __name__ == "__main__":
    asyncio.run(main())
