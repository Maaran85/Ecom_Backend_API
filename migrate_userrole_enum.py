import asyncio
from core.database import engine
from sqlalchemy import text

async def migrate_enum():
    print("Connecting to database...")
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        print("Adding PARTNER_HELPDESK...")
        try:
            await conn.execute(text("ALTER TYPE userrole ADD VALUE 'PARTNER_HELPDESK'"))
        except Exception as e:
            print("Failed or already exists:", str(e))
        
        print("Adding PARTNER_BACKOFFICE...")
        try:
            await conn.execute(text("ALTER TYPE userrole ADD VALUE 'PARTNER_BACKOFFICE'"))
        except Exception as e:
            print("Failed or already exists:", str(e))
            
        print("Enum migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_enum())
