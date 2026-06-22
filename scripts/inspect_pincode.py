import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models.location import PincodeMaster
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(PincodeMaster).limit(20))
        for r in res.scalars():
            print(f"Pincode: {r.pincode}, Office: {r.office_name}, District: {r.district}, State: {r.state_name}")

if __name__ == "__main__":
    asyncio.run(main())
