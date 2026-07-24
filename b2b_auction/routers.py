from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from core.database import get_db
from core.permissions import get_current_active_user, get_current_user_optional, get_current_user
from models.user import User, UserRole
from models.dealer import Dealer
from models.partner import Partner

from . import schemas
from . import services
from services.file_upload import FileUploadService as UploadService

router = APIRouter(
    prefix="/b2b-auctions",
    tags=["B2B Auctions"],
)

async def get_current_dealer(user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Dealer:
    if user.role != UserRole.DEALER:
        raise HTTPException(status_code=403, detail="Only Dealers can perform this action")
    from sqlalchemy.future import select as sa_select
    dealer_res = await db.execute(sa_select(Dealer).where(Dealer.user_id == user.id))
    dealer = dealer_res.scalars().first()
    if not dealer:
        raise HTTPException(status_code=403, detail="Dealer profile not found")
    return dealer

async def get_current_partner(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only Partners or Admins can perform this action")
    if user.partner_id:
        from sqlalchemy.future import select
        result = await db.execute(select(Partner).filter(Partner.id == user.partner_id))
        partner = result.scalars().first()
        if not partner:
            raise HTTPException(status_code=403, detail="Partner profile not found")
        return partner
    return None

@router.get("/", response_model=List[schemas.B2BAuctionItemResponse])
async def list_auctions(
    skip: int = 0, 
    limit: int = 100, 
    b2b_product_id: Optional[UUID] = Query(None, description="Filter by b2b product"),
    status: Optional[schemas.B2BAuctionStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    dealer = None
    if current_user and current_user.role == UserRole.DEALER:
        from sqlalchemy.future import select as sa_select
        dealer_res = await db.execute(sa_select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = dealer_res.scalars().first()

    return await services.get_auctions(db, skip=skip, limit=limit, b2b_product_id=b2b_product_id, status=status, dealer=dealer)

@router.get("/{auction_id}", response_model=schemas.B2BAuctionItemResponse)
async def get_auction_detail(
    auction_id: UUID, 
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    dealer = None
    if current_user and current_user.role == UserRole.DEALER:
        from sqlalchemy.future import select as sa_select
        dealer_res = await db.execute(sa_select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = dealer_res.scalars().first()
    return await services.get_auction(db, auction_id=auction_id, dealer=dealer)

@router.post("/", response_model=schemas.B2BAuctionItemResponse)
async def create_auction(
    auction_in: schemas.B2BAuctionItemCreate,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner = Depends(get_current_partner)
):
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
    
    return await services.create_auction(db, auction_in, partner_id=creator_partner_id)

@router.put("/{auction_id}", response_model=schemas.B2BAuctionItemResponse)
async def update_auction(
    auction_id: UUID,
    auction_in: schemas.B2BAuctionItemUpdate,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner = Depends(get_current_partner)
):
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
    
    return await services.update_auction(db, auction_id, auction_in, partner_id=creator_partner_id)

@router.post("/{auction_id}/bids", response_model=schemas.B2BAuctionBidResponse)
async def place_bid(
    auction_id: UUID,
    bid_in: schemas.B2BAuctionBidCreate,
    db: AsyncSession = Depends(get_db),
    dealer: Dealer = Depends(get_current_dealer)
):
    return await services.place_bid(db, auction_id, bid_in, dealer=dealer)

@router.put("/{auction_id}/publish", response_model=schemas.B2BAuctionItemResponse)
async def publish_auction(
    auction_id: UUID,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner = Depends(get_current_partner)
):
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.publish_auction(db, auction_id, partner_id=creator_partner_id)

@router.put("/{auction_id}/cancel", response_model=schemas.B2BAuctionItemResponse)
async def cancel_auction(
    auction_id: UUID,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner = Depends(get_current_partner)
):
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.cancel_auction(db, auction_id, partner_id=creator_partner_id)

@router.delete("/{auction_id}")
async def delete_auction(
    auction_id: UUID,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner = Depends(get_current_partner)
):
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.delete_auction(db, auction_id, partner_id=creator_partner_id)

@router.get("/{auction_id}/registration-status")
async def get_registration_status(
    auction_id: UUID,
    db: AsyncSession = Depends(get_db),
    dealer: Dealer = Depends(get_current_dealer)
):
    """Check if the current dealer is registered for a specific auction."""
    return await services.get_registration_status(db, auction_id, dealer=dealer)

@router.post("/{auction_id}/register", response_model=schemas.B2BAuctionRegistrationResponse)
async def register_for_auction(
    auction_id: UUID,
    reg_in: schemas.B2BAuctionRegistrationCreate,
    db: AsyncSession = Depends(get_db),
    dealer: Dealer = Depends(get_current_dealer)
):
    """Register for a B2B auction."""
    return await services.register_for_auction(db, auction_id, reg_in, dealer=dealer)

@router.post("/{auction_id}/finalize", response_model=List[schemas.B2BOrderResponse])
async def finalize_auction(
    auction_id: UUID,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    """Finalize auction and generate B2B orders."""
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
    return await services.finalize_auction_orders(db, auction_id, partner_id=creator_partner_id)


# ----------------- B2B Products Routes -----------------

product_router = APIRouter(
    prefix="/b2b-products",
    tags=["B2B Products"],
)

@product_router.post("/upload-image", response_model=dict)
async def upload_b2b_product_image(
    file: UploadFile = File(...),
    current_partner: Partner = Depends(get_current_partner)
):
    """Upload B2B product image"""
    path = await UploadService.upload_image(file, "b2b_products")
    return {"path": path}

@product_router.get("/", response_model=List[schemas.B2BProductResponse])
async def list_b2b_products(
    partner_id: int = Query(None, description="Filter by partner"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """Get all B2B products (public or dealer facing)"""
    return await services.get_b2b_products(db, partner_id=partner_id, skip=skip, limit=limit)

@product_router.get("/{product_id}", response_model=schemas.B2BProductResponse)
async def get_b2b_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific B2B product"""
    return await services.get_b2b_product(db, product_id)

@product_router.post("/", response_model=schemas.B2BProductResponse)
async def create_b2b_product(
    product_in: schemas.B2BProductCreate,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    """Create a B2B product (Partner or Admin)"""
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.create_b2b_product(db, product_in, creator_partner_id)

@product_router.put("/{product_id}", response_model=schemas.B2BProductResponse)
async def update_b2b_product(
    product_id: UUID,
    product_in: schemas.B2BProductUpdate,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    """Update a B2B product"""
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.update_b2b_product(db, product_id, product_in, creator_partner_id)

@product_router.delete("/{product_id}")
async def delete_b2b_product(
    product_id: UUID,
    partner_id: int = Query(None, description="Required for Admins to specify which partner"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    """Delete a B2B product"""
    creator_partner_id = current_partner.id if current_partner else partner_id
    if not creator_partner_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
        
    return await services.delete_b2b_product(db, product_id, creator_partner_id)

# ----------------- B2B Orders Routes -----------------

order_router = APIRouter(
    prefix="/b2b-orders",
    tags=["B2B Orders"],
)

@order_router.get("/partner", response_model=List[schemas.B2BOrderResponse])
async def list_partner_b2b_orders(
    status: Optional[schemas.B2BOrderStatus] = None,
    skip: int = 0,
    limit: int = 100,
    partner_id: int = Query(None, description="Required for Admins"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    p_id = current_partner.id if current_partner else partner_id
    if not p_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
    return await services.get_partner_b2b_orders(db, partner_id=p_id, status=status, skip=skip, limit=limit)

@order_router.get("/dealer", response_model=List[schemas.B2BOrderResponse])
async def list_dealer_b2b_orders(
    status: Optional[schemas.B2BOrderStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    dealer: Dealer = Depends(get_current_dealer)
):
    return await services.get_dealer_b2b_orders(db, dealer_id=dealer.id, status=status, skip=skip, limit=limit)

@order_router.post("/dealer/{order_id}/pay", response_model=schemas.B2BOrderResponse)
async def pay_dealer_b2b_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    dealer: Dealer = Depends(get_current_dealer)
):
    return await services.pay_b2b_order(db, order_id=order_id, dealer_id=dealer.id)

@order_router.get("/{order_id}", response_model=schemas.B2BOrderResponse)
async def get_b2b_order_detail(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    dealer = None
    p_id = None
    if current_user.role == UserRole.DEALER:
        from sqlalchemy.future import select as sa_select
        res = await db.execute(sa_select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = res.scalars().first()
    elif current_user.partner_id:
        p_id = current_user.partner_id
    return await services.get_b2b_order(db, order_id, dealer=dealer, partner_id=p_id)

@order_router.put("/{order_id}/dispatch", response_model=schemas.B2BOrderResponse)
async def dispatch_b2b_order(
    order_id: UUID,
    update_in: schemas.B2BOrderUpdate,
    partner_id: int = Query(None, description="Required for Admins"),
    db: AsyncSession = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
    user: User = Depends(get_current_user)
):
    p_id = current_partner.id if current_partner else partner_id
    if not p_id:
        raise HTTPException(status_code=400, detail="partner_id must be provided")
    if not update_in.courier_company or not update_in.tracking_number:
        raise HTTPException(status_code=400, detail="courier_company and tracking_number required")
    return await services.update_b2b_order_dispatch(db, order_id, courier_company=update_in.courier_company, tracking_number=update_in.tracking_number, partner_id=p_id)

@order_router.put("/{order_id}/status", response_model=schemas.B2BOrderResponse)
async def update_b2b_order_status(
    order_id: UUID,
    update_in: schemas.B2BOrderUpdate,
    partner_id: int = Query(None, description="Required for Admins"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not update_in.order_status:
        raise HTTPException(status_code=400, detail="order_status required")
    dealer = None
    p_id = None
    if current_user.role == UserRole.DEALER:
        from sqlalchemy.future import select as sa_select
        res = await db.execute(sa_select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = res.scalars().first()
    else:
        p_id = current_user.partner_id or partner_id
    return await services.update_b2b_order_status(db, order_id, status_in=update_in.order_status, partner_id=p_id, dealer=dealer)


