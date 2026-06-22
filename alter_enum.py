import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import text
from core.database import SessionLocal

async def check():
    async with SessionLocal() as db:
        res = await db.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'userrole'"))
        labels = [r[0] for r in res.fetchall()]
        print("Existing labels:", labels)
        
        for r in ['PARTNER_HELPDESK_OPERATOR', 'PARTNER_HELPDESK_SUPERVISOR', 'PARTNER_HELPDESK_MANAGER']:
            if r not in labels:
                try:
                    await db.execute(text(f"ALTER TYPE userrole ADD VALUE '{r}';"))
                    await db.commit()
                    print(f"Added {r}")
                except Exception as e:
                    print(f"Error adding {r}:", e)
                    await db.rollback()

if __name__ == "__main__":
    asyncio.run(check())
