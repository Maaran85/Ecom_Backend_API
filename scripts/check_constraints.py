import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from sqlalchemy import text

async def main():
    async with SessionLocal() as db:
        result = await db.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'products_tax_rule_id_fkey';"))
        for row in result:
            print(row)
        
        result2 = await db.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'products_category_id_fkey';"))
        for row in result2:
            print(row)
            
        result3 = await db.execute(text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'products'::regclass;"))
        for row in result3:
            print(row)

asyncio.run(main())
