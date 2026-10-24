from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.database import get_db
from models.location import Country, State, PincodeMaster
from schemas.location import Country as CountrySchema, State as StateSchema, PincodeResponse

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

@router.get("/pincode/{pincode}", response_model=PincodeResponse)
async def get_pincode_details(pincode: str, db: AsyncSession = Depends(get_db)):
    """Fetch location details for a given pincode"""
    # Just grab the first match for the pincode
    result = await db.execute(select(PincodeMaster).where(PincodeMaster.pincode == pincode).limit(1))
    pincode_data = result.scalars().first()
    
    if not pincode_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pincode not found")
        
    # Clean up common post office suffixes to get the actual location name
    location_name = pincode_data.office_name
    if location_name:
        for suffix in [" S.O", " B.O", " H.O"]:
            if location_name.endswith(suffix):
                location_name = location_name[:-len(suffix)]
                
    # Combine actual location and district for the city field, e.g., "Koramangala, Bangalore"
    city_name = f"{location_name}, {pincode_data.district}" if location_name and pincode_data.district and location_name.lower() != pincode_data.district.lower() else (location_name or pincode_data.district)
                
    return PincodeResponse(
        pincode=pincode_data.pincode,
        city=city_name,
        state=pincode_data.state_name,
        latitude=pincode_data.latitude,
        longitude=pincode_data.longitude
    )

import math

def get_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

from models.product import Product
from models.hub import DeliveryHub
from typing import List, Optional
from services.delivery_pricing_service import check_serviceability_full
from schemas.location import ServiceabilityCheckResponse

@router.get("/check-serviceability", response_model=ServiceabilityCheckResponse)
async def check_serviceability(
    pincode: str, 
    product_id: UUID, 
    variant_id: Optional[UUID] = None,
    lat: float = None, 
    long: float = None, 
    db: AsyncSession = Depends(get_db)
):
    """Check if a product can be delivered to a location based on Warehouse, Courier Pincodes, or Hub Radius"""
    res = await check_serviceability_full(
        db=db,
        pincode=pincode,
        product_id=product_id,
        variant_id=variant_id,
        lat=lat,
        long=long
    )
    if res.reason_code == "PRODUCT_NOT_FOUND":
        raise HTTPException(status_code=404, detail=res.message)
    return ServiceabilityCheckResponse(
        is_serviceable=res.is_serviceable,
        serviceable=res.is_serviceable,
        delivery_type=res.delivery_type,
        serviceability_source=res.serviceability_source,
        message=res.message,
        estimated_days=res.estimated_days,
        estimated_delivery_date=res.estimated_delivery_date,
        pincode=res.pincode,
        product_id=res.product_id,
        variant_id=res.variant_id,
        reason_code=res.reason_code,
        delivery_fee=res.delivery_fee,
        warehouse_id=res.warehouse_id,
        locality=res.locality,
        district=res.district,
        city=res.city,
        state=res.state,
        is_interstate=getattr(res, 'is_interstate', False),
        origin_state=getattr(res, 'origin_state', None),
        destination_state=getattr(res, 'destination_state', None)
    )

