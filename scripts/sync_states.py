import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models.location import Country, State, PincodeMaster
from sqlalchemy import select, delete, text

async def main():
    async with SessionLocal() as db:
        print("Checking for India in countries table...")
        result = await db.execute(select(Country).where(Country.name == 'India'))
        country = result.scalars().first()
        
        if not country:
            print("Creating 'India' country record...")
            country = Country(name='India', iso_code='IN', phone_code='+91')
            db.add(country)
            await db.commit()
            await db.refresh(country)
            
        country_id = country.id
            
        print("Clearing foreign key references...")
        try:
            await db.execute(text("UPDATE delivery_hubs SET state_id = NULL"))
        except Exception as e:
            print("No delivery_hubs table or state_id:", e)
            
        print("Clearing existing states table...")
        await db.execute(delete(State))
        await db.commit()
        
        print("Fetching distinct state names from pincode_master...")
        result = await db.execute(select(PincodeMaster.state_name).distinct().where(PincodeMaster.state_name != None))
        state_names = result.scalars().all()
        
        print(f"Found {len(state_names)} distinct states. Inserting...")
        for name in state_names:
            if name.strip():
                new_state = State(name=name.strip(), country_id=country_id, is_active=True)
                db.add(new_state)
                
        await db.commit()
        print("Sync complete!")

if __name__ == "__main__":
    asyncio.run(main())
