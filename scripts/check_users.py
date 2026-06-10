import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from models import User, Dealer
from sqlalchemy import select

async def check():
    async with SessionLocal() as db:
        users = await db.execute(select(User.id, User.email, User.role))
        print("USERS:", users.all())
        dealers = await db.execute(select(Dealer.id, Dealer.user_id, Dealer.business_name))
        print("DEALERS:", dealers.all())

if __name__ == "__main__":
    asyncio.run(check())
