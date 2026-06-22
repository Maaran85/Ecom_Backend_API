import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://postgres:admin@localhost:5432/onlineshopappdb')
    rows = await conn.fetch("SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_name = 'support_tickets';")
    for r in rows:
        print(f"{r[0]}: {r[1]} ({r[2]})")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
