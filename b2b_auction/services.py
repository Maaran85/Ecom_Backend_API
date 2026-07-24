from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, delete
from fastapi import HTTPException
from datetime import datetime, timezone
from uuid import UUID
import uuid
from typing import Optional, List

from .models import B2BAuctionItem, B2BAuctionBid, B2BAuctionStatus, B2BAuctionRegistration, B2BRegistrationType, B2BProduct, B2BOrder, B2BOrderItem, B2BOrderStatus
from .schemas import B2BAuctionItemCreate, B2BAuctionItemUpdate, B2BAuctionBidCreate, B2BProductCreate, B2BProductUpdate, B2BOrderUpdate, B2BAuctionRegistrationCreate
from models.dealer import Dealer
from models.partner import Partner



async def get_auctions(db: AsyncSession, skip: int = 0, limit: int = 100, b2b_product_id: Optional[UUID] = None, status: Optional[B2BAuctionStatus] = None, dealer: Optional[Dealer] = None):
    query = (
        select(B2BAuctionItem)
        .options(selectinload(B2BAuctionItem.b2b_product), selectinload(B2BAuctionItem.bids).selectinload(B2BAuctionBid.dealer))
        .order_by(B2BAuctionItem.created_at.desc())
    )
    if b2b_product_id:
        query = query.filter(B2BAuctionItem.b2b_product_id == b2b_product_id)
    if status:
        query = query.filter(B2BAuctionItem.status == status)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    auctions = result.scalars().all()

    # Pre-fetch dealer's registrations if a dealer is logged in
    dealer_registered_auction_ids = set()
    dealer_winning_auction_ids = set()
    if dealer:
        reg_query = select(B2BAuctionRegistration.auction_id).filter(B2BAuctionRegistration.dealer_id == dealer.id)
        reg_result = await db.execute(reg_query)
        dealer_registered_auction_ids = set(reg_result.scalars().all())
        
        # Determine auctions where this dealer is winning/won
        win_query = select(B2BAuctionBid.auction_id).filter(B2BAuctionBid.dealer_id == dealer.id, B2BAuctionBid.is_winning == True)
        win_result = await db.execute(win_query)
        dealer_winning_auction_ids = set(win_result.scalars().all())

    # Pre-fetch registration counts for all auctions in one query
    from sqlalchemy import func
    auction_ids = [a.id for a in auctions]
    reg_count_query = (
        select(B2BAuctionRegistration.auction_id, func.count(B2BAuctionRegistration.id).label("reg_count"))
        .filter(B2BAuctionRegistration.auction_id.in_(auction_ids))
        .group_by(B2BAuctionRegistration.auction_id)
    )
    reg_count_result = await db.execute(reg_count_query)
    registration_counts = {row.auction_id: row.reg_count for row in reg_count_result}

    # Attach computed bid_count and is_registered to each auction object
    for auction in auctions:
        auction.bid_count = len(auction.bids)
        auction.is_registered = auction.id in dealer_registered_auction_ids
        auction.is_winner = auction.id in dealer_winning_auction_ids
        auction.registration_count = registration_counts.get(auction.id, 0)

    return auctions

async def get_auction(db: AsyncSession, auction_id: UUID, dealer: Optional[Dealer] = None):
    result = await db.execute(
        select(B2BAuctionItem)
        .options(selectinload(B2BAuctionItem.b2b_product), selectinload(B2BAuctionItem.bids).selectinload(B2BAuctionBid.dealer))
        .filter(B2BAuctionItem.id == auction_id)
        .execution_options(populate_existing=True)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    auction.bid_count = len(auction.bids)

    if dealer:
        reg_res = await db.execute(select(B2BAuctionRegistration).filter(
            B2BAuctionRegistration.auction_id == auction_id,
            B2BAuctionRegistration.dealer_id == dealer.id
        ))
        auction.is_registered = reg_res.scalars().first() is not None
        
        win_res = await db.execute(select(B2BAuctionBid).filter(
            B2BAuctionBid.auction_id == auction_id,
            B2BAuctionBid.dealer_id == dealer.id,
            B2BAuctionBid.is_winning == True
        ))
        auction.is_winner = win_res.scalars().first() is not None
        
        last_bid_res = await db.execute(select(B2BAuctionBid.bid_amount).filter(
            B2BAuctionBid.auction_id == auction_id,
            B2BAuctionBid.dealer_id == dealer.id
        ).order_by(B2BAuctionBid.bid_amount.desc()).limit(1))
        auction.my_last_bid = last_bid_res.scalar()

    else:
        auction.is_registered = False
        auction.is_winner = False
        auction.my_last_bid = None

    return auction

async def create_auction(db: AsyncSession, auction_in: B2BAuctionItemCreate, partner_id: int):
    now = datetime.now(timezone.utc)
    start = auction_in.start_time if auction_in.start_time.tzinfo else auction_in.start_time.replace(tzinfo=timezone.utc)
    end = auction_in.end_time if auction_in.end_time.tzinfo else auction_in.end_time.replace(tzinfo=timezone.utc)

    if start <= now:
        raise HTTPException(status_code=400, detail="Start time must be in the future (greater than current time).")
    if end <= now:
        raise HTTPException(status_code=400, detail="End time must be in the future (greater than current time).")
    if start >= end:
        raise HTTPException(status_code=400, detail="Start time must be strictly before End time.")

    # Fetch B2B product to reserve qty
    result = await db.execute(
        select(B2BProduct).filter(B2BProduct.id == auction_in.b2b_product_id)
    )
    product = result.scalars().first()

    if not product or product.partner_id != partner_id:
        raise HTTPException(status_code=400, detail="Product not found or doesn't belong to partner")

    auction_data = auction_in.model_dump()
    db_auction = B2BAuctionItem(**auction_data, partner_id=partner_id)
    
    db.add(db_auction)
    db.add(product)
    
    await db.commit()
    await db.refresh(db_auction)
    
    return await get_auction(db, db_auction.id)

async def update_auction(db: AsyncSession, auction_id: UUID, auction_in: B2BAuctionItemUpdate, partner_id: int):
    result = await db.execute(select(B2BAuctionItem).filter(B2BAuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    if auction.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this auction")
        
    update_data = auction_in.model_dump(exclude_unset=True)
    
    now = datetime.now(timezone.utc)
    start_val = update_data.get('start_time', auction.start_time)
    end_val = update_data.get('end_time', auction.end_time)
    start = start_val if start_val.tzinfo else start_val.replace(tzinfo=timezone.utc)
    end = end_val if end_val.tzinfo else end_val.replace(tzinfo=timezone.utc)

    if 'start_time' in update_data and start <= now:
        raise HTTPException(status_code=400, detail="Start time must be in the future (greater than current time).")
    if 'end_time' in update_data and end <= now:
        raise HTTPException(status_code=400, detail="End time must be in the future (greater than current time).")
    if start >= end:
        raise HTTPException(status_code=400, detail="Start time must be strictly before End time.")

    for field, value in update_data.items():
        setattr(auction, field, value)
        
    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    return await get_auction(db, auction_id)

async def recalculate_allocations(db: AsyncSession, auction: B2BAuctionItem):
    """
    Recalculates the allocated_qty and is_winning flags for all bids of an auction.
    Follows multi-winner allocation logic: allocates total qty to top bidders.
    """
    # Fetch all ACTIVE bids for this auction, ordered by amount (desc) and created_at (asc)
    result = await db.execute(
        select(B2BAuctionBid)
        .where(
            B2BAuctionBid.auction_id == auction.id,
            B2BAuctionBid.is_active == True
        )
        .order_by(B2BAuctionBid.bid_amount.desc(), B2BAuctionBid.created_at.asc())
    )
    bids = result.scalars().all()
    
    remaining_qty = auction.qty
    
    for bid in bids:
        if remaining_qty > 0:
            allocated = min(bid.bid_qty, remaining_qty)
            bid.allocated_qty = allocated
            bid.is_winning = True
            remaining_qty -= allocated
        else:
            bid.allocated_qty = 0
            bid.is_winning = False
            
    db.add_all(bids)
    # We do not commit here; the caller commits.

async def place_bid(db: AsyncSession, auction_id: UUID, bid_in: B2BAuctionBidCreate, dealer: Dealer):
    auction = await get_auction(db, auction_id)
    
    if auction.status != B2BAuctionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Auction is not active")
        
    now = datetime.now(timezone.utc)
    if now < auction.start_time or now > auction.end_time:
        raise HTTPException(status_code=400, detail="Auction has ended or not started yet")
        
    highest_bid = auction.current_highest_bid or 0.0
    
    if bid_in.bid_amount < auction.base_price:
        raise HTTPException(status_code=400, detail=f"Bid amount must be at least the base price of ₹{auction.base_price}")
        
    # Verify the dealer is registered (required for ALL auctions)
    reg_result = await db.execute(
        select(B2BAuctionRegistration).filter(
            B2BAuctionRegistration.auction_id == auction_id,
            B2BAuctionRegistration.dealer_id == dealer.id
        )
    )
    registration = reg_result.scalars().first()
    if not registration:
        raise HTTPException(
            status_code=403,
            detail="You must register for this auction before placing a bid."
        )

    # Ensure bid is strictly greater than dealer's own previous highest ACTIVE bid
    prev_bid_result = await db.execute(
        select(B2BAuctionBid.bid_amount)
        .where(
            B2BAuctionBid.auction_id == auction_id,
            B2BAuctionBid.dealer_id == dealer.id,
            B2BAuctionBid.is_active == True
        )
        .order_by(B2BAuctionBid.bid_amount.desc())
        .limit(1)
    )
    dealer_highest_prev_bid = prev_bid_result.scalar()
    
    if dealer_highest_prev_bid is not None and bid_in.bid_amount <= dealer_highest_prev_bid:
        raise HTTPException(
            status_code=400,
            detail=f"Your new bid must be greater than your previous highest bid of ₹{dealer_highest_prev_bid}"
        )

    is_winning = False
        
    # Mark previous bids by this dealer as inactive to maintain history but prevent duplicate allocations
    old_bids = [b for b in auction.bids if b.dealer_id == dealer.id and b.is_active]
    for old_bid in old_bids:
        old_bid.is_active = False
        old_bid.is_winning = False
        old_bid.allocated_qty = 0

    # Create the new bid
    db_bid = B2BAuctionBid(
        auction_id=auction.id,
        dealer_id=dealer.id,
        bid_amount=bid_in.bid_amount,
        bid_qty=registration.registered_qty,
        is_winning=is_winning,
        is_active=True
    )
    
    if bid_in.bid_amount > (auction.current_highest_bid or 0):
        auction.current_highest_bid = bid_in.bid_amount
    
    db.add(db_bid)
    db.add(auction)
    # Flush to ensure db_bid is inserted before recalculating
    await db.flush()
    
    await recalculate_allocations(db, auction)
    
    await db.commit()
    await db.refresh(db_bid)
    await db.refresh(dealer)
    db_bid.dealer = dealer
    
    return db_bid

async def publish_auction(db: AsyncSession, auction_id: UUID, partner_id: int):
    result = await db.execute(
        select(B2BAuctionItem)
        .options(selectinload(B2BAuctionItem.b2b_product), selectinload(B2BAuctionItem.bids).selectinload(B2BAuctionBid.dealer))
        .where(B2BAuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.status != B2BAuctionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only PENDING auctions can be published")
        
    if auction.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to publish this auction")

    auction.status = B2BAuctionStatus.ACTIVE
    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    
    return auction

async def cancel_auction(db: AsyncSession, auction_id: UUID, partner_id: int):
    result = await db.execute(
        select(B2BAuctionItem)
        .options(selectinload(B2BAuctionItem.b2b_product), selectinload(B2BAuctionItem.bids).selectinload(B2BAuctionBid.dealer))
        .where(B2BAuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.status not in [B2BAuctionStatus.PENDING, B2BAuctionStatus.ACTIVE]:
        raise HTTPException(status_code=400, detail="Only PENDING or ACTIVE auctions can be cancelled")
        
    if auction.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this auction")

    auction.status = B2BAuctionStatus.CANCELLED

    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    
    return auction

async def delete_auction(db: AsyncSession, auction_id: UUID, partner_id: int):
    result = await db.execute(select(B2BAuctionItem).where(B2BAuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this auction")
        
    if auction.status not in [B2BAuctionStatus.PENDING, B2BAuctionStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Only PENDING or CANCELLED auctions can be deleted")

    await db.delete(auction)
    await db.commit()
    return {"message": "Auction deleted successfully"}

async def get_registration_status(db: AsyncSession, auction_id: UUID, dealer: Dealer):
    result = await db.execute(select(B2BAuctionItem).filter(B2BAuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    reg_result = await db.execute(
        select(B2BAuctionRegistration).filter(
            B2BAuctionRegistration.auction_id == auction_id,
            B2BAuctionRegistration.dealer_id == dealer.id
        )
    )
    registration = reg_result.scalars().first()

    return {
        "is_registered": registration is not None,
        "auction_id": auction_id,
        "registration_type": auction.registration_type,
        "deposit_amount": auction.deposit_amount,
        "deposit_paid": registration.deposit_paid if registration else 0.0,
        "registered_at": registration.registered_at if registration else None,
        "registered_qty": registration.registered_qty if registration else 0
    }

async def register_for_auction(db: AsyncSession, auction_id: UUID, reg_in: B2BAuctionRegistrationCreate, dealer: Dealer):
    result = await db.execute(select(B2BAuctionItem).filter(B2BAuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    if auction.status not in [B2BAuctionStatus.ACTIVE, B2BAuctionStatus.PENDING]:
        raise HTTPException(status_code=400, detail="Can only register for ACTIVE or PENDING auctions")

    reg_result = await db.execute(
        select(B2BAuctionRegistration).filter(
            B2BAuctionRegistration.auction_id == auction_id,
            B2BAuctionRegistration.dealer_id == dealer.id
        )
    )
    if reg_result.scalars().first():
        raise HTTPException(status_code=400, detail="Already registered for this auction")

    deposit_paid = 0.0
    if auction.registration_type == B2BRegistrationType.PAID:
        deposit_amount = auction.deposit_amount or 0.0
        # In a real system, you'd process payment or deduct from wallet here.
        # For now, we simulate payment success.
        deposit_paid = deposit_amount
        
    qty = reg_in.registered_qty
    if qty < auction.min_bid_qty:
        raise HTTPException(status_code=400, detail=f"Minimum registration quantity is {auction.min_bid_qty}")
    if qty % auction.min_bid_qty != 0:
        raise HTTPException(status_code=400, detail=f"Registration quantity must be a multiple of {auction.min_bid_qty}")
    if qty > auction.qty:
        raise HTTPException(status_code=400, detail=f"Registration quantity cannot exceed total auction quantity ({auction.qty})")

    registration = B2BAuctionRegistration(
        auction_id=auction_id,
        dealer_id=dealer.id,
        deposit_paid=deposit_paid,
        registered_qty=qty
    )
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    return registration

async def get_b2b_products(
    db: AsyncSession, 
    partner_id: Optional[int] = None,
    skip: int = 0, 
    limit: int = 100
) -> List[B2BProduct]:
    query = select(B2BProduct).where(B2BProduct.is_deleted == False)
    if partner_id:
        query = query.filter(B2BProduct.partner_id == partner_id)
    
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()

async def get_b2b_product(db: AsyncSession, product_id: UUID) -> B2BProduct:
    result = await db.execute(select(B2BProduct).filter(B2BProduct.id == product_id))
    product = result.scalars().first()
    if not product:
        raise HTTPException(status_code=404, detail="B2B Product not found")
    return product

async def create_b2b_product(db: AsyncSession, product_in: B2BProductCreate, partner_id: int) -> B2BProduct:
    # Ensure partner exists
    result = await db.execute(select(Partner).filter(Partner.id == partner_id))
    if not result.scalars().first():
        raise HTTPException(status_code=404, detail="Partner not found")
        
    db_product = B2BProduct(**product_in.model_dump(), partner_id=partner_id)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product

async def update_b2b_product(db: AsyncSession, product_id: UUID, product_in: B2BProductUpdate, partner_id: int) -> B2BProduct:
    product = await get_b2b_product(db, product_id)
    
    if product.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this product")
        
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
        
    await db.commit()
    await db.refresh(product)
    return product

async def delete_b2b_product(db: AsyncSession, product_id: UUID, partner_id: int):
    product = await get_b2b_product(db, product_id)
    
    if product.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this product")
        
    # Check if product is in any auction
    result = await db.execute(select(B2BAuctionItem).where(B2BAuctionItem.b2b_product_id == product_id))
    in_auction = result.scalars().first()
    
    if in_auction:
        product.is_deleted = True
        db.add(product)
        await db.commit()
        return {"message": "B2B Product soft deleted successfully"}
    else:
        await db.delete(product)
        await db.commit()
        return {"message": "B2B Product hard deleted successfully"}

async def finalize_auction_orders(db: AsyncSession, auction_id: UUID, partner_id: int):
    result = await db.execute(
        select(B2BAuctionItem)
        .options(selectinload(B2BAuctionItem.b2b_product), selectinload(B2BAuctionItem.bids).selectinload(B2BAuctionBid.dealer))
        .where(B2BAuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to finalize this auction")
        
    # Check if orders already generated
    existing_orders = await db.execute(select(B2BOrder).where(B2BOrder.auction_id == auction_id))
    if existing_orders.scalars().first():
        raise HTTPException(status_code=400, detail="Orders have already been finalized for this auction")

    if auction.status == B2BAuctionStatus.ACTIVE or auction.status == B2BAuctionStatus.PENDING:
        auction.status = B2BAuctionStatus.COMPLETED
        db.add(auction)
        
    await recalculate_allocations(db, auction)
    await db.flush()
    
    # Query winning bids
    bids_res = await db.execute(
        select(B2BAuctionBid)
        .where(B2BAuctionBid.auction_id == auction_id, B2BAuctionBid.is_winning == True, B2BAuctionBid.allocated_qty > 0)
    )
    winning_bids = bids_res.scalars().all()
    
    # Group winning bids by dealer_id
    dealer_bids = {}
    for bid in winning_bids:
        dealer_bids.setdefault(bid.dealer_id, []).append(bid)
        
    created_orders = []
    for d_id, b_list in dealer_bids.items():
        dealer_res = await db.execute(select(Dealer).where(Dealer.id == d_id))
        dealer = dealer_res.scalars().first()
        
        reg_res = await db.execute(
            select(B2BAuctionRegistration)
            .where(B2BAuctionRegistration.auction_id == auction_id, B2BAuctionRegistration.dealer_id == d_id)
        )
        reg = reg_res.scalars().first()
        deposit_paid = reg.deposit_paid if reg else 0.0
        
        order_num = f"B2B-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(d_id)[:4].upper()}-{str(uuid.uuid4())[:6].upper()}"
        
        # Determine address
        addr = ""
        if dealer:
            addr = getattr(dealer, 'address', '') or getattr(dealer, 'city', '') or "Dealer Store Address"
        else:
            addr = "Dealer Store Address"
            
        new_order = B2BOrder(
            order_number=order_num,
            auction_id=auction_id,
            partner_id=partner_id,
            dealer_id=d_id,
            b2b_product_id=auction.b2b_product_id,
            total_qty=0,
            total_amount=0.0,
            deposit_applied=deposit_paid,
            balance_due=0.0,
            payment_status="PENDING_PAYMENT",
            order_status=B2BOrderStatus.PENDING_CONFIRMATION,
            shipping_address=addr
        )
        db.add(new_order)
        await db.flush()
        
        tot_qty = 0
        tot_amt = 0.0
        for b in b_list:
            item_sub = b.allocated_qty * b.bid_amount
            tot_qty += b.allocated_qty
            tot_amt += item_sub
            
            order_item = B2BOrderItem(
                order_id=new_order.id,
                bid_id=b.id,
                qty=b.allocated_qty,
                unit_price=b.bid_amount,
                subtotal=item_sub
            )
            db.add(order_item)
            
        new_order.total_qty = tot_qty
        new_order.total_amount = tot_amt
        new_order.balance_due = max(0.0, tot_amt - deposit_paid)
        if new_order.balance_due == 0.0:
            new_order.payment_status = "PAID"
            
        db.add(new_order)
        created_orders.append(new_order)
        
    await db.commit()
    for o in created_orders:
        await db.refresh(o)
        
    return created_orders

async def get_partner_b2b_orders(db: AsyncSession, partner_id: int, status: Optional[B2BOrderStatus] = None, skip: int = 0, limit: int = 100):
    query = (
        select(B2BOrder)
        .options(selectinload(B2BOrder.items), selectinload(B2BOrder.b2b_product), selectinload(B2BOrder.dealer), selectinload(B2BOrder.auction))
        .where(B2BOrder.partner_id == partner_id)
        .order_by(B2BOrder.created_at.desc())
    )
    if status:
        query = query.where(B2BOrder.order_status == status)
    query = query.offset(skip).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()

async def get_dealer_b2b_orders(db: AsyncSession, dealer_id: UUID, status: Optional[B2BOrderStatus] = None, skip: int = 0, limit: int = 100):
    query = (
        select(B2BOrder)
        .options(selectinload(B2BOrder.items), selectinload(B2BOrder.b2b_product), selectinload(B2BOrder.partner), selectinload(B2BOrder.auction))
        .where(B2BOrder.dealer_id == dealer_id)
        .order_by(B2BOrder.created_at.desc())
    )
    if status:
        query = query.where(B2BOrder.order_status == status)
    query = query.offset(skip).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()

async def get_b2b_order(db: AsyncSession, order_id: UUID, dealer: Optional[Dealer] = None, partner_id: Optional[int] = None):
    query = (
        select(B2BOrder)
        .options(selectinload(B2BOrder.items), selectinload(B2BOrder.b2b_product), selectinload(B2BOrder.dealer), selectinload(B2BOrder.partner), selectinload(B2BOrder.auction))
        .where(B2BOrder.id == order_id)
    )
    res = await db.execute(query)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if dealer and order.dealer_id != dealer.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
    if partner_id and order.partner_id != partner_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")
        
    return order

async def update_b2b_order_dispatch(db: AsyncSession, order_id: UUID, courier_company: str, tracking_number: str, partner_id: int):
    order = await get_b2b_order(db, order_id, partner_id=partner_id)
    order.courier_company = courier_company
    order.tracking_number = tracking_number
    order.order_status = B2BOrderStatus.DISPATCHED
    order.dispatched_at = datetime.now(timezone.utc)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order

async def update_b2b_order_status(db: AsyncSession, order_id: UUID, status_in: B2BOrderStatus, partner_id: Optional[int] = None, dealer: Optional[Dealer] = None):
    order = await get_b2b_order(db, order_id, dealer=dealer, partner_id=partner_id)
    order.order_status = status_in
    if status_in == B2BOrderStatus.DELIVERED:
        order.delivered_at = datetime.now(timezone.utc)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order

async def pay_b2b_order(db: AsyncSession, order_id: UUID, dealer_id: UUID):
    order = await get_b2b_order(db, order_id, dealer=Dealer(id=dealer_id)) # Mock dealer just to pass the check or we can fetch dealer if needed. Wait, get_b2b_order expects actual Dealer model but only checks `dealer.id`.
    # Let's bypass get_b2b_order and fetch directly to be safe, or just pass a mock Dealer object.
    query = (
        select(B2BOrder)
        .options(selectinload(B2BOrder.items), selectinload(B2BOrder.b2b_product), selectinload(B2BOrder.dealer), selectinload(B2BOrder.partner), selectinload(B2BOrder.auction))
        .where(B2BOrder.id == order_id)
        .where(B2BOrder.dealer_id == dealer_id)
    )
    res = await db.execute(query)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.payment_status == 'PAID':
        raise HTTPException(status_code=400, detail="Order is already paid")
        
    # Mock online payment gateway logic:
    # 1. Charge card/UPI via Razorpay/Stripe (Simulated)
    # 2. Update order
    order.payment_status = 'PAID'
    order.balance_due = 0.0
    if order.order_status == B2BOrderStatus.PENDING_CONFIRMATION:
        order.order_status = B2BOrderStatus.CONFIRMED
        
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order

