import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

from core.database import SessionLocal
from models.tds_configuration import TDSConfiguration
from sqlalchemy import select

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(TDSConfiguration))
        for tc in res.scalars():
            print(f"TDS ID {tc.id}: org_type={tc.organization_type}, rate_with_pan={tc.tds_rate_with_pan}, rate_without_pan={tc.tds_rate_without_pan}, exemption_with_pan={tc.exemption_limit_with_pan}, active={tc.is_active}")

if __name__ == "__main__":
    asyncio.run(main())
