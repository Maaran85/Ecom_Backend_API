from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from core.database import get_db
from core.permissions import get_current_active_user
from models import User, Dealer, DealerFollow, CustomerUser

router = APIRouter()

class DealerFollowResponse(BaseModel):
    dealer_id: int
    dealer_name: str
    followed_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/dealers/{dealer_id}/follow", status_code=status.HTTP_201_CREATED)
async def follow_dealer(
    dealer_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Follow a dealer"""
    
    # Check if dealer exists
    dealer_result = await db.execute(select(Dealer).where(Dealer.id == dealer_id))
    dealer = dealer_result.scalar_one_or_none()
    
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    # Check if already following
    existing_follow = await db.execute(
        select(DealerFollow).where(
            DealerFollow.customer_id == current_user.id,
            DealerFollow.dealer_id == dealer_id
        )
    )
    if existing_follow.scalar_one_or_none():
        return {"message": "Already following this dealer"}
        
    # Create follow
    follow = DealerFollow(customer_id=current_user.id, dealer_id=dealer_id)
    db.add(follow)
    await db.commit()
    
    return {"message": "Successfully followed dealer"}

@router.delete("/dealers/{dealer_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_dealer(
    dealer_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Unfollow a dealer"""
    
    result = await db.execute(
        select(DealerFollow).where(
            DealerFollow.customer_id == current_user.id,
            DealerFollow.dealer_id == dealer_id
        )
    )
    follow = result.scalar_one_or_none()
    
    if not follow:
        raise HTTPException(status_code=404, detail="Not following this dealer")
        
    await db.delete(follow)
    await db.commit()
    
    return None

@router.get("/user/following", response_model=List[DealerFollowResponse])
async def list_following(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List dealers followed by current user"""
    
    result = await db.execute(
        select(DealerFollow, Dealer.store_name)
        .join(Dealer, Dealer.id == DealerFollow.dealer_id)
        .where(DealerFollow.customer_id == current_user.id)
    )
    
    following = []
    for follow, store_name in result.all():
        following.append(DealerFollowResponse(
            dealer_id=follow.dealer_id,
            dealer_name=store_name,
            followed_at=follow.created_at
        ))
        
    return following
