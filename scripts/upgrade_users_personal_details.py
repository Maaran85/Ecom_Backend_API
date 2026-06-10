
import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_users_personal_details():
    async with engine.begin() as conn:
        print("Adding personal detail columns to users table...")
        
        await conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS phone_number VARCHAR,
            ADD COLUMN IF NOT EXISTS dob VARCHAR,
            ADD COLUMN IF NOT EXISTS address VARCHAR,
            ADD COLUMN IF NOT EXISTS aadhaar_number VARCHAR,
            ADD COLUMN IF NOT EXISTS emergency_contact VARCHAR,
            ADD COLUMN IF NOT EXISTS photo_url VARCHAR,
            ADD COLUMN IF NOT EXISTS aadhaar_image VARCHAR
        """))
        print("Columns added successfully.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_users_personal_details())
