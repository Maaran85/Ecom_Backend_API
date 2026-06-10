
import asyncio
from sqlalchemy import select
from core.database import engine, AsyncSession
from models.location import Country, State

async def seed_locations():
    async with AsyncSession(engine) as session:
        # Check if India exists
        result = await session.execute(select(Country).where(Country.name == 'India'))
        india = result.scalar_one_or_none()
        
        if not india:
            india = Country(name='India', iso_code='IN', is_active=True)
            session.add(india)
            await session.flush()
            print("Added India")
        else:
            india.is_active = True
            print("India already exists, ensured active")

        states = [
            "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
            "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
            "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
            "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
            "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
            "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
            "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
            "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"
        ]

        for state_name in states:
            res = await session.execute(
                select(State).where(State.name == state_name, State.country_id == india.id)
            )
            if not res.scalar_one_or_none():
                state = State(name=state_name, country_id=india.id, is_active=True)
                session.add(state)
                print(f"Added state: {state_name}")
            else:
                print(f"State exists: {state_name}")

        await session.commit()
    print("Seeding completed.")

if __name__ == "__main__":
    asyncio.run(seed_locations())
