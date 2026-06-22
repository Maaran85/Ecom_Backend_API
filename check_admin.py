import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import select
from models import User
from core.security import verify_password

async def check_admin():
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email.like('%admin%')))
        admins = result.scalars().all()
        for admin in admins:
            print(f"Found admin: {admin.email}, role: {admin.role}")
            # Try some common passwords
            passwords_to_try = ["admin123", "password", "123456", "admin", "superadmin"]
            for p in passwords_to_try:
                if verify_password(p, admin.password_hash):
                    print(f"--> Password for {admin.email} is: {p}")
                    break

if __name__ == "__main__":
    asyncio.run(check_admin())
