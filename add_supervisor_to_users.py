import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from core.config import settings

async def alter_users_table():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=True)
    async with engine.begin() as conn:
        try:
            # Check if column exists
            result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='supervisor_id'"))
            if not result.scalar():
                print("Adding supervisor_id column to users table...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN supervisor_id INTEGER REFERENCES users(id)"))
                print("Successfully added supervisor_id column.")
            else:
                print("Column supervisor_id already exists.")
        except Exception as e:
            print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(alter_users_table())
