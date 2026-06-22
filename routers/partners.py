from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from core.database import get_db
from models.user import User
from models.partner import Partner
from schemas.partner import PartnerCreate, PartnerUpdate, PartnerResponse
from core.permissions import get_current_user

router = APIRouter()

from models.user import UserRole

def require_super_admin(user: User = Depends(get_current_user)):
    if user.role != UserRole.SUPER_ADMIN and user.role != "SUPER_ADMIN" and user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only Super Admins can access partners (found role {user.role})"
        )
    return user

@router.get("/", response_model=List[PartnerResponse])
async def get_partners(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_super_admin)):
    result = await db.execute(select(Partner))
    return result.scalars().all()

@router.post("/", response_model=PartnerResponse, status_code=status.HTTP_201_CREATED)
async def create_partner(
    partner_in: PartnerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin)
):
    if partner_in.license_key:
        result = await db.execute(select(Partner).filter(Partner.license_key == partner_in.license_key))
        existing = result.scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="License key already in use")
            
    partner = Partner(**partner_in.dict())
    db.add(partner)
    await db.commit()
    await db.refresh(partner)
    return partner

@router.put("/{partner_id}", response_model=PartnerResponse)
async def update_partner(
    partner_id: int,
    partner_in: PartnerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin)
):
    result = await db.execute(select(Partner).filter(Partner.id == partner_id))
    partner = result.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
        
    if partner_in.license_key and partner_in.license_key != partner.license_key:
        res2 = await db.execute(select(Partner).filter(Partner.license_key == partner_in.license_key))
        existing = res2.scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="License key already in use")
            
    for key, value in partner_in.dict(exclude_unset=True).items():
        setattr(partner, key, value)
        
    await db.commit()
    await db.refresh(partner)
    return partner

@router.delete("/{partner_id}", response_model=dict)
async def delete_partner(
    partner_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin)
):
    result = await db.execute(select(Partner).filter(Partner.id == partner_id))
    partner = result.scalars().first()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
        
    from models.dealer import Dealer
    dealers_result = await db.execute(select(Dealer).where(Dealer.is_deleted == False).filter(Dealer.partner_id == partner_id))
    dealers = dealers_result.scalars().all()
    
    if dealers:
        # Instead of hard delete, just deactivate
        partner.is_active = False
        await db.commit()
        return {"message": "Partner deactivated successfully because dealers are associated"}
    else:
        # Hard delete if no dealers exist
        await db.delete(partner)
        await db.commit()
        return {"message": "Partner deleted successfully"}
