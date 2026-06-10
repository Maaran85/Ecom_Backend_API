import asyncio
from sqlalchemy import text
from core.database import engine

async def upgrade_dealers_cin_logo():
    async with engine.begin() as conn:
        print("Adding CIN and Logo columns to dealers table...")
        
        await conn.execute(text("""
            ALTER TABLE dealers 
            ADD COLUMN IF NOT EXISTS cin_number VARCHAR,
            ADD COLUMN IF NOT EXISTS cin_certificate_url VARCHAR,
            ADD COLUMN IF NOT EXISTS company_logo_url VARCHAR
        """))
        print("Columns added successfully.")
        
    print("Migration completed.")

if __name__ == "__main__":
    asyncio.run(upgrade_dealers_cin_logo())
