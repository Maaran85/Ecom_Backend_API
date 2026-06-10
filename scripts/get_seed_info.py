import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import select
from models import Dealer, TaxRule

async def get_info():
    async with SessionLocal() as db:
        d = await db.execute(select(Dealer.id).limit(1))
        t = await db.execute(select(TaxRule.id).limit(1))
        print(f"DEALER_ID: {d.scalar()}")
        print(f"TAXRULE_ID: {t.scalar()}")

if __name__ == "__main__":
    asyncio.run(get_info())
