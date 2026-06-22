import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import text
from core.database import SessionLocal

async def remove_enum():
    async with SessionLocal() as db:
        print("Updating old partner_helpdesk roles to partner_helpdesk_operator...")
        try:
            # We must cast the string to userrole
            await db.execute(text("UPDATE users SET role = 'partner_helpdesk_operator'::userrole WHERE role::text = 'partner_helpdesk' OR role::text = 'PARTNER_HELPDESK';"))
            await db.commit()
            print("Users updated successfully.")
        except Exception as e:
            print("Error updating users:", e)
            await db.rollback()
            
        print("Removing 'partner_helpdesk' from pg_enum...")
        try:
            # Deleting from pg_enum directly is possible in Postgres if the value is not used
            await db.execute(text("DELETE FROM pg_enum WHERE enumlabel IN ('partner_helpdesk', 'PARTNER_HELPDESK') AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole');"))
            await db.commit()
            print("Enum values removed from DB successfully.")
        except Exception as e:
            print("Error removing enum from pg_enum:", e)
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(remove_enum())
