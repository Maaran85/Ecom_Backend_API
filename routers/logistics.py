from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.permissions import require_admin, require_logistics, require_logistics_or_admin, LOGISTICS_ROLES
from models import User, OrderItem, DeliveryRider, LogisticsPartner, Order, OrderStatus, OrderReturn, ReturnStatus, RiderReview, RiderEarning, LogisticsRemittance
from schemas.logistics import (
    LogisticsPartner as LogisticsPartnerSchema,
    LogisticsPartnerCreate,
    LogisticsPartnerUpdate,
    LogisticsStats,
    OrderAssignmentCreate,
    LogisticsUserCreate,
    LogisticsUserUpdate,
    RemittanceCreate,
    RemittanceResponse
)
from schemas.rider import Rider as RiderSchema, RiderAdminCreate, RiderUpdate
from core.security import get_password_hash
from schemas.user import User as UserSchema
from models import UserRole
from datetime import datetime
import os
import shutil
import traceback

router = APIRouter()

# --- Rider Management ---

@router.get("/riders", response_model=List[RiderSchema])
async def list_riders(
    partner_id: Optional[int] = None,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all delivery riders, optionally filtered by partner"""
    # If logistics partner manager, force filter to their own partner_id
    if current_user.role in [UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER]:
        partner_id = current_user.logistics_partner_id
        if not partner_id:
             return [] # Should not happen but safety first
             
    query = select(DeliveryRider).options(selectinload(DeliveryRider.user))
    if partner_id:
        query = query.where(DeliveryRider.partner_id == partner_id)
    
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/riders", response_model=RiderSchema)
async def create_rider_full(
    rider_in: RiderAdminCreate,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new delivery rider from scratch (Creates User + Rider Profile)"""
    # Ensure logistics partners only create riders for themselves
    if current_user.role in [UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER]:
        rider_in.partner_id = current_user.logistics_partner_id
    try:
        # Check if email exists
        check_user = await db.execute(select(User).where(User.email == rider_in.email, User.is_active == True))
        if check_user.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # 1. Create User
        new_user = User(
            email=rider_in.email,
            password_hash=get_password_hash(rider_in.password),
            full_name=rider_in.full_name,
            phone=rider_in.phone_number,
            dob=rider_in.dob,
            address=rider_in.address,
            aadhaar_number=rider_in.aadhaar_number,
            emergency_contact=rider_in.emergency_contact,
            photo_url=rider_in.photo_url,
            aadhaar_image=rider_in.aadhaar_image,
            role=UserRole.RIDER,
            is_active=True
        )
        db.add(new_user)
        await db.flush() # Get user ID
        
        # 2. Create Rider Profile
        rider_data = rider_in.model_dump(exclude={"full_name", "email", "password", "phone_number"})
        new_rider = DeliveryRider(
            user_id=new_user.id,
            **rider_data,
            created_by=current_user.id
        )
        db.add(new_rider)
        await db.commit()
        # Fetch with user relationship to satisfy schema properties (full_name, user_email)
        res = await db.execute(
            select(DeliveryRider)
            .options(selectinload(DeliveryRider.user))
            .where(DeliveryRider.id == new_rider.id)
        )
        return res.scalar_one()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/riders/{rider_id}", response_model=RiderSchema)
async def update_rider(
    rider_id: int,
    rider_in: RiderUpdate,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a delivery rider's profile and user account"""
    # Load user explicitly to update identity fields
    res = await db.execute(
        select(DeliveryRider)
        .options(selectinload(DeliveryRider.user))
        .where(DeliveryRider.id == rider_id)
    )
    rider = res.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    
    # Permission check for logistics partners
    if current_user.role in LOGISTICS_ROLES:
        if rider.partner_id != current_user.logistics_partner_id:
            raise HTTPException(status_code=403, detail="Not authorized to update this rider")
    
    update_data = rider_in.model_dump(exclude_unset=True)
    
    # Handle User model updates (identity fields)
    if rider.user:
        # Map fields between schemas/update_data and User model
        # some fields have different names or need multi-field updates
        if "full_name" in update_data:
            rider.user.full_name = update_data["full_name"]
        
        if "phone_number" in update_data:
            val = update_data.get("phone_number")
            if val and val != rider.user.phone:
                check_phone = await db.execute(
                    select(User).where(User.phone == val, User.id != rider.user.id)
                )
                if check_phone.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Phone number already registered to another user")

            rider.user.phone = val
            # Also update rider profile phone
            rider.phone_number = val
            
        # Other simple syncs
        for field in ["dob", "address", "aadhaar_number", "emergency_contact", "photo_url", "aadhaar_image"]:
            if field in update_data:
                setattr(rider.user, field, update_data[field])

    # Update Rider profile specific fields
    # Exclude properties/virtual fields from the update loop
    virtual_fields = {"full_name", "user_email", "email"}
    
    for key_raw, value in update_data.items():
        key = str(key_raw)
        if key not in virtual_fields and hasattr(rider, key):
            # Ensure it's an actual column or settable attribute, not a property
            attr = getattr(type(rider), key, None)
            if not isinstance(attr, property):
                setattr(rider, key, value)
    
    rider.updated_by = current_user.id
    await db.commit()
    
    # Re-fetch with relationship for final response serialization
    res = await db.execute(
        select(DeliveryRider)
        .options(selectinload(DeliveryRider.user))
        .where(DeliveryRider.id == rider_id)
    )
    return res.scalar_one()

@router.delete("/riders/{rider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rider(
    rider_id: int,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a rider profile and deactivate their user account"""
    try:
        res = await db.execute(select(DeliveryRider).where(DeliveryRider.id == rider_id))
        rider = res.scalar_one_or_none()
        if not rider:
            raise HTTPException(status_code=404, detail="Rider not found")
            
        # Permission check for logistics partners
        if current_user.role in LOGISTICS_ROLES:
            if rider.partner_id != current_user.logistics_partner_id:
                raise HTTPException(status_code=403, detail="Not authorized to delete this rider")
        
        # 1. Manually nullify/delete references to bypass DB constraints (since migrations aren't easy)
        # 1a. Nullify in OrderItems
        await db.execute(
            update(OrderItem)
            .where(OrderItem.rider_id == rider_id)
            .values(rider_id=None)
        )
        
        # 1b. Nullify in OrderReturns
        await db.execute(
            update(OrderReturn)
            .where(OrderReturn.rider_id == rider_id)
            .values(rider_id=None)
        )
        
        # 1c. Delete Earnings and Reviews (since they are non-nullable and linked to rider)
        from sqlalchemy import delete
        await db.execute(delete(RiderReview).where(RiderReview.rider_id == rider_id))
        await db.execute(delete(RiderEarning).where(RiderEarning.rider_id == rider_id))
        
        # 2. Fetch and deactivate associated user
        user_res = await db.execute(select(User).where(User.id == rider.user_id))
        user = user_res.scalar_one_or_none()
        if user:
            user.is_active = False
            db.add(user)
        
        # 3. Delete the rider profile
        await db.delete(rider)
        await db.commit()
        return None
    except Exception as e:
        await db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete rider: {str(e)}")

# --- Partner User Management ---

@router.post("/users/profile-photo")
async def upload_logistics_user_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_logistics_or_admin)
):
    """Upload a profile photo for a logistics user"""
    from core.config import settings
    
    # Simple local storage for now
    upload_dir = "uploads/logistics/profiles"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"profile_{current_user.id}_{int(datetime.now().timestamp())}{file_extension}"
    file_path = os.path.join(upload_dir, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"image_url": f"/static/logistics/profiles/{filename}"}

@router.post("/users/aadhaar-photo")
async def upload_logistics_user_aadhaar_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_logistics_or_admin)
):
    """Upload an Aadhaar card photo for a logistics user"""
    upload_dir = "uploads/logistics/aadhaar"
    os.makedirs(upload_dir, exist_ok=True)
    
    file_extension = os.path.splitext(file.filename)[1]
    filename = f"aadhaar_{current_user.id}_{int(datetime.now().timestamp())}{file_extension}"
    file_path = os.path.join(upload_dir, filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"image_url": f"/static/logistics/aadhaar/{filename}"}

@router.get("/users", response_model=List[UserSchema])
async def list_partner_users(
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all staff users belonging to the current logistics partner"""
    partner_id = current_user.logistics_partner_id
    if not partner_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Not associated with any partner")
        
    query = select(User).where(User.logistics_partner_id == partner_id)
    # Exclude riders from this list (they are managed elsewhere)
    query = query.where(User.role != UserRole.RIDER)
    
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/users")
async def create_partner_user(
    user_in: LogisticsUserCreate,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Add a new staff user (manager/admin) to the partner fleet"""
    # Ensure logistics partner admin is creating for their own partner_id
    if current_user.role in LOGISTICS_ROLES:
        user_in.logistics_partner_id = current_user.logistics_partner_id
        
    # Check if email exists
    check = await db.execute(select(User).where(User.email == user_in.email, User.is_active == True))
    if check.scalar_one_or_none():
         raise HTTPException(status_code=400, detail="Email already registered")
         
    new_user = User(
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
        logistics_partner_id=current_user.logistics_partner_id,
        phone=user_in.phone,
        dob=user_in.dob,
        address=user_in.address,
        aadhaar_number=user_in.aadhaar_number,
        photo_url=user_in.photo_url,
        aadhaar_image=user_in.aadhaar_image,
        employee_id=user_in.employee_id,
        shift_type=user_in.shift_type,
        emergency_contact=user_in.emergency_contact,
        is_active=user_in.is_active
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.patch("/users/{user_id}")
async def update_partner_user(
    user_id: int,
    user_in: LogisticsUserUpdate,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a staff user's details"""
    res = await db.execute(select(User).where(User.id == user_id))
    target_user = res.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if current_user.role in LOGISTICS_ROLES:
        if target_user.logistics_partner_id != current_user.logistics_partner_id:
            raise HTTPException(status_code=403, detail="Not authorized")
            
    update_data = user_in.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["password_hash"] = get_password_hash(update_data.pop("password"))
        
    for field, value in update_data.items():
        setattr(target_user, field, value)
        
    await db.commit()
    await db.refresh(target_user)
    return target_user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner_user(
    user_id: int,
    current_user: User = Depends(require_logistics_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Remove a staff user from the partner"""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if current_user.role in LOGISTICS_ROLES:
        if user.logistics_partner_id != current_user.logistics_partner_id:
            raise HTTPException(status_code=403, detail="Not authorized")
            
    await db.delete(user)
    await db.commit()
    return None

# --- Logistics Partners ---

@router.get("/stats", response_model=LogisticsStats)
async def get_logistics_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get logistics overview stats (Admin only)"""
    partners_count = await db.execute(select(func.count(LogisticsPartner.id)))
    total_partners = partners_count.scalar()
    
    active_partners_count = await db.execute(select(func.count(LogisticsPartner.id)).where(LogisticsPartner.is_active == True))
    active_partners = active_partners_count.scalar()
    
    assigned_count = await db.execute(select(func.count(OrderItem.id)).where(OrderItem.logistics_partner_id != None))
    total_assigned = assigned_count.scalar()
    
    pending_count = await db.execute(select(func.count(OrderItem.id)).where(OrderItem.logistics_partner_id == None, OrderItem.status == "pending"))
    pending_assignments = pending_count.scalar()
    
    return {
        "total_partners": total_partners,
        "active_partners": active_partners,
        "total_assigned_orders": total_assigned,
        "pending_assignments": pending_assignments
    }

@router.get("/partner/stats")
async def get_partner_stats(
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """Get logistics partner dashboard stats"""
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=400, detail="User not associated with a logistics partner")
    
    # 1. Total Riders count
    riders_res = await db.execute(select(func.count(DeliveryRider.id)).where(DeliveryRider.partner_id == partner_id))
    total_riders = riders_res.scalar() or 0
    
    # 2. Active Riders (User.is_active is True)
    # This is a bit simplified; real "active" might mean online status
    active_riders_res = await db.execute(
        select(func.count(DeliveryRider.id))
        .join(User, DeliveryRider.user_id == User.id)
        .where(DeliveryRider.partner_id == partner_id, User.is_active == True)
    )
    active_riders = active_riders_res.scalar() or 0
    
    # 3. Granular Order Stats
    assigned_orders_res = await db.execute(
        select(func.count(OrderItem.id))
        .where(OrderItem.logistics_partner_id == partner_id)
    )
    assigned_orders = assigned_orders_res.scalar() or 0

    dispatched_res = await db.execute(
        select(func.count(OrderItem.id))
        .where(OrderItem.logistics_partner_id == partner_id, func.lower(OrderItem.status) == OrderStatus.DISPATCHED.value.lower())
    )
    dispatched_orders = dispatched_res.scalar() or 0

    shipped_res = await db.execute(
        select(func.count(OrderItem.id))
        .where(OrderItem.logistics_partner_id == partner_id, func.lower(OrderItem.status) == OrderStatus.SHIPPED.value.lower())
    )
    shipped_orders = shipped_res.scalar() or 0

    out_for_delivery_res = await db.execute(
        select(func.count(OrderItem.id))
        .where(OrderItem.logistics_partner_id == partner_id, func.lower(OrderItem.status) == OrderStatus.OUT_FOR_DELIVERY.value.lower())
    )
    out_for_delivery_orders = out_for_delivery_res.scalar() or 0

    delivered_res = await db.execute(
        select(func.count(OrderItem.id))
        .where(OrderItem.logistics_partner_id == partner_id, OrderItem.status == OrderStatus.DELIVERED.value)
    )
    delivered_orders = delivered_res.scalar() or 0
    
    # 4. Earnings
    earnings_res = await db.execute(
        select(func.sum(RiderEarning.amount))
        .join(DeliveryRider, RiderEarning.rider_id == DeliveryRider.id)
        .where(DeliveryRider.partner_id == partner_id)
    )
    earnings = earnings_res.scalar() or 0.0
    
    return {
        "total_riders": total_riders,
        "active_riders": active_riders,
        "assigned_orders": assigned_orders,
        "dispatched_orders": dispatched_orders,
        "in_transit_orders": shipped_orders,
        "out_for_delivery": out_for_delivery_orders,
        "delivered_orders": delivered_orders,
        "earnings": float(earnings)
    }


@router.get("/earnings")
async def get_partner_earnings(
    period: str = "30days",  # today, 7days, 30days, 90days, all
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed earnings for current logistics partner"""
    from datetime import timedelta, timezone
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=400, detail="Not associated with a logistics partner")

    # Date filter
    now = datetime.now(tz=timezone.utc)
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7days":
        start_date = now - timedelta(days=7)
    elif period == "30days":
        start_date = now - timedelta(days=30)
    elif period == "90days":
        start_date = now - timedelta(days=90)
    else:
        start_date = None  # all time

    # Get all riders for this partner
    riders_res = await db.execute(
        select(DeliveryRider)
        .options(selectinload(DeliveryRider.user))
        .where(DeliveryRider.partner_id == partner_id)
    )
    riders = riders_res.scalars().all()
    rider_ids = [r.id for r in riders]
    rider_map = {r.id: r for r in riders}

    if not rider_ids:
        return {
            "total_earned": 0,
            "total_paid_out": 0,
            "total_pending": 0,
            "total_deliveries": 0,
            "period": period,
            "riders": [],
            "transactions": []
        }

    # Base earnings query filtered by partner riders
    earn_q = select(RiderEarning).where(RiderEarning.rider_id.in_(rider_ids))
    if start_date:
        earn_q = earn_q.where(RiderEarning.created_at >= start_date)
    earn_q = earn_q.options(
        selectinload(RiderEarning.rider).selectinload(DeliveryRider.user),
        selectinload(RiderEarning.order_item).selectinload(OrderItem.product),
        selectinload(RiderEarning.order_item).selectinload(OrderItem.order)
    ).order_by(RiderEarning.created_at.desc())

    earn_res = await db.execute(earn_q)
    all_earnings = earn_res.scalars().all()

    # Partner-level totals
    total_earned   = sum(e.amount for e in all_earnings if e.type != "payout")
    total_paid_out = sum(e.amount for e in all_earnings if e.type == "payout")
    total_pending  = total_earned - total_paid_out
    total_deliveries = sum(1 for e in all_earnings if e.type == "delivery")

    # Cash Collected (from delivered COD orders)
    cash_q = (
        select(OrderItem, Order)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            OrderItem.logistics_partner_id == partner_id,
            OrderItem.status == "delivered",
            Order.payment_method == "COD",
            OrderItem.logistics_remittance_id.is_(None)
        )
        .options(selectinload(OrderItem.product))
    )
    if start_date:
        cash_q = cash_q.where(OrderItem.delivered_at >= start_date)
    cash_res = await db.execute(cash_q)
    cash_items = cash_res.all()
    
    cash_collected = sum(float(item.price * item.quantity) for item, order in cash_items)

    # Per-rider breakdown
    rider_breakdown: dict = {}
    
    # Initialize all partner riders
    for r in riders:
        rider_breakdown[r.id] = {
            "rider_id": r.id,
            "rider_name": r.user.full_name if r.user else "Unknown",
            "earned": 0.0,
            "paid_out": 0.0,
            "pending": 0.0,
            "deliveries": 0,
            "cash_collected": 0.0
        }
    for e in all_earnings:
        rid = e.rider_id
        if rid in rider_breakdown:
            if e.type == "payout":
                rider_breakdown[rid]["paid_out"] += e.amount
            else:
                rider_breakdown[rid]["earned"] += e.amount
                if e.type == "delivery":
                    rider_breakdown[rid]["deliveries"] += 1

    for item, order in cash_items:
        rid = item.rider_id
        if rid in rider_breakdown:
            rider_breakdown[rid]["cash_collected"] += float(item.price * item.quantity)

    for v in rider_breakdown.values():
        v["pending"] = v["earned"] - v["paid_out"]

    # Combine earnings and cash collections into a single transactions list
    transactions = []
    
    # Add regular earnings
    for e in all_earnings:
        r = rider_map.get(e.rider_id)
        prod_name = None
        if e.order_item and e.order_item.product:
            prod_name = e.order_item.product.name
        transactions.append({
            "id": f"earn_{e.id}",
            "sort_date": e.created_at,
            "rider_name": r.user.full_name if r and r.user else "Unknown",
            "amount": float(e.amount),
            "type": e.type,
            "status": e.status,
            "description": e.description or (prod_name if prod_name else e.type.capitalize()),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "order_item_id": e.order_item_id,
            "order_number": e.order_item.order.order_number if e.order_item and e.order_item.order else (e.order_item.item_order_id if e.order_item else None),
        })
        
    # Add cash collections
    for item, order in cash_items:
        r = rider_map.get(item.rider_id)
        prod_name = item.product.name if item.product else "Unknown Product"
        transactions.append({
            "id": f"cash_{item.id}",
            "sort_date": item.delivered_at or item.updated_at,
            "rider_name": r.user.full_name if r and r.user else "Unknown",
            "amount": float(item.price * item.quantity),
            "type": "cash_collection",
            "status": "collected",
            "description": f"Cash (COD) - {prod_name}",
            "created_at": (item.delivered_at or item.updated_at).isoformat() if (item.delivered_at or item.updated_at) else None,
            "order_item_id": item.id,
            "order_number": order.order_number if order else item.item_order_id,
        })
        
    # Sort descending by date and take latest 50
    transactions.sort(key=lambda x: x["sort_date"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    
    # Cleanup sort_date
    for tx in transactions:
        tx.pop("sort_date", None)
        
    transactions = transactions[:50]

    return {
        "total_earned": float(total_earned),
        "total_paid_out": float(total_paid_out),
        "total_pending": float(total_pending),
        "total_deliveries": total_deliveries,
        "cash_collected": float(cash_collected),
        "period": period,
        "riders": list(rider_breakdown.values()),
        "transactions": transactions,
    }


@router.get("/partners", response_model=List[LogisticsPartnerSchema])
async def list_partners(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all logistics partners (Admin only)"""
    result = await db.execute(select(LogisticsPartner))
    return result.scalars().all()

@router.post("/partners", response_model=LogisticsPartnerSchema)
async def create_partner(
    partner_in: LogisticsPartnerCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new logistics partner (Admin only)"""
    db_partner = LogisticsPartner(**partner_in.model_dump())
    db.add(db_partner)
    await db.commit()
    await db.refresh(db_partner)
    return db_partner

@router.patch("/partners/{partner_id}", response_model=LogisticsPartnerSchema)
async def update_partner(
    partner_id: int,
    partner_in: LogisticsPartnerUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a logistics partner (Admin only)"""
    res = await db.execute(select(LogisticsPartner).where(LogisticsPartner.id == partner_id))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    update_data = partner_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(partner, key, value)
    
    await db.commit()
    await db.refresh(partner)
    return partner

@router.delete("/partners/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    partner_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a logistics partner (Admin only)"""
    res = await db.execute(select(LogisticsPartner).where(LogisticsPartner.id == partner_id))
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    
    # Check if partner is being used by any riders or order items
    # For now, let's just delete it, or we could prevent deletion if assigned
    await db.delete(partner)
    await db.commit()
    return None

@router.get("/pending-orders")
async def get_pending_assignments(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List order items pending logistics assignment (Admin only)"""
    # Join with Order to get shipping details
    query = (
        select(OrderItem)
        .options(selectinload(OrderItem.order))
        .where(OrderItem.logistics_partner_id == None)
        .where(OrderItem.status.in_(["pending", "packaging", "packed"]))
    )
    result = await db.execute(query)
    items = result.scalars().all()
    
    return [
        {
            "id": item.id,
            "order_number": item.order.order_number,
            "product_name": item.product.name if item.product else "Unknown",
            "quantity": item.quantity,
            "status": item.status,
            "shipping_address": item.order.shipping_address if item.order else None,
            "created_at": item.created_at
        }
        for item in items
    ]

@router.post("/assign")
async def assign_orders(
    assignment: OrderAssignmentCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Assign multiple order items to a partner and/or rider (Admin only)"""
    if not assignment.logistics_partner_id and not assignment.rider_id:
        raise HTTPException(status_code=400, detail="Must provide either logistics_partner_id or rider_id")
    
    # Update OrderItems
    # Update OrderItems
    stmt = (
        update(OrderItem)
        .where(OrderItem.id.in_(assignment.order_item_ids))
        .values(
            logistics_partner_id=assignment.logistics_partner_id,
            rider_id=assignment.rider_id,
            status=OrderStatus.DISPATCHED.value if assignment.logistics_partner_id else "shipped" # Initial state after assignment
        )
    )
    await db.execute(stmt)
    
    # Update parent orders status
    from core.order_status_logic import calculate_and_update_order_status
    # Get unique order IDs affected
    res = await db.execute(select(OrderItem.order_id).where(OrderItem.id.in_(assignment.order_item_ids)).distinct())
    order_ids = res.scalars().all()
    for oid in order_ids:
        await calculate_and_update_order_status(db, oid)

    await db.commit()
    
    return {"message": f"Successfully assigned {len(assignment.order_item_ids)} items"}

@router.get("/orders")
async def list_logistics_orders(
    status: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    limit: int = 100,
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """List orders assigned to the current logistics partner"""
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        return {"items": [], "total": 0}

    # Base query for OrderItems assigned to this partner OR returns assigned to this partner
    query = (
        select(OrderItem)
        .outerjoin(OrderReturn, OrderItem.id == OrderReturn.order_item_id)
        .options(
            selectinload(OrderItem.order).selectinload(Order.customer),
            selectinload(OrderItem.product).selectinload(__import__('models.product', fromlist=['Product']).Product.dealer),
            selectinload(OrderItem.rider).selectinload(DeliveryRider.user)
        )
        .where(
            (OrderItem.logistics_partner_id == partner_id) | 
            (OrderReturn.logistics_partner_id == partner_id)
        )
    )

    if status:
        query = query.where(func.lower(OrderItem.status) == status.lower())
    
    if start_date:
        query = query.where(OrderItem.created_at >= start_date)
    if end_date:
        query = query.where(OrderItem.created_at <= end_date)

    if search:
        search_filter = f"%{search}%"
        query = query.join(Order, OrderItem.order_id == Order.id).where(
            (Order.order_number.ilike(search_filter)) |
            (OrderItem.item_order_id.ilike(search_filter))
        )

    # Count total
    total_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(total_query)
    total = total_res.scalar() or 0

    # Pagination
    query = query.order_by(OrderItem.id.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    # Extra: fetch active returns
    order_ids = list(set([item.order_id for item in items]))
    returns_map = {}
    if order_ids:
        returns_res = await db.execute(select(OrderReturn).where(OrderReturn.order_id.in_(order_ids)))
        for r in returns_res.scalars().all():
            returns_map[f"{r.order_id}_{r.order_item_id}"] = r
            if r.order_item_id is None:
                returns_map[f"{r.order_id}_None"] = r

    # Format response
    formatted_items = []
    for item in items:
        order = item.order
        prod = item.product
        rider = item.rider
        
        item_ret = returns_map.get(f"{item.order_id}_{item.id}") or returns_map.get(f"{item.order_id}_None")
        return_status = item_ret.status.value if item_ret and hasattr(item_ret.status, 'value') else (item_ret.status if item_ret else None)
        return_id = item_ret.id if item_ret else None
        
        # We group items by order for the frontend LogisticsOrder schema
        # but in this case, we act on individual OrderItems.
        # Minimal mapping to match frontend LogisticsOrder interface:
        formatted_items.append({
            "id": order.id,
            "order_number": order.order_number or f"ORD-{order.id}",
            "created_at": order.created_at,
            "total_amount": float(item.price * item.quantity),
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "payment_method": order.payment_method,
            "shipping_address": "Customer Address", # Placeholder or fetch if needed
            "customer_name": order.customer.full_name if order.customer else "Customer",
            "customer_phone": order.customer.phone if order.customer else "",
            "dealer_name": prod.dealer.business_name if prod and prod.dealer else "Dealer",
            "items": [{
                "id": item.id,
                "product_id": item.product_id,
                "product_name": prod.name if prod else "Unknown",
                "quantity": item.quantity,
                "price": float(item.price),
                "status": item.status,
                "item_order_id": item.item_order_id,
                "payment_status": item.payment_status,
                "logistics_remittance_id": item.logistics_remittance_id,
                "rider_name": rider.user.full_name if rider and rider.user else None,
                "rider_id": item.rider_id,
                "return_status": return_status,
                "return_id": return_id,
                "is_exchange": item_ret.is_exchange if item_ret else False
            }]
        })

    return {"items": formatted_items, "total": total}


@router.get("/orders/{order_id}")
async def get_logistics_order_detail(
    order_id: int,
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """Get full details for a specific order assigned to the current logistics partner"""
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=403, detail="Not associated with a logistics partner")

    from models import Address
    from models.product import Product
    from models.dealer import Dealer

    # Fetch order
    order_res = await db.execute(
        select(Order)
        .options(
            selectinload(Order.customer),
            selectinload(Order.shipping_address),
            selectinload(Order.payment),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(Order.items).selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
        )
        .where(Order.id == order_id)
    )
    order = order_res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify at least one item or return belongs to this partner
    from models.order_return import OrderReturn
    partner_items = [i for i in order.items if i.logistics_partner_id == partner_id]
    
    # Also check returns
    returns_res = await db.execute(select(OrderReturn).where(OrderReturn.order_id == order_id, OrderReturn.logistics_partner_id == partner_id))
    partner_returns = returns_res.scalars().all()
    
    if not partner_items and not partner_returns:
        raise HTTPException(status_code=403, detail="No items or returns in this order are assigned to your partner")
    
    # If there are returns for this partner but the items themselves aren't theirs, 
    # we should include those items anyway for return management
    return_item_ids = {r.order_item_id for r in partner_returns if r.order_item_id}
    partner_items_all = list(set(partner_items + [i for i in order.items if i.id in return_item_ids]))

    # Build address string
    addr = order.shipping_address
    if addr:
        addr_parts = [
            getattr(addr, 'address_line1', ''),
            getattr(addr, 'address_line2', ''),
            getattr(addr, 'landmark', ''),
            getattr(addr, 'city', ''),
            getattr(addr, 'state', ''),
            getattr(addr, 'postcode', getattr(addr, 'pincode', '')),
        ]
        addr_str = ", ".join([p for p in addr_parts if p])
    else:
        addr_str = "No address provided"

    # Filter for active returns
    from models.order_return import OrderReturn
    returns_query = select(OrderReturn).where(OrderReturn.order_id == order_id)
    returns_res = await db.execute(returns_query)
    returns_map = {r.order_item_id: r for r in returns_res.scalars().all()}
    global_return = returns_map.get(None)

    # Format items (partner's items + items with returns for this partner)
    items_out = []
    for item in partner_items_all:
        prod = item.product
        rider = item.rider
        
        item_ret = returns_map.get(item.id) or global_return
        return_status = item_ret.status.value if item_ret and hasattr(item_ret.status, 'value') else (item_ret.status if item_ret else None)
        return_id = item_ret.id if item_ret else None

        items_out.append({
            "id": item.id,
            "item_order_id": item.item_order_id,
            "product_id": item.product_id,
            "product_name": prod.name if prod else "Unknown Product",
            "product_image": prod.images[0] if prod and prod.images else None,
            "quantity": item.quantity,
            "price": float(item.price),
            "size": item.size,
            "status": item.status,
            "payment_status": item.payment_status,
            "courier_company": item.courier_company,
            "tracking_number": item.tracking_number,
            "tracking_url": item.tracking_url,
            "dispatch_date": item.dispatch_date.isoformat() if item.dispatch_date else None,
            "estimated_delivery": item.estimated_delivery.isoformat() if item.estimated_delivery else None,
            "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
            "hub_id": item.hub_id,
            "hub_arrived_at": item.hub_arrived_at.isoformat() if item.hub_arrived_at else None,
            "tax_amount": float(item.tax_amount or 0),
            "cgst_rate": float(item.cgst_rate or 0),
            "sgst_rate": float(item.sgst_rate or 0),
            "igst_rate": float(item.igst_rate or 0),
            "hsn_code": item.hsn_code,
            "platform_fee": float(item.platform_fee or 0),
            "dealer_name": prod.dealer.business_name if prod and prod.dealer else "N/A",
            "rider_id": item.rider_id,
            "rider_name": rider.user.full_name if rider and rider.user else None,
            "rider_phone": rider.phone_number if rider else None,
            "delivery_attempts": getattr(item, 'delivery_attempts', 0),
            "reject_reason": item.reject_reason,
            "return_status": return_status,
            "return_id": return_id,
            "return_reason": item_ret.reason if item_ret else None,
            "return_pickup_date": item_ret.pickup_date.isoformat() if item_ret and item_ret.pickup_date else None,
            "return_requested_at": item_ret.requested_at.isoformat() if item_ret and item_ret.requested_at else None,
            "is_exchange": item_ret.is_exchange if item_ret else False,
            "exchange_variant_id": item_ret.exchange_variant_id if item_ret else None,
        })

    return {
        "id": order.id,
        "order_number": order.order_number or f"ORD-{order.id}",
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        "payment_method": order.payment_method or "COD",
        "total_amount": float(order.total_amount or 0),
        "subtotal": float(order.subtotal or 0),
        "discount_amount": float(order.discount_amount or 0),
        "notes": order.notes,
        "shipping_address": addr_str,
        "customer_name": order.customer.full_name if order.customer else "N/A",
        "customer_phone": order.customer.phone if order.customer else "N/A",
        "items": items_out,
    }

@router.put("/orders/{order_id}/return-status")
async def update_logistics_return_status(
    order_id: int,
    payload: dict,
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """
    Update return status by Logistics (e.g. Assign Rider, Send to Hub).
    Payload should contain: status (string), order_item_id (int), optional rider_id (int).
    """
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=400, detail="User not associated with a logistics partner")
        
    status_str = payload.get("status")
    order_item_id = payload.get("order_item_id")
    rider_id = payload.get("rider_id")
    
    if not status_str or not order_item_id:
        raise HTTPException(status_code=400, detail="Missing status or order_item_id")
        
    # Find active return
    from sqlalchemy import or_
    query = (
        select(OrderReturn)
        .join(OrderItem, OrderReturn.order_item_id == OrderItem.id)
        .where(OrderReturn.order_id == order_id)
        .where(OrderReturn.order_item_id == order_item_id)
        .where(
            or_(
                OrderReturn.logistics_partner_id == partner_id,
                OrderItem.logistics_partner_id == partner_id,
            )
        )
        .order_by(OrderReturn.requested_at.desc())
    )
    res = await db.execute(query)
    order_return = res.scalar_one_or_none()
    
    if not order_return:
        raise HTTPException(status_code=404, detail="Return record not found or not assigned to your logistics partner")
    
    # Stamp partner_id on the return if missing (data repair for old records)
    if not order_return.logistics_partner_id:
        order_return.logistics_partner_id = partner_id

        
    # GATED FLOW: Ensure return is already APPROVED before logistics acts on it
    if order_return.status == ReturnStatus.REQUESTED:
        raise HTTPException(status_code=400, detail="Return must be approved by admin before logistics processing")
    try:
        new_status = ReturnStatus(status_str.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid return status: {status_str}")
        
    # LOGISTICS PROTECTION: Logistics cannot mark as REFUNDED manually for online orders
    if new_status == ReturnStatus.REFUNDED:
        # Check if online order (needs admin to record UTR)
        from core.permissions import is_online_payment_method
        # We need to fetch order to check payment method
        await db.refresh(order_return, attribute_names=['order'])
        if order_return.order and order_return.order.payment_method:
            if is_online_payment_method(order_return.order.payment_method):
                raise HTTPException(status_code=403, detail="Refunds for online orders must be processed by Admin (UTR recording)")

    # Automatically choose between OUT_FOR_PICKUP and OUT_FOR_SWAP for exchanges
    if new_status == ReturnStatus.OUT_FOR_PICKUP and order_return.is_exchange:
        new_status = ReturnStatus.OUT_FOR_SWAP
        
    order_return.status = new_status
    if rider_id is not None:
        order_return.rider_id = rider_id
        
    # Fetch item to update status depending on flow
    res_item = await db.execute(select(OrderItem).where(OrderItem.id == order_item_id))
    order_item = res_item.scalar_one_or_none()
    if order_item:
        if new_status in [ReturnStatus.OUT_FOR_PICKUP, ReturnStatus.OUT_FOR_SWAP]:
            order_item.status = "returning"
        elif new_status == ReturnStatus.SWAP_COMPLETED:
            order_item.status = "exchanged"
            # Record payment collection if extra amount was due
            if order_return.extra_amount_to_collect > 0:
                payment_collected = payload.get("payment_collected", False)
                if payment_collected:
                    order_return.refund_initiated = True # Using this as a flag for payment recorded for now
                    order_return.admin_notes = (order_return.admin_notes or "") + f"\n[Payment] Extra amount ₹{order_return.extra_amount_to_collect} collected by rider."
        elif new_status == ReturnStatus.EXCHANGE_COMPLETED:
             order_item.status = "exchanged"
             order_return.completed_at = datetime.now(timezone.utc)
        elif new_status in [ReturnStatus.COMPLETED, ReturnStatus.REFUNDED]:
            order_item.status = "returned"
            order_return.completed_at = datetime.now(timezone.utc)
            
    await db.commit()
    await db.refresh(order_return)
    return {"message": f"Return status updated to {new_status.value}", "status": new_status.value, "extra_amount_due": order_return.extra_amount_to_collect}


@router.post("/remittances", response_model=RemittanceResponse, status_code=status.HTTP_201_CREATED)
async def create_remittance(
    remittance_in: RemittanceCreate,
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """Create a new COD cash remittance to the platform admin"""
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=400, detail="Only logistics partners can create remittances")
        
    db_remittance = LogisticsRemittance(
        logistics_partner_id=partner_id,
        amount=remittance_in.amount,
        reference_no=remittance_in.reference_no,
        payment_method=remittance_in.payment_method,
        payment_date=remittance_in.payment_date,
        notes=remittance_in.notes,
        status="pending"
    )
    db.add(db_remittance)
    await db.flush() # Get ID
    
    # Link specified order items to this remittance
    if remittance_in.order_item_ids:
        # Verify these items belong to this partner and are delivered COD
        # Also ensure they aren't already linked to another remittance
        stmt = (
            update(OrderItem)
            .where(
                OrderItem.id.in_(remittance_in.order_item_ids),
                OrderItem.logistics_partner_id == partner_id,
                OrderItem.logistics_remittance_id.is_(None)
            )
            .values(logistics_remittance_id=db_remittance.id)
        )
        await db.execute(stmt)

    await db.commit()
    await db.refresh(db_remittance)
    return db_remittance

@router.get("/remittances", response_model=List[RemittanceResponse])
async def list_remittances(
    skip: int = 0, limit: int = 50,
    current_user: User = Depends(require_logistics),
    db: AsyncSession = Depends(get_db)
):
    """List all remittances for the current logistics partner"""
    partner_id = current_user.logistics_partner_id
    if not partner_id:
        raise HTTPException(status_code=400, detail="Not associated with a logistics partner")
        
    query = (
        select(LogisticsRemittance)
        .where(LogisticsRemittance.logistics_partner_id == partner_id)
        .order_by(LogisticsRemittance.created_at.desc())
        .offset(skip).limit(limit)
    )
    result = await db.execute(query)
    remittances = result.scalars().all()
    
    # Enrich with order numbers
    enriched_remittances = []
    for r in remittances:
        items_query = (
            select(Order.order_number)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.logistics_remittance_id == r.id)
            .distinct()
        )
        items_res = await db.execute(items_query)
        order_numbers = items_res.scalars().all()
        
        r_dict = {
            "id": r.id,
            "logistics_partner_id": r.logistics_partner_id,
            "amount": r.amount,
            "status": r.status,
            "reference_no": r.reference_no,
            "payment_method": r.payment_method,
            "notes": r.notes,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "confirmed_at": r.confirmed_at,
            "confirmed_by_admin_id": r.confirmed_by_admin_id,
            "order_numbers": order_numbers
        }
        enriched_remittances.append(r_dict)
        
    return enriched_remittances
