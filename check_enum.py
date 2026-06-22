import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://postgres:admin@localhost:5432/onlineshopappdb')
    rows = await conn.fetch("SELECT unnest(enum_range(NULL::tickettype))")
    print("TicketType:", [r[0] for r in rows])
    
    rows = await conn.fetch("SELECT unnest(enum_range(NULL::ticketstatus))")
    print("TicketStatus:", [r[0] for r in rows])
    
    rows = await conn.fetch("SELECT unnest(enum_range(NULL::ticketpriority))")
    print("TicketPriority:", [r[0] for r in rows])
    
    rows = await conn.fetch("SELECT unnest(enum_range(NULL::ticketlevel))")
    print("TicketLevel:", [r[0] for r in rows])
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
