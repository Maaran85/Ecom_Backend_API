import asyncio
import sys
import os
from dotenv import load_dotenv

# Load env variables from backend/.env
load_dotenv(os.path.abspath(os.path.join(os.getcwd(), 'backend', '.env')))

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'backend')))

from core.database import SessionLocal
from sqlalchemy import select
from models.location import State

async def check_states():
    async with SessionLocal() as session:
        result = await session.execute(select(State))
        states = result.scalars().all()
        print(f"Found {len(states)} states in total.")
        active_states = [s for s in states if s.is_active]
        print(f"Found {len(active_states)} ACTIVE states.")
        
if __name__ == "__main__":
    asyncio.run(check_states())
