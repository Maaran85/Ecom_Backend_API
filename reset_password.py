import asyncio
from core.database import SessionLocal
from models.user import User
from core.security import get_password_hash
from sqlalchemy import select

async def run():
    async with SessionLocal() as db:
        u = (await db.execute(select(User).where(User.email=='dealer@myntra.com'))).scalar_one()
        u.password_hash = get_password_hash('dealer123')
        await db.commit()
        print('Password updated to dealer123')

asyncio.run(run())
