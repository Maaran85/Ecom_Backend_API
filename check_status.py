import asyncio
from core.database import SessionLocal
from sqlalchemy import select
from models.support_ticket import SupportTicket
from schemas.support_ticket import SupportTicketResponse
from sqlalchemy.orm import selectinload

async def run():
    async with SessionLocal() as db:
        res = await db.execute(select(SupportTicket).options(selectinload(SupportTicket.messages)).where(SupportTicket.id==13))
        t = res.scalar_one_or_none()
        try:
            print(SupportTicketResponse.model_validate(t).model_dump_json())
        except Exception as e:
            print("Validation error:", e)

asyncio.run(run())
