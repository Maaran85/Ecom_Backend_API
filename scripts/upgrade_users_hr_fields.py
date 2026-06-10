
import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_users_hr_fields():
    async with engine.begin() as conn:
        print("Checking for employee_id and shift_type columns in users table...")
        
        await conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS employee_id VARCHAR UNIQUE,
            ADD COLUMN IF NOT EXISTS shift_type VARCHAR
        """))
        print("Columns ensured.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_users_hr_fields())
