from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.database import get_db
from core.permissions import get_current_active_user, get_current_user_optional
from models.user import User, UserRole

from . import schemas
from . import services

auction_router = APIRouter()

@auction_router.get("/auctions", response_model=List[schemas.AuctionItemResponse])
async def list_auctions(
    skip: int = 0, 
    limit: int = 100, 
    product_id: Optional[UUID] = None,
    status: Optional[schemas.AuctionStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    return await services.get_auctions(db, skip=skip, limit=limit, product_id=product_id, status=status, user=current_user)

@auction_router.get("/auctions/{auction_id}", response_model=schemas.AuctionItemDetailResponse)
async def get_auction_detail(auction_id: UUID, db: AsyncSession = Depends(get_db)):
    return await services.get_auction(db, auction_id=auction_id)

@auction_router.post("/auctions", response_model=schemas.AuctionItemResponse)
async def create_auction(
    auction_in: schemas.AuctionItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.DEALER]:
        raise HTTPException(status_code=403, detail="Only admins or dealers can create auctions")
    
    # Check dealer has auction feature enabled
    if current_user.role == UserRole.DEALER:
        from models.dealer import Dealer
        from sqlalchemy.future import select as sa_select
        from sqlalchemy.ext.asyncio import AsyncSession
        dealer_res = await db.execute(sa_select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = dealer_res.scalars().first()
        if not dealer or not dealer.is_auction_enabled:
            raise HTTPException(status_code=403, detail="Auction feature is not enabled for your account. Please contact admin.")
    
    auction = await services.create_auction(db, auction_in, user=current_user)
    return auction

@auction_router.post("/auctions/{auction_id}/bids", response_model=schemas.AuctionBidResponse)
async def place_bid(
    auction_id: UUID,
    bid_in: schemas.AuctionBidCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    # Only customers can place bids, or dealers too if they want
    if current_user.role == UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admins cannot place bids")
        
    bid = await services.place_bid(db, auction_id, bid_in, user=current_user)
    return bid

@auction_router.put("/auctions/{auction_id}/publish", response_model=schemas.AuctionItemResponse)
async def publish_auction(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.DEALER]:
        raise HTTPException(status_code=403, detail="Only admins or dealers can publish auctions")
        
    auction = await services.publish_auction(db, auction_id, user=current_user)
    return auction

@auction_router.put("/auctions/{auction_id}/cancel", response_model=schemas.AuctionItemResponse)
async def cancel_auction(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role not in [UserRole.ADMIN, UserRole.DEALER]:
        raise HTTPException(status_code=403, detail="Only admins or dealers can cancel auctions")
        
    auction = await services.cancel_auction(db, auction_id, user=current_user)
    return auction

@auction_router.get("/auctions/{auction_id}/registration-status", response_model=schemas.RegistrationStatusResponse)
async def get_registration_status(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Check if the current customer is registered for a specific auction."""
    return await services.get_registration_status(db, auction_id, user=current_user)

@auction_router.post("/auctions/{auction_id}/register", response_model=schemas.AuctionRegistrationResponse)
async def register_for_auction(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Register the current customer for an auction (FREE: instant, PAID: deducts deposit from wallet)."""
    return await services.register_for_auction(db, auction_id, user=current_user)

@auction_router.post("/auctions/{auction_id}/finalize")
async def finalize_auction(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Finalize an auction (Mark as COMPLETED and generate Orders for winners).
    Only Admins or the Dealer who owns the auction can finalize it.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.DEALER]:
        raise HTTPException(status_code=403, detail="Only admins or dealers can finalize auctions")
        
    return await services.finalize_auction(db, auction_id)
