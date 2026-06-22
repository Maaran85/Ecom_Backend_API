import asyncio
from sqlalchemy import text
from core.database import SessionLocal

async def fix():
    async with SessionLocal() as db:
        await db.execute(text('ALTER TABLE support_tickets DROP CONSTRAINT IF EXISTS support_tickets_user_id_fkey;'))
        try:
            await db.execute(text('ALTER TABLE support_tickets ADD CONSTRAINT support_tickets_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES customer_users(id);'))
        except Exception as e:
            pass # might already exist
        await db.commit()
        print('Fixed DB constraint')

asyncio.run(fix())
