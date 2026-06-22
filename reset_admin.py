import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import select
from models import User
from core.security import get_password_hash

async def reset_super_admin():
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.email == 'superadmin@myntra.com'))
        admin = result.scalar_one_or_none()
        if admin:
            admin.password_hash = get_password_hash("admin123")
            await db.commit()
            print("Successfully reset password for superadmin@myntra.com to 'admin123'")
        else:
            print("Super admin not found.")

if __name__ == "__main__":
    asyncio.run(reset_super_admin())
