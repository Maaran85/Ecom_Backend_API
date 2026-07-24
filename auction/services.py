from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import update, delete
from fastapi import HTTPException
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from .models import AuctionItem, AuctionBid, AuctionStatus, AuctionRegistration, RegistrationType
from .schemas import AuctionItemCreate, AuctionItemUpdate, AuctionBidCreate
from models.user import User

async def get_auctions(db: AsyncSession, skip: int = 0, limit: int = 100, product_id: Optional[UUID] = None, status: Optional[AuctionStatus] = None, user: Optional[User] = None):
    query = (
        select(AuctionItem)
        .options(selectinload(AuctionItem.product), selectinload(AuctionItem.bids))
        .order_by(AuctionItem.created_at.desc())
    )
    if product_id:
        query = query.filter(AuctionItem.product_id == product_id)
    if status:
        query = query.filter(AuctionItem.status == status)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    auctions = result.scalars().all()

    # Pre-fetch user's registrations if a user is logged in
    user_registered_auction_ids = set()
    user_winning_auction_ids = set()
    if user:
        reg_query = select(AuctionRegistration.auction_id).filter(AuctionRegistration.user_id == user.id)
        reg_result = await db.execute(reg_query)
        user_registered_auction_ids = set(reg_result.scalars().all())
        
        # Determine auctions where this user is winning/won
        win_query = select(AuctionBid.auction_id).filter(AuctionBid.user_id == user.id, AuctionBid.is_winning == True)
        win_result = await db.execute(win_query)
        user_winning_auction_ids = set(win_result.scalars().all())

    # Pre-fetch registration counts for all auctions in one query
    from sqlalchemy import func
    auction_ids = [a.id for a in auctions]
    reg_count_query = (
        select(AuctionRegistration.auction_id, func.count(AuctionRegistration.id).label("reg_count"))
        .filter(AuctionRegistration.auction_id.in_(auction_ids))
        .group_by(AuctionRegistration.auction_id)
    )
    reg_count_result = await db.execute(reg_count_query)
    registration_counts = {row.auction_id: row.reg_count for row in reg_count_result}

    # Attach computed bid_count and is_registered to each auction object
    for auction in auctions:
        auction.bid_count = len(auction.bids)
        auction.is_registered = auction.id in user_registered_auction_ids
        auction.is_winner = auction.id in user_winning_auction_ids
        auction.registration_count = registration_counts.get(auction.id, 0)

    return auctions

async def get_auction(db: AsyncSession, auction_id: UUID):
    result = await db.execute(
        select(AuctionItem)
        .options(selectinload(AuctionItem.product), selectinload(AuctionItem.bids))
        .filter(AuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
    auction.bid_count = len(auction.bids)
    return auction

async def create_auction(db: AsyncSession, auction_in: AuctionItemCreate, user: User):
    from models.inventory import ProductInventory, StockMovement, MovementType
    
    # Strategy: Manual Hub Allocation
    result = await db.execute(
        select(ProductInventory)
        .filter(
            ProductInventory.product_id == auction_in.product_id,
            ProductInventory.hub_id == auction_in.hub_id
        )
    )
    selected_hub_inventory = result.scalars().first()

    if not selected_hub_inventory or selected_hub_inventory.stock < auction_in.qty:
        raise HTTPException(status_code=400, detail=f"Selected Hub has insufficient stock. Requires {auction_in.qty}.")

    # Deduct qty units
    stock_before = selected_hub_inventory.stock
    selected_hub_inventory.stock -= auction_in.qty
    stock_after = selected_hub_inventory.stock

    # Only dealers or admins should create auctions ideally
    dealer_id = None
    if user.role == "DEALER":
        pass

    auction_data = auction_in.model_dump()
    
    db_auction = AuctionItem(**auction_data)
    db.add(db_auction)
    db.add(selected_hub_inventory)
    
    await db.flush() # Flush to get auction ID

    movement = StockMovement(
        product_id=auction_in.product_id,
        hub_id=selected_hub_inventory.hub_id,
        movement_type=MovementType.RESERVATION,
        quantity=-auction_in.qty,
        stock_before=stock_before,
        stock_after=stock_after,
        reference_type="auction_created",
        user_id=user.id,
        notes=f"Auction reserved. Auction ID: {db_auction.id}"
    )
    db.add(movement)

    auction_id = db_auction.id
    await db.commit()
    
    # Eagerly load the product relationship for the response
    result = await db.execute(
        select(AuctionItem)
        .options(__import__('sqlalchemy.orm').orm.selectinload(AuctionItem.product))
        .filter(AuctionItem.id == auction_id)
    )
    return result.scalars().first()

async def recalculate_allocations(db: AsyncSession, auction: AuctionItem):
    """
    Recalculates the allocated_qty and is_winning flags for all bids of an auction.
    Follows multi-winner allocation logic: allocates total qty to top bidders.
    """
    # Fetch all bids for this auction, ordered by amount (desc) and created_at (asc)
    result = await db.execute(
        select(AuctionBid)
        .where(AuctionBid.auction_id == auction.id)
        .order_by(AuctionBid.bid_amount.desc(), AuctionBid.created_at.asc())
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

async def place_bid(db: AsyncSession, auction_id: UUID, bid_in: AuctionBidCreate, user: User):
    auction = await get_auction(db, auction_id)
    
    if auction.status != AuctionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Auction is not active")
        
    now = datetime.now(timezone.utc)
    if now < auction.start_time or now > auction.end_time:
        raise HTTPException(status_code=400, detail="Auction has ended or not started yet")
        
    highest_bid = auction.current_highest_bid or 0.0
    
    # Bidders can bid any amount >= base_price. They can bid the same amount as highest_bid.
    if bid_in.bid_amount < auction.base_price:
        raise HTTPException(status_code=400, detail=f"Bid amount must be at least the base price of ₹{auction.base_price}")
        
    if bid_in.bid_qty < auction.min_bid_qty:
        raise HTTPException(status_code=400, detail=f"Minimum bid quantity is {auction.min_bid_qty}")
        
    if bid_in.bid_qty % auction.min_bid_qty != 0:
        raise HTTPException(status_code=400, detail=f"Bid quantity must be a multiple of {auction.min_bid_qty}")
        
    if bid_in.bid_qty > auction.qty:
        raise HTTPException(status_code=400, detail=f"Bid quantity cannot exceed total auction quantity ({auction.qty})")
        
    # Verify the user is registered (required for ALL auctions)
    reg_result = await db.execute(
        select(AuctionRegistration).filter(
            AuctionRegistration.auction_id == auction_id,
            AuctionRegistration.user_id == user.id
        )
    )
    registration = reg_result.scalars().first()
    if not registration:
        raise HTTPException(
            status_code=403,
            detail="You must register for this auction before placing a bid."
        )

    is_winning = False
        
    # Create the bid
    db_bid = AuctionBid(
        auction_id=auction.id,
        user_id=user.id,
        bid_amount=bid_in.bid_amount,
        bid_qty=bid_in.bid_qty,
        is_winning=is_winning
    )
    
    auction.current_highest_bid = bid_in.bid_amount
    
    db.add(db_bid)
    db.add(auction)
    # Flush to ensure db_bid is inserted before recalculating
    await db.flush()
    
    await recalculate_allocations(db, auction)
    
    await db.commit()
    await db.refresh(db_bid)
    
    return db_bid

async def publish_auction(db: AsyncSession, auction_id: UUID, user: User):
    result = await db.execute(
        select(AuctionItem)
        .options(selectinload(AuctionItem.product), selectinload(AuctionItem.dealer), selectinload(AuctionItem.bids))
        .where(AuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.status != AuctionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Only PENDING auctions can be published")
        
    # Dealers can only publish their own auctions
    if user.role == "DEALER":
        from models.user import Dealer
        dealer_result = await db.execute(select(Dealer).where(Dealer.user_id == user.id))
        dealer = dealer_result.scalars().first()
        if not dealer or auction.dealer_id != dealer.id:
            raise HTTPException(status_code=403, detail="Not authorized to publish this auction")

    auction.status = AuctionStatus.ACTIVE
    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    
    return auction

async def cancel_auction(db: AsyncSession, auction_id: UUID, user: User):
    result = await db.execute(
        select(AuctionItem)
        .options(selectinload(AuctionItem.product), selectinload(AuctionItem.dealer), selectinload(AuctionItem.bids))
        .where(AuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")
        
    if auction.status not in [AuctionStatus.PENDING, AuctionStatus.ACTIVE]:
        raise HTTPException(status_code=400, detail="Only PENDING or ACTIVE auctions can be cancelled")
        
    # Dealers can only cancel their own auctions
    if user.role == "DEALER":
        from models.user import Dealer
        dealer_result = await db.execute(select(Dealer).where(Dealer.user_id == user.id))
        dealer = dealer_result.scalars().first()
        if not dealer or auction.dealer_id != dealer.id:
            raise HTTPException(status_code=403, detail="Not authorized to cancel this auction")

    # NOTE: If we are cancelling, we might want to release the inventory reserved.
    # We will simply update the status to CANCELLED for now. The inventory release logic 
    # should ideally be added here.
    
    auction.status = AuctionStatus.CANCELLED
    db.add(auction)
    await db.commit()
    await db.refresh(auction)
    
    return auction

async def get_registration_status(db: AsyncSession, auction_id: UUID, user: User):
    """Check if a user is registered for an auction and return status details."""
    # Get auction basic info
    result = await db.execute(select(AuctionItem).filter(AuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    # Check for existing registration
    reg_result = await db.execute(
        select(AuctionRegistration).filter(
            AuctionRegistration.auction_id == auction_id,
            AuctionRegistration.user_id == user.id
        )
    )
    registration = reg_result.scalars().first()

    return {
        "is_registered": registration is not None,
        "registration": registration,
        "auction_registration_type": auction.registration_type,
        "deposit_amount": auction.deposit_amount,
    }

async def register_for_auction(db: AsyncSession, auction_id: UUID, user: User):
    """Register a customer for an auction, handling FREE and PAID flows."""
    result = await db.execute(select(AuctionItem).filter(AuctionItem.id == auction_id))
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    if auction.status != AuctionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Can only register for ACTIVE auctions")

    now = auction.start_time.tzinfo  # check if tz-aware
    # Check auction hasn't ended
    from datetime import datetime, timezone
    if datetime.now(timezone.utc) > auction.end_time:
        raise HTTPException(status_code=400, detail="This auction has already ended")

    # Enforce max_bidders limit — always enforced since default is 100
    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(AuctionRegistration.id)).filter(AuctionRegistration.auction_id == auction_id)
    )
    current_count = count_result.scalar() or 0
    if current_count >= auction.max_bidders:
        raise HTTPException(
            status_code=400,
            detail=f"Registration is full. This auction only allows {auction.max_bidders} bidders."
        )

    # Check if already registered
    reg_result = await db.execute(
        select(AuctionRegistration).filter(
            AuctionRegistration.auction_id == auction_id,
            AuctionRegistration.user_id == user.id
        )
    )
    existing = reg_result.scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="You are already registered for this auction")

    deposit_paid = 0.0

    if auction.registration_type == RegistrationType.PAID:
        # Deduct deposit from customer wallet
        from models.user import CustomerUser
        cust_result = await db.execute(
            select(CustomerUser).filter(CustomerUser.id == user.customer_profile_id)
        )
        customer = cust_result.scalars().first()

        if not customer:
            raise HTTPException(status_code=404, detail="Customer profile not found")

        wallet_balance = getattr(customer, 'wallet_balance', 0.0) or 0.0
        deposit_required = auction.deposit_amount or 0.0

        if wallet_balance < deposit_required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient wallet balance. Required: ₹{deposit_required}, Available: ₹{wallet_balance}"
            )

        # Deduct from wallet
        customer.wallet_balance = wallet_balance - deposit_required
        db.add(customer)
        deposit_paid = deposit_required

    registration = AuctionRegistration(
        auction_id=auction_id,
        user_id=user.id,
        deposit_paid=deposit_paid
    )
    db.add(registration)
    await db.commit()
    await db.refresh(registration)
    return registration

async def finalize_auction(db: AsyncSession, auction_id: UUID):
    """
    Finalizes an auction:
    - Marks it as COMPLETED
    - Runs recalculate_allocations to be certain
    - Generates a single PENDING Order for each winning user, with an OrderItem per winning bid.
    - Deducts deposit from Order total if applicable.
    """
    from models.cart import Order, OrderItem, OrderStatus
    from models.customer_user import CustomerUser
    from services.tax_service import TaxService
    from models.tax import TaxLedger

    result = await db.execute(
        select(AuctionItem)
        .options(selectinload(AuctionItem.product), selectinload(AuctionItem.bids))
        .where(AuctionItem.id == auction_id)
    )
    auction = result.scalars().first()
    if not auction:
        raise HTTPException(status_code=404, detail="Auction not found")

    if auction.status == AuctionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Auction is already finalized")

    # Mark as completed
    auction.status = AuctionStatus.COMPLETED
    db.add(auction)
    
    # Recalculate allocations just to be sure
    await recalculate_allocations(db, auction)
    await db.flush()

    # Group winning bids by user_id
    winning_bids = [b for b in auction.bids if b.is_winning and getattr(b, 'allocated_qty', 0) > 0 and b.order_id is None]
    
    user_bids_map = {}
    for bid in winning_bids:
        if bid.user_id not in user_bids_map:
            user_bids_map[bid.user_id] = []
        user_bids_map[bid.user_id].append(bid)
        
    generated_orders = []

    for user_id, bids in user_bids_map.items():
        # Get registration to find deposit
        reg_result = await db.execute(
            select(AuctionRegistration).filter(
                AuctionRegistration.auction_id == auction_id,
                AuctionRegistration.user_id == user_id
            )
        )
        registration = reg_result.scalars().first()
        deposit_deduction = registration.deposit_paid if registration else 0.0

        # Calculate taxes and subtotals
        subtotal = 0.0
        total_tax = 0.0
        total_cgst = 0.0
        total_sgst = 0.0
        total_igst = 0.0
        bids_tax_data = []

        for bid in bids:
            bid_subtotal = bid.allocated_qty * bid.bid_amount
            subtotal += bid_subtotal
            
            # Pass None for buyer/seller state since we don't have shipping address selected yet
            tax_data = await TaxService.calculate_item_tax(
                db, 
                base_price=bid.bid_amount, 
                qty=bid.allocated_qty, 
                product_id=auction.product_id, 
                buyer_state=None, 
                seller_state=None,
                is_inclusive=False
            )
            bids_tax_data.append((bid, tax_data))
            
            total_tax += tax_data["total_tax"]
            total_cgst += tax_data["cgst_amount"]
            total_sgst += tax_data["sgst_amount"]
            total_igst += tax_data["igst_amount"]

        # Final amount includes the subtotal + calculated taxes - deposit
        total_amount = max(0, subtotal + total_tax - deposit_deduction)
        tax_invoice_no = await TaxService.generate_tax_invoice_number(db)

        # Create Order
        new_order = Order(
            customer_id=user_id,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            total_amount=total_amount,
            discount_amount=deposit_deduction,  # Treat deposit as a discount for now
            payment_method="PENDING",
            is_auction_order=True,
            tax_amount=total_tax,
            cgst_amount=total_cgst,
            sgst_amount=total_sgst,
            igst_amount=total_igst,
            tax_invoice_no=tax_invoice_no
        )
        db.add(new_order)
        await db.flush() # Get order ID

        generated_orders.append(new_order.id)

        # Create OrderItems and link bids
        for bid, tax_data in bids_tax_data:
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=auction.product_id,
                quantity=bid.allocated_qty,
                price=bid.bid_amount,
                status="pending",
                payment_status="pending",
                tax_amount=tax_data["total_tax"],
                cgst_rate=tax_data["cgst_rate"],
                sgst_rate=tax_data["sgst_rate"],
                igst_rate=tax_data["igst_rate"]
            )
            db.add(order_item)
            await db.flush()
            
            bid.order_id = new_order.id
            db.add(bid)

            if tax_data["tax_category_id"]:
                db.add(TaxLedger(
                    order_id=new_order.id,
                    order_item_id=order_item.id,
                    tax_category_id=tax_data["tax_category_id"],
                    taxable_amount=tax_data["taxable_amount"],
                    cgst_amount=tax_data["cgst_amount"],
                    sgst_amount=tax_data["sgst_amount"],
                    igst_amount=tax_data["igst_amount"],
                    total_tax=tax_data["total_tax"]
                ))

    await db.commit()
    return {"status": "success", "message": f"Auction finalized. Generated {len(generated_orders)} orders.", "order_ids": generated_orders}
