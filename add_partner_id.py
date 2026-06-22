import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from core.config import settings

async def main():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text('ALTER TABLE users ADD COLUMN partner_id INTEGER REFERENCES partners(id) ON DELETE SET NULL;'))
        print('Column partner_id added successfully.')
    await engine.dispose()

asyncio.run(main())
