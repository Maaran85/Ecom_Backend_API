"""
Address management router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from core.database import get_db
from core.permissions import get_current_active_user
from models import User, Address, CustomerUser
from schemas.address import AddressCreate, AddressUpdate, Address as AddressSchema

router = APIRouter()

@router.post("", response_model=AddressSchema, status_code=status.HTTP_201_CREATED)
async def create_address(
    address_data: AddressCreate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new address"""
    
    # If this is set as default, unset other defaults
    if address_data.is_default:
        result = await db.execute(
            select(Address).where(
                Address.customer_id == current_user.id,
                Address.is_default == True
            )
        )
        existing_defaults = result.scalars().all()
        for addr in existing_defaults:
            addr.is_default = False
    
    address = Address(
        customer_id=current_user.id,
        **address_data.model_dump()
    )
    
    db.add(address)
    await db.flush()
    new_address_id = address.id
    await db.commit()
    
    # Reload with relationship
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(Address.id == new_address_id)
    )
    address = result.scalar_one()
    if address.state_rel:
        address.state_name = address.state_rel.name
        address.state_code = address.state_rel.state_code
    
    return address

@router.get("", response_model=list[AddressSchema])
async def list_addresses(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all user addresses"""
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(Address.customer_id == current_user.id)
    )
    addresses = result.scalars().all()
    
    for addr in addresses:
        if addr.state_rel:
            addr.state_name = addr.state_rel.name
            addr.state_code = addr.state_rel.state_code
            
    return addresses

@router.get("/{address_id}", response_model=AddressSchema)
async def get_address(
    address_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific address"""
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(
            Address.id == address_id,
            Address.customer_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
        
    if address.state_rel:
        address.state_name = address.state_rel.name
        address.state_code = address.state_rel.state_code
    
    return address

@router.put("/{address_id}", response_model=AddressSchema)
async def update_address(
    address_id: int,
    address_data: AddressUpdate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update address"""
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(
            Address.id == address_id,
            Address.customer_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    # If setting as default, unset other defaults
    if address_data.is_default:
        result = await db.execute(
            select(Address).where(
                Address.customer_id == current_user.id,
                Address.is_default == True,
                Address.id != address_id
            )
        )
        existing_defaults = result.scalars().all()
        for addr in existing_defaults:
            addr.is_default = False
    
    # Update fields
    for field, value in address_data.model_dump(exclude_unset=True).items():
        setattr(address, field, value)
    
    await db.commit()
    
    # Reload with relationship to ensure correct state data
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(Address.id == address_id)
    )
    address = result.scalar_one()
    if address.state_rel:
        address.state_name = address.state_rel.name
        address.state_code = address.state_rel.state_code
    
    return address

@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete address"""
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.customer_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    await db.delete(address)
    await db.commit()
    
    return None

@router.put("/{address_id}/set-default", response_model=AddressSchema)
async def set_default_address(
    address_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Set address as default"""
    result = await db.execute(
        select(Address).options(selectinload(Address.state_rel)).where(
            Address.id == address_id,
            Address.customer_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()
    
    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )
    
    # Unset other defaults
    result = await db.execute(
        select(Address).where(
            Address.customer_id == current_user.id,
            Address.is_default == True
        )
    )
    existing_defaults = result.scalars().all()
    for addr in existing_defaults:
        addr.is_default = False
    
    address.is_default = True
    await db.commit()
    
    if address.state_rel:
        address.state_name = address.state_rel.name
        address.state_code = address.state_rel.state_code
    
    return address
