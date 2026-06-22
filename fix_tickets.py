import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT id FROM customer_users WHERE phone='9876543211'"))
        cust_user = res.first()
        if cust_user:
            print(f"Fixing tickets to use customer_users.id = {cust_user.id}")
            # Find the user id in the users table with the same phone
            res2 = await conn.execute(text("SELECT id FROM users WHERE phone='9876543211'"))
            user = res2.first()
            if user:
                await conn.execute(text(f"UPDATE support_tickets SET customer_id={cust_user.id} WHERE customer_id={user.id}"))
                await conn.commit()
                print(f"Updated tickets from user_id {user.id} to customer_id {cust_user.id}")
            else:
                print("No user found in users table with that phone")
        else:
            print("CustomerUser not found")

asyncio.run(main())
