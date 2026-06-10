from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.database import get_db
from models.location import Country, State
from schemas.location import Country as CountrySchema, State as StateSchema

router = APIRouter()

@router.get("/countries", response_model=List[CountrySchema])
async def get_countries(db: AsyncSession = Depends(get_db)):
    """Fetch all active countries"""
    result = await db.execute(select(Country).where(Country.is_active == True))
    return result.scalars().all()

@router.get("/countries/{country_id}/states", response_model=List[StateSchema])
async def get_states(country_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch all active states for a specific country"""
    result = await db.execute(select(State).where(State.country_id == country_id, State.is_active == True))
    return result.scalars().all()

@router.get("/states", response_model=List[StateSchema])
async def get_all_states(db: AsyncSession = Depends(get_db)):
    """Fetch all active states across all countries"""
    result = await db.execute(select(State).where(State.is_active == True))
    return result.scalars().all()
