import asyncio
import asyncpg
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.config import settings

async def check():
    url = str(settings.SQLALCHEMY_DATABASE_URI).replace('+asyncpg', '')
    conn = await asyncpg.connect(url)
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name='delivery_riders' ORDER BY ordinal_position"
    )
    print([c['column_name'] for c in cols])
    await conn.close()

asyncio.run(check())
