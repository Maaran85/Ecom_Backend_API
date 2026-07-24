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
from models.location import ServiceablePincode
from schemas.location import ServiceabilityCheckResponse

@router.get("/check-serviceability", response_model=ServiceabilityCheckResponse)
async def check_serviceability(
    pincode: str, 
    product_id: UUID, 
    lat: float = None, 
    long: float = None, 
    db: AsyncSession = Depends(get_db)
):
    """Check if a product can be delivered to a location based on Courier Pincodes or Hub Radius"""
    
    # Get product and its dealer
    result = await db.execute(select(Product).where(Product.id == product_id).limit(1))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    dealer_id = product.dealer_id
    
    # 1. Check Courier Serviceability (Pincode Whitelist)
    # Check if there's a specific entry for this dealer, or a global entry
    result = await db.execute(
        select(ServiceablePincode)
        .where(
            ServiceablePincode.pincode == pincode,
            ServiceablePincode.is_active == True,
            (ServiceablePincode.dealer_id == dealer_id) | ServiceablePincode.dealer_id.is_(None)
        )
        .limit(1)
    )
    is_courier_serviceable = result.scalars().first() is not None
    
    if is_courier_serviceable:
        return ServiceabilityCheckResponse(
            is_serviceable=True,
            delivery_type="courier",
            message="Delivery available in 3-5 business days.",
            estimated_days=4
        )
        
    # 2. Check Local Hub Serviceability (Radius)
    if lat is not None and long is not None:
        result = await db.execute(
            select(DeliveryHub)
            .where(
                DeliveryHub.dealer_id == dealer_id,
                DeliveryHub.is_active == True,
                DeliveryHub.lat_long != None,
                DeliveryHub.max_delivery_radius != None
            )
        )
        hubs = result.scalars().all()
        
        for hub in hubs:
            try:
                h_lat, h_lon = map(float, hub.lat_long.split(","))
                distance = get_distance_km(lat, long, h_lat, h_lon)
                if distance <= hub.max_delivery_radius:
                    return ServiceabilityCheckResponse(
                        is_serviceable=True,
                        delivery_type="local_hub",
                        message="Same-day or next-day local delivery available.",
                        estimated_days=1
                    )
            except Exception:
                continue # Skip invalid lat_long formats
                
    return ServiceabilityCheckResponse(
        is_serviceable=False,
        message="Sorry, this product cannot be delivered to your location.",
    )
