import asyncio
import sys
import os

sys.path.append(os.path.abspath('d:/My Project/OnlineshopApp/Ecom_Backend_API'))

from core.database import SessionLocal
from models.support_ticket import SupportTicket
from sqlalchemy import select

async def run():
    async with SessionLocal() as db:
        res = await db.execute(select(SupportTicket))
        tickets = res.scalars().all()
        print("TOTAL TICKETS:", len(tickets))
        for t in tickets:
            print(f"- {t.ticket_number} (Stage: {t.ticket_stage}, Partner: {t.partner_id})")

if __name__ == "__main__":
    asyncio.run(run())
