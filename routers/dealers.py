"""
Dealer management router
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional, List, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Dealer, UserRole, Order, OrderItem, Product, DeliveryRider, CustomerUser
from models.cart import OrderStatus
from models.order_return import OrderReturn, ReturnStatus
from models.payment import PaymentStatus
from schemas.dealer import DealerCreate, DealerUpdate, DealerProfileComplete, Dealer as DealerSchema, DealerWithUser, DealerOrderResponse, OrderItemDealer, DealerStockUpdate
from schemas.rider import Rider as RiderSchema
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
from models.flash_sale import FlashSale
from schemas.flash_sale import FlashSaleCreate, FlashSale as FlashSaleSchema
from schemas.logistics import LogisticsPartner as LogisticsPartnerSchema
from models.logistics_partner import LogisticsPartner
from models.dealer_logistics import dealer_logistics_mapping

router = APIRouter()

from models.hub import DeliveryHub
from models.inventory import ProductInventory, MovementType, StockMovement
# Role Category Definitions (Values as strings for robustness)
HUB_ROLES_STR = ["hub", "hub_manager", "hub_staff", "hub_dispatcher", "hub_returns"]
DEALER_ROLES_STR = ["dealer", "dealer_manager", "dealer_inventory", "dealer_orders", "dealer_finance"]
SHOWROOM_ROLES_STR = ["showroom_manager", "showroom_staff"]
RIDER_ROLES_STR = ["rider", "delivery_partner"]
ADMIN_ROLES_STR = ["admin", "super_admin"]

MANAGEMENT_AND_HUB_ROLES = DEALER_ROLES_STR + HUB_ROLES_STR + ADMIN_ROLES_STR
LOGISTICS_ROLES_STR = ["logistics_admin", "logistics_manager"]
ALL_MANAGEMENT_ROLES = DEALER_ROLES_STR + HUB_ROLES_STR + SHOWROOM_ROLES_STR + RIDER_ROLES_STR + ADMIN_ROLES_STR + LOGISTICS_ROLES_STR

HUB_ROLES = [
    UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, 
    UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS
]
DEALER_ROLES_ALL = [
    UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY,
    UserRole.DEALER_ORDERS, UserRole.DEALER_FINANCE
]
SHOWROOM_ROLES = [UserRole.SHOWROOM_MANAGER, UserRole.SHOWROOM_STAFF]
RIDER_ROLES = [UserRole.RIDER, UserRole.DELIVERY_PARTNER]

class UserManageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
    
    id: int
    email: str
    full_name: Optional[str] = None
    role: UserRole
    is_active: bool
    is_approved: Optional[bool] = None
    created_at: Optional[datetime] = None
    hub_id: Optional[int] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    dob: Optional[str] = None
    # Rider Profile Extensions
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    vehicle_model: Optional[str] = None
    insurance_expiry: Optional[str] = None
    aadhaar_image: Optional[str] = None
    license_image: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

class UserManageCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.DEALER
    is_active: bool = True
    is_approved: bool = True
    hub_id: Optional[int] = None
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    dob: Optional[str] = None
    # Rider Profile Extensions
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    vehicle_model: Optional[str] = None
    insurance_expiry: Optional[str] = None
    aadhaar_image: Optional[str] = None
    license_image: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None

class UserManageUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    is_approved: Optional[bool] = None
    hub_id: Optional[int] = None
    employee_id: Optional[str] = None
    shift_type: Optional[str] = None
    dob: Optional[str] = None
    # Rider Profile Extensions
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    vehicle_model: Optional[str] = None
    insurance_expiry: Optional[str] = None
    aadhaar_image: Optional[str] = None
    license_image: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None

class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    user_name: Optional[str] = None
    
    class Config:
        from_attributes = True
    hub_id: Optional[int] = None
    # Rider Profile Extensions
    license_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    vehicle_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None
    vehicle_model: Optional[str] = None
    insurance_expiry: Optional[str] = None
    aadhaar_image: Optional[str] = None
    license_image: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_id: Optional[str] = None

async def get_current_dealer(user: User, db: AsyncSession) -> Dealer:
    # 1. Check if user IS the primary dealer user
    res = await db.execute(select(Dealer).options(selectinload(Dealer.state_rel)).where(Dealer.is_deleted == False).where(Dealer.user_id == user.id))
    dealer = res.scalar_one_or_none()
    if dealer:
        return dealer
    
    # 2. Check if user is staff (has dealer_id)
    if user.dealer_id:
        res = await db.execute(select(Dealer).options(selectinload(Dealer.state_rel)).where(Dealer.is_deleted == False).where(Dealer.id == user.dealer_id))
        dealer = res.scalar_one_or_none()
        if dealer:
            return dealer
            
    # 3. Check if hub user (staff or manager)
    if user.hub_id:
        res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).join(DeliveryHub).where(DeliveryHub.id == user.hub_id))
        dealer = res.scalar_one_or_none()
        if dealer:
            return dealer

    # 4. Backwards compatibility check for old hub manager linkage (where hub.user_id was set)
    # This covers cases where a user is a hub manager but doesn't have user.hub_id directly set.
    res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).join(DeliveryHub).where(DeliveryHub.user_id == user.id))
    dealer = res.scalar_one_or_none()
    if dealer:
        return dealer
        
    return None

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Dealer Discount Schedules (Flash Sales scoped to the dealer)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class DealerDiscountCreate(BaseModel):
    name: str
    discount_percentage: float
    start_time: datetime
    end_time: datetime
    product_ids: list[UUID] = []

@router.get("/discounts", response_model=list[FlashSaleSchema])
async def get_dealer_discounts(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all discount schedules for current dealer."""
    # Resolve dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(FlashSale).where(FlashSale.dealer_id == dealer.id).order_by(FlashSale.created_at.desc())
    )
    return result.scalars().all()


@router.post("/discounts", response_model=FlashSaleSchema, status_code=status.HTTP_201_CREATED)
async def create_dealer_discount(
    payload: DealerDiscountCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a discount schedule for current dealer."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    sale = FlashSale(
        name=payload.name,
        discount_percentage=payload.discount_percentage,
        start_time=payload.start_time,
        end_time=payload.end_time,
        product_ids=payload.product_ids,
        dealer_id=dealer.id,
        is_active=True,
    )
    db.add(sale)
    await db.commit()
    await db.refresh(sale)
    return sale


@router.delete("/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dealer_discount(
    discount_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a dealer's own discount schedule."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(FlashSale).where(FlashSale.id == discount_id, FlashSale.dealer_id == dealer.id)
    )
    sale = result.scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Discount not found or not owned by you")

    await db.delete(sale)
    await db.commit()
    return None


@router.put("/discounts/{discount_id}", response_model=FlashSaleSchema)
async def update_dealer_discount(
    discount_id: int,
    payload: DealerDiscountCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a dealer's own discount schedule."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(FlashSale).where(FlashSale.id == discount_id, FlashSale.dealer_id == dealer.id)
    )
    sale = result.scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Discount not found or not owned by you")

    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    sale.name = payload.name
    sale.discount_percentage = payload.discount_percentage
    sale.start_time = payload.start_time
    sale.end_time = payload.end_time
    sale.product_ids = payload.product_ids
    
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(sale, "product_ids")
    
    await db.commit()
    await db.refresh(sale)
    return sale

class DealerPaginatedOrders(BaseModel):
    items: List[DealerOrderResponse]
    total: int
    page: int
    limit: int

@router.get("/orders", response_model=DealerPaginatedOrders)
async def get_dealer_orders(
    status: Optional[str] = None,
    type: Optional[str] = "new",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    hub_id: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get orders containing products from the current dealer.
    Note: If mixed with other dealers' products, shows entire order for now.
    """
    # 1. Verify user is a dealer or hub
    if current_user.role not in ALL_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    provided_hub_id = hub_id
    hub_id = None
    dealer_id = None
    
    # Resolve dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    dealer_id = dealer.id

    # If it's a HUB user and no hub_id was provided, we could default to their hub,
    # but the user wants it to be a "copy from dealers" (seeing everything).
    # So we only filter by hub if provided_hub_id is set.
    if provided_hub_id:
        hub_id = provided_hub_id
    elif current_user.role in [UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS]:
        # We still verify the hub exists for the user, but we don't force filter unless requested
        hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
        hub = hub_result.scalar_one_or_none()
        if not hub:
            # If user.hub_id is set, use that to find the hub
            if current_user.hub_id:
                hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.id == current_user.hub_id))
                hub = hub_result.scalar_one_or_none()
            if not hub:
                raise HTTPException(status_code=404, detail="Hub profile not found for this user")
        # hub_id = hub.id  <-- We intentionally don't force this now


    # 3. Find orders containing this dealer's products
    from sqlalchemy.orm import selectinload
    from sqlalchemy import func, or_
    
    from models.order_return import OrderReturn
    
    skip = (page - 1) * limit

    # Log the identity for debugging
    print(f"DEBUG: get_dealer_orders for User={current_user.id}, Dealer={dealer_id}, Hub={hub_id}, Type={type}, Status={status}")

    # 3.1 Start with a clean Order query
    from sqlalchemy import exists, cast, String as AlchemyString
    base_query = select(Order)
    
    # NEW: Exclude showroom orders immediately
    base_query = base_query.where(~Order.order_number.ilike("SR-%"))
    
    # 3.2 Basic Dealer/Hub Item Match
    item_match = (
        select(OrderItem.id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id == Order.id)
    )
    if dealer_id:
        item_match = item_match.where(Product.dealer_id == dealer_id)
    if hub_id:
        item_match = item_match.where(OrderItem.hub_id == hub_id)

    # 3.2 Add status filtering to the item match if status is provided
    if status:
        if type in ["return", "exchange"]:
            status_enum_val = str(status).upper()
            if status_enum_val == 'REJECTED':
                item_match = item_match.join(OrderReturn, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
                item_match = item_match.where(cast(OrderReturn.status, AlchemyString).in_(['REJECTED', 'PICKUP_FAILED']))
            else:
                item_match = item_match.join(OrderReturn, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
                item_match = item_match.where(cast(OrderReturn.status, AlchemyString) == status_enum_val)
        else:
            s_lower = str(status).lower()
            if s_lower in ['cancelled', 'failed', 'rejected', 'undelivered', 'returned']:
                item_match = item_match.where(or_(
                    func.lower(OrderItem.status).in_(['cancelled', 'rejected', 'undelivered', 'returned', 'failed']),
                    func.lower(cast(Order.status, AlchemyString)).in_(['cancelled', 'failed'])
                ))
            elif s_lower in ['order_placed', 'new', 'pending']:
                item_match = item_match.where(
                    func.lower(OrderItem.status).in_(['order_placed', 'pending']),
                    func.lower(cast(Order.status, AlchemyString)) != 'cancelled'
                )
            elif s_lower == 'confirmed':
                item_match = item_match.where(
                    func.lower(OrderItem.status).in_(['confirmed', 'processing']),
                    func.lower(cast(Order.status, AlchemyString)) != 'cancelled'
                )
            elif s_lower == 'packaging':
                item_match = item_match.where(
                    func.lower(OrderItem.status).in_(['packaging', 'packed']),
                    func.lower(cast(Order.status, AlchemyString)) != 'cancelled'
                )
            elif s_lower == 'dispatched':
                item_match = item_match.where(
                    func.lower(OrderItem.status).in_(['dispatched', 'at_hub']),
                    func.lower(cast(Order.status, AlchemyString)) != 'cancelled'
                )
            else:
                item_match = item_match.where(
                    func.lower(OrderItem.status) == s_lower,
                    func.lower(cast(Order.status, AlchemyString)) != 'cancelled'
                )
    
    # 3.3 Add global type filtering
    if type == "return":
        item_match = item_match.join(OrderReturn, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        item_match = item_match.where(OrderReturn.is_exchange == False)
    elif type == "exchange":
        item_match = item_match.join(OrderReturn, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        item_match = item_match.where(OrderReturn.is_exchange == True)
    elif type == "auction":
        base_query = base_query.where(Order.is_auction_order == True)
    elif type == "new":
        pass

    # Now apply the combined match to the base query
    base_query = base_query.where(exists(item_match))

    # Search filter (applies to the whole Order)
    if search:
        search_query = f"%{search}%"
        from models.customer_user import CustomerUser
        base_query = base_query.outerjoin(CustomerUser, Order.customer_id == CustomerUser.id).where(or_(
            Order.order_number.ilike(search_query),
            Order.customer_name.ilike(search_query),
            CustomerUser.full_name.ilike(search_query)
        ))
        
    from datetime import datetime
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            base_query = base_query.where(Order.created_at >= sd)
        except ValueError:
            pass
            
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            base_query = base_query.where(Order.created_at <= ed)
        except ValueError:
            pass

    # To get total count (distinct orders)
    count_query = select(func.count(Order.id)).select_from(base_query.alias("sub"))
    total_count_result = await db.execute(count_query)
    total_count = total_count_result.scalar() or 0
    print(f"DEBUG: Found total_count={total_count} matching orders")

    query = (
        base_query
        .distinct()
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.items).selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
            selectinload(Order.shipping_address),
            selectinload(Order.returns).selectinload(OrderReturn.exchange_variant),
            selectinload(Order.customer)
        )
        .offset(skip)
        .limit(limit)
        .order_by(Order.created_at.desc())
    )
    
    result = await db.execute(query)
    orders = result.scalars().unique().all()
    
    # Transform to schema (simplified)
    response = []
    for order in orders:
        dealer_items = []
        dealer_order_total = 0.0
        for item in order.items:
             prod = item.product
             
             # Filter items by dealer AND hub (if hub user)
             if prod and prod.dealer_id == dealer_id and (hub_id is None or item.hub_id == hub_id):
                 # Find return for this specific item if any
                 item_return = None
                 if hasattr(order, 'returns') and order.returns:
                     # Match specifically by order_item_id, or if no item is specified (applies to all)
                     item_return = next((r for r in order.returns if r.order_item_id == item.id or r.order_item_id is None), None)

                 if status:
                     if type in ["return", "exchange"]:
                         if not item_return:
                             continue
                         ret_status_val = str(item_return.status.value if hasattr(item_return.status, 'value') else item_return.status).upper()
                         status_upper = str(status).upper()
                         if status_upper == 'REJECTED':
                             if ret_status_val not in ['REJECTED', 'PICKUP_FAILED']:
                                 continue
                         elif ret_status_val != status_upper:
                             continue
                     else:
                         item_status_lower = str(item.status).lower() if item.status else ""
                         order_status_lower = str(order.status.value if hasattr(order.status, 'value') else order.status).lower() if order.status else ""
                         s_lower = str(status).lower()
                         if s_lower in ['cancelled', 'failed', 'rejected', 'undelivered', 'returned']:
                             if not (item_status_lower in ['cancelled', 'rejected', 'undelivered', 'returned', 'failed'] or order_status_lower in ['cancelled', 'failed']):
                                 continue
                         elif s_lower in ['order_placed', 'new', 'pending']:
                             if not (item_status_lower in ['order_placed', 'pending'] and order_status_lower != 'cancelled'):
                                 continue
                         elif s_lower == 'confirmed':
                             if not (item_status_lower in ['confirmed', 'processing'] and order_status_lower != 'cancelled'):
                                 continue
                         elif s_lower == 'packaging':
                             if not (item_status_lower in ['packaging', 'packed'] and order_status_lower != 'cancelled'):
                                 continue
                         elif s_lower == 'dispatched':
                             if not (item_status_lower in ['dispatched', 'at_hub'] and order_status_lower != 'cancelled'):
                                 continue
                         else:
                             if not (item_status_lower == s_lower and order_status_lower != 'cancelled'):
                                 continue

                 dealer_items.append(OrderItemDealer(
                     id=item.id,
                     item_order_id=getattr(item, 'item_order_id', f"ITEM-{item.id}"),
                     product_id=prod.id,
                     product_name=prod.name,
                     quantity=item.quantity,
                     price=item.price,
                     mrp=(item.variant.mrp if hasattr(item, 'variant') and item.variant and item.variant.mrp else None) or prod.mrp or item.price,
                     variant_attributes=item.variant_attributes,
                     product_image=prod.images[0] if prod.images else None,
                     status=OrderStatus.CANCELLED.value if order.status == OrderStatus.CANCELLED else item.status,
                     reject_reason=item.reject_reason,
                     courier_company=item.courier_company,
                     tracking_number=item.tracking_number,
                     tracking_url=item.tracking_url,
                     dispatch_date=item.dispatch_date,
                     estimated_delivery=item.estimated_delivery,
                     delivered_at=item.delivered_at,
                      accepted_at=item.accepted_at,
                      hub_id=item.hub_id,
                      hub_arrived_at=item.hub_arrived_at,
                      tax_amount=item.tax_amount,
                      cgst_rate=item.cgst_rate,
                      sgst_rate=item.sgst_rate,
                      igst_rate=item.igst_rate,
                      hsn_code=item.hsn_code,
                      platform_fee=item.platform_fee,
                       logistics_partner_id=getattr(item, 'logistics_partner_id', None),
                     return_status=item_return.status.value if item_return and hasattr(item_return.status, 'value') else (item_return.status if item_return else None),
                     return_reason=item_return.reason if item_return else None,
                     return_id=item_return.id if item_return else None,
                     return_pickup_date=item_return.pickup_date if item_return else None,
                     payment_status=item.payment_status,
                     rider_id=item.rider_id,
                     rider_name=item.rider.user.full_name if (item.rider and item.rider.user) else None,
                     rider_phone=item.rider.phone_number if item.rider else None,
                     delivery_attempts=getattr(item, 'delivery_attempts', 0),
                     is_exchange=getattr(item_return, 'is_exchange', False) if item_return else False,
                     exchange_variant_id=getattr(item_return, 'exchange_variant_id', None) if item_return else None,
                     exchange_variant=item_return.exchange_variant.attributes if item_return and hasattr(item_return.exchange_variant, 'attributes') else None
                 ))
                 dealer_order_total += (item.quantity * item.price)
        
        if dealer_items:
            # Address string
            addr_str = "No address"
            if order.shipping_address:
                # Join all address parts for full details
                addr = order.shipping_address
                parts = [
                    getattr(addr, 'address_line1', getattr(addr, 'street_address', '')),
                    getattr(addr, 'address_line2', ''),
                    getattr(addr, 'landmark', ''),
                    getattr(addr, 'city', ''),
                    getattr(addr, 'state', ''),
                    getattr(addr, 'pincode', getattr(addr, 'postal_code', ''))
                ]
                addr_str = ", ".join([p for p in parts if p])
                customer_lat = getattr(addr, 'latitude', None)
                customer_long = getattr(addr, 'longitude', None)
            else:
                customer_lat = None
                customer_long = None
                
            return_status = None
            return_reason = None
            refund_amount = None
            if type in ["return", "exchange"] and getattr(order, 'returns', None):
                # An order might have multiple return requests (e.g. if one was rejected), just pick the latest or first
                active_return = order.returns[-1] if order.returns else None
                if active_return:
                    return_status = active_return.status.value if hasattr(active_return.status, 'value') else active_return.status
                    return_reason = active_return.reason
                    refund_amount = active_return.refund_amount

            # Resolve customer info
            cust_name = order.customer_name
            cust_phone = order.customer_phone
            
            # For online orders (non showroom), fall back to user full name if available
            if not cust_name and order.customer:
                cust_name = order.customer.full_name
                cust_phone = order.customer.phone if hasattr(order.customer, 'phone') else None
                # Actually if Order.customer_phone is missing, it's missing.

            response.append(DealerOrderResponse(
                id=order.id,
                order_number=order.order_number,
                created_at=order.created_at,
                subtotal=order.subtotal,
                discount_amount=order.discount_amount,
                delivery_charge=order.delivery_charge,
                platform_fee_amount=order.platform_fee_amount,
                coupon_code=order.coupon_code,
                total_amount=order.total_amount,
                status=order.status,
                payment_method=order.payment_method,
                shipping_address=addr_str,
                customer_name=cust_name or "Regular Customer",
                customer_phone=cust_phone,
                notes=order.notes,
                items=dealer_items,
                return_status=return_status,
                return_reason=return_reason,
                refund_amount=refund_amount,
                cancellation_reason=order.cancellation_reason,
                customer_lat=customer_lat,
                customer_long=customer_long
            ))
    return {
        "items": response,
        "total": total_count,
        "page": page,
        "limit": limit
    }

@router.get("/auction-bids")
async def get_dealer_auction_bids(
    page: int = 1,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if current_user.role != UserRole.DEALER:
        raise HTTPException(status_code=403, detail="Only dealers can access this")
        
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer not found")
        
    from auction.models import AuctionBid, AuctionItem
    from models.customer_user import CustomerUser
    from sqlalchemy import select, desc
    
    skip = (page - 1) * limit
    
    q = (
        select(AuctionBid, CustomerUser.full_name)
        .join(AuctionItem, AuctionItem.id == AuctionBid.auction_id)
        .join(CustomerUser, CustomerUser.id == AuctionBid.user_id)
        .where(AuctionItem.dealer_id == dealer.id)
        .order_by(desc(AuctionBid.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    res = await db.execute(q)
    rows = res.all()
    
    bids = []
    for bid, user_name in rows:
        bids.append({
            "id": str(bid.id),
            "auction_id": str(bid.auction_id),
            "user_name": user_name or 'Customer',
            "amount": bid.bid_amount,
            "status": "WINNING" if bid.is_winning else "OUTBID",
            "time": bid.created_at.isoformat()
        })
        
    return bids

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    type: Optional[str] = "new",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hub_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get overview stats for the dealer dashboard"""
    # 1. Verify user is a dealer or hub
    if current_user.role not in ALL_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    provided_hub_id = hub_id
    hub_id = None
    dealer_id = None
    
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    dealer_id = dealer.id

    if provided_hub_id:
        hub_id = provided_hub_id
    elif current_user.role in [UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS]:
        hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
        hub = hub_result.scalar_one_or_none()
        if not hub:
            if current_user.hub_id:
                hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.id == current_user.hub_id))
                hub = hub_result.scalar_one_or_none()
            if not hub:
                raise HTTPException(status_code=404, detail="Hub profile not found")
        # hub_id = hub.id  <-- We intentionally don't force this now


    from datetime import datetime
    from sqlalchemy import func, text, case, or_
    
    # Base conditions
    filters = []
    if start_date:
        try:
            sd = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            filters.append(Order.created_at >= sd)
        except ValueError: pass
    if end_date:
        try:
            ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            filters.append(Order.created_at <= ed)
        except ValueError: pass

    status_counts = {}
    
    if type in ["return", "exchange"]:
        from models.order_return import OrderReturn
        q = (
            select(OrderReturn.status, func.count(OrderReturn.id.distinct()))
            .join(OrderItem, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
            .join(Product, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderReturn.order_id)
            .where(Product.dealer_id == dealer_id)
            .where(OrderReturn.is_exchange == (type == "exchange"))
            .where(~Order.order_number.ilike("SR-%"))
        )
        if hub_id:
            q = q.where(OrderItem.hub_id == hub_id)
        for f in filters:
            q = q.where(f)
        q = q.group_by(OrderReturn.status)
        
        item_stats_res = await db.execute(q)
        for row in item_stats_res.all():
            if row[0]: 
                val = row[0].value if hasattr(row[0], 'value') else row[0]
                status_counts[str(val).lower()] = row[1]
    else:
        q = (
            select(
                case(
                    (Order.status == OrderStatus.CANCELLED, OrderStatus.CANCELLED),
                    else_=OrderItem.status
                ).label('effective_status'),
                func.count(OrderItem.id)
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, OrderItem.product_id == Product.id)
            .where(Product.dealer_id == dealer_id)
            .where(~Order.order_number.ilike("SR-%"))
        )
        if type == "auction":
            q = q.where(Order.is_auction_order == True)
        if hub_id:
            q = q.where(OrderItem.hub_id == hub_id)
        for f in filters:
            q = q.where(f)
        q = q.group_by(text('effective_status'))
        
        item_stats_res = await db.execute(q)
        for row in item_stats_res.all():
            if row[0]:
                val = row[0].value if hasattr(row[0], 'value') else row[0]
                status_counts[str(val).lower()] = row[1]

    # Calculate extra overall stats
    total_sales = 0
    total_products = 0
    rating = 4.8

    # Total Products
    prod_q = select(func.count(Product.id)).where(Product.dealer_id == dealer_id)
    prod_res = await db.execute(prod_q)
    total_products = prod_res.scalar() or 0

    # Total Sales (Delivered Items)
    sales_q = (
        select(func.sum(OrderItem.price * OrderItem.quantity))
        .join(Product, OrderItem.product_id == Product.id)
        .where(Product.dealer_id == dealer_id)
        .where(OrderItem.status == OrderStatus.DELIVERED.value)
    )
    sales_res = await db.execute(sales_q)
    total_sales = sales_res.scalar() or 0

    # Active Orders
    active_statuses = ["pending", "order_placed", "confirmed", "packaging", "packed", "shipped", "dispatched", "out_for_delivery", "processing"]
    active_orders = sum(status_counts.get(s, 0) for s in active_statuses)

    return {
        "statusCounts": status_counts,
        "totalSales": float(total_sales),
        "activeOrders": active_orders,
        "totalProducts": total_products,
        "rating": rating
    }


@router.get("/orders/{order_id}", response_model=DealerOrderResponse)
async def get_dealer_order_detail(
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get full details for a specific order (DEALER/HUB/LOGISTICS)"""
    # Resolve dealer/logistics
    dealer = await get_current_dealer(current_user, db)
    dealer_id = dealer.id if dealer else None
    
    logistics_partner_id = None
    if current_user.role in [UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER]:
        logistics_partner_id = current_user.logistics_partner_id
        if not logistics_partner_id:
             raise HTTPException(status_code=400, detail="User not associated with a logistics partner")
             
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

    # Determine if user is hub-restricted
    hub_id = None
    if current_user.role in [UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS]:
        hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
        hub = hub_res.scalar_one_or_none()
        if not hub and current_user.hub_id:
             hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.id == current_user.hub_id))
             hub = hub_res.scalar_one_or_none()
        if hub:
            hub_id = hub.id

    # Fetch order with details
    from sqlalchemy import and_
    query = (
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.items).selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
            selectinload(Order.items).selectinload(OrderItem.hub),
            selectinload(Order.shipping_address),
            selectinload(Order.returns).selectinload(OrderReturn.exchange_variant),
            selectinload(Order.customer),
            selectinload(Order.payment)
        )
        .distinct()
    )

    if hub_id:
        query = query.where(OrderItem.hub_id == hub_id)
    if logistics_partner_id:
        # Logistics partners see items assigned to them
        query = query.where(OrderItem.logistics_partner_id == logistics_partner_id)
    if dealer_id:
        # Dealers see their own products
        query = query.where(Product.dealer_id == dealer_id)
    elif not is_admin and not hub_id and not logistics_partner_id:
        # Others might need separate logic, but for now 403
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found or access denied")

    # Transform to schema
    dealer_items = []
    dealer_order_total = 0.0
    for item in order.items:
        prod = item.product
        
        # Access check for this specific item
        is_item_dealer = dealer_id and prod and prod.dealer_id == dealer_id
        is_item_logistics = logistics_partner_id and item.logistics_partner_id == logistics_partner_id
        is_item_hub = hub_id and item.hub_id == hub_id
        
        if prod and (is_item_dealer or is_item_logistics or is_item_hub or is_admin):
             # Find return for this specific item if any
             item_return = None
             if hasattr(order, 'returns') and order.returns:
                 item_return = next((r for r in order.returns if r.order_item_id == item.id or r.order_item_id is None), None)

             dealer_items.append(OrderItemDealer(
                 id=item.id,
                 item_order_id=item.item_order_id,
                 product_id=prod.id,
                 product_name=prod.name,
                 quantity=item.quantity,
                 price=item.price,
                 mrp=(item.variant.mrp if hasattr(item, 'variant') and item.variant and item.variant.mrp else None) or prod.mrp or item.price,
                 variant_attributes=item.variant_attributes,
                 product_image=prod.images[0] if prod.images else None,
                 status=OrderStatus.CANCELLED.value if order.status == OrderStatus.CANCELLED else item.status,
                 reject_reason=item.reject_reason,
                 courier_company=item.courier_company,
                 tracking_number=item.tracking_number,
                 tracking_url=item.tracking_url,
                 dispatch_date=item.dispatch_date,
                 estimated_delivery=item.estimated_delivery,
                 delivered_at=item.delivered_at,
                      accepted_at=item.accepted_at,
                      hub_id=item.hub_id,
                      hub_arrived_at=item.hub_arrived_at,
                      tax_amount=item.tax_amount,
                      cgst_rate=item.cgst_rate,
                      sgst_rate=item.sgst_rate,
                      igst_rate=item.igst_rate,
                      hsn_code=item.hsn_code,
                      platform_fee=item.platform_fee,
                       logistics_partner_id=getattr(item, 'logistics_partner_id', None),
                 return_status=item_return.status.value if item_return and hasattr(item_return.status, 'value') else (item_return.status if item_return else None),
                 return_reason=item_return.reason if item_return else None,
                 return_id=item_return.id if item_return else None,
                 return_pickup_date=item_return.pickup_date if item_return else None,
                 payment_status=item.payment_status,
                 rider_id=item.rider_id,
                 rider_name=item.rider.user.full_name if (item.rider and item.rider.user) else None,
                 rider_phone=item.rider.phone_number if item.rider else None,
                 delivery_attempts=getattr(item, 'delivery_attempts', 0),
                 is_exchange=getattr(item_return, 'is_exchange', False) if item_return else False,
                 exchange_variant_id=getattr(item_return, 'exchange_variant_id', None) if item_return else None,
                 exchange_variant=item_return.exchange_variant.attributes if item_return and hasattr(item_return.exchange_variant, 'attributes') else None
             ))
             dealer_order_total += (item.quantity * item.price)

    # Find a showroom name from items
    showroom_name = "Online Order"
    for o_item in order.items:
        if o_item.hub:
            showroom_name = o_item.hub.name
            break

    # Address string
    addr_str = "No address"
    customer_lat = None
    customer_long = None
    if order.shipping_address:
        addr = order.shipping_address
        street = getattr(addr, 'address_line1', getattr(addr, 'street_address', ''))
        city = getattr(addr, 'city', '')
        state = getattr(addr, 'state', '')
        zip_code = getattr(addr, 'pincode', getattr(addr, 'postal_code', ''))
        parts = [p for p in [street, city, state, zip_code] if p]
        if parts:
            addr_str = ", ".join(parts[:3]) + (f" - {zip_code}" if zip_code else "")
        customer_lat = getattr(addr, 'latitude', None)
        customer_long = getattr(addr, 'longitude', None)

    return DealerOrderResponse(
        id=order.id,
        order_number=order.order_number,
        created_at=order.created_at,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        delivery_charge=order.delivery_charge,
        platform_fee_amount=order.platform_fee_amount,
        coupon_code=order.coupon_code,
        total_amount=order.total_amount,
        status=order.status,
        payment_method=order.payment_method,
        shipping_address=addr_str,
        customer_name=order.customer_name or (order.customer.full_name if order.customer else "Direct Customer"),
        customer_phone=order.customer_phone or (order.customer.phone if order.customer else ""),
        showroom_name=showroom_name,
        items=dealer_items,
        customer_lat=customer_lat,
        customer_long=customer_long
    )

@router.put("/orders/{order_id}/status", response_model=DealerOrderResponse)
async def update_dealer_order_status(
    order_id: int,
    status: OrderStatus,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update order status (DEALER only).
    """
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
         raise HTTPException(status_code=404, detail="Dealer profile not found")

    # Verify order contains dealer's products
    # (Simplified check: Does this order exist for this dealer?)
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(Order.id == order_id)
        .where(Product.dealer_id == dealer.id)
        .options(
            selectinload(Order.items), 
            selectinload(Order.shipping_address),
            selectinload(Order.payment)
        )
        .distinct()
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not belonging to you")

    # Update status
    # Note: This updates the MAIN order status. If multi-dealer, this affects all.
    # Accepted limitation for MVP.
    order.status = status
    
    # Update payment status if delivered
    if status == OrderStatus.DELIVERED:
        order.delivered_at = datetime.now(timezone.utc)
        if order.payment:
            order.payment.status = PaymentStatus.SUCCESS
            order.payment.completed_at = datetime.now(timezone.utc)
    
    # Construct response BEFORE commit to avoid MissingGreenlet on expired attributes
    dealer_items = []
    for item in order.items:
         prod_result = await db.execute(select(Product).where(Product.id == item.product_id))
         prod = prod_result.scalar_one_or_none()
         if prod and prod.dealer_id == dealer.id:
             dealer_items.append(OrderItemDealer(
                 id=item.id,
                 item_order_id=item.item_order_id,
                 product_id=prod.id,
                 product_name=prod.name,
                 quantity=item.quantity,
                 price=item.price,
                 variant_attributes=item.variant_attributes,
                 product_image=prod.images[0] if prod.images else None,
                 status=item.status,
                 reject_reason=item.reject_reason,
                 courier_company=item.courier_company,
                 tracking_number=item.tracking_number,
                 tracking_url=item.tracking_url,
                 dispatch_date=item.dispatch_date,
                 estimated_delivery=item.estimated_delivery,
                 delivered_at=item.delivered_at
             ))
             
    addr_str = "No address"
    customer_lat = None
    customer_long = None
    if order.shipping_address:
        addr = order.shipping_address
        street = getattr(addr, 'address_line1', getattr(addr, 'street_address', ''))
        city = getattr(addr, 'city', '')
        state = getattr(addr, 'state', '')
        zip_code = getattr(addr, 'pincode', getattr(addr, 'postal_code', ''))
        parts = [p for p in [street, city, state, zip_code] if p]
        if parts:
            addr_str = ", ".join(parts[:3]) + (f" - {zip_code}" if zip_code else "")
        customer_lat = getattr(addr, 'latitude', None)
        customer_long = getattr(addr, 'longitude', None)

    response_data = DealerOrderResponse(
        id=order.id,
        created_at=order.created_at,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        delivery_charge=order.delivery_charge,
        platform_fee_amount=order.platform_fee_amount,
        coupon_code=order.coupon_code,
        total_amount=order.total_amount,
        status=order.status, # Overall Order Status
        payment_status=order.payment.status.value if order.payment else "pending",
        shipping_address=addr_str,
        items=dealer_items,
        customer_lat=customer_lat,
        customer_long=customer_long
    )

    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_order_status(
            db,
            customer_id=order.customer_id,
            order_number=order.order_number or f"ORD-{order.id}",
            status=status.value,
            data={"order_id": order.id}
        )
    except Exception as e:
        print(f"Error sending order status notification: {e}")

    await db.commit()
    
    return response_data

@router.get("/available-riders", response_model=List[RiderSchema])
async def get_available_riders(
    pincode: Optional[str] = None,
    hub_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List available delivery riders, optionally filtered by pincode (Zone-based)."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in MANAGEMENT_AND_HUB_ROLES:
         raise HTTPException(status_code=403, detail="Not authorized")
    
    dealer = await get_current_dealer(current_user, db)
    dealer_id = dealer.id if dealer else None
    
    from models.hub import DeliveryHub
    hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
    my_hub = hub_result.scalars().first()
    my_hub_id = my_hub.id if my_hub else None

    # Show approved riders OR riders managed by this dealer OR riders managed by this hub
    # (Allowing assignment of own riders even if approval status is pending)
    from sqlalchemy import or_
    query = select(DeliveryRider).where(
        or_(
            DeliveryRider.is_approved == True,
            DeliveryRider.dealer_id == dealer_id if dealer_id else False,
            DeliveryRider.hub_id == my_hub_id if my_hub_id else False
        )
    ).options(selectinload(DeliveryRider.user))
    
    if pincode and pincode.strip():
        from sqlalchemy import or_
        # Allow riders matching the pincode in their comma-separated zones
        # Also handle empty strings or spaces in service_zones
        query = query.where(or_(
            DeliveryRider.service_zones.ilike(f"%{pincode}%"),
            DeliveryRider.service_zones.is_(None),
            DeliveryRider.service_zones == "",
            DeliveryRider.service_zones == " "
        ))

    if hub_id:
        query = query.where(DeliveryRider.hub_id == hub_id)
        
    result = await db.execute(query)
    riders = result.scalars().all()
    
    # Manually populate full_name and phone_number from user/profile if missing
    for r in riders:
        if not r.full_name and r.user:
            r.full_name = r.user.full_name
        if not r.phone_number and r.user:
            r.phone_number = r.user.phone
            
    return riders


@router.get("/my-riders", response_model=List[RiderSchema])
async def get_dealer_riders(
    hub_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all riders assigned/managed by this dealer."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in MANAGEMENT_AND_HUB_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    dealer_id = dealer.id if dealer else None
    
    from models.hub import DeliveryHub
    hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
    my_hub = hub_result.scalars().first()
    my_hub_id = my_hub.id if my_hub else None

    if not dealer_id and not my_hub_id:
        raise HTTPException(status_code=404, detail="Dealer or Hub profile not found")

    from sqlalchemy import or_
    stmt = select(DeliveryRider).where(
        or_(
            DeliveryRider.dealer_id == dealer_id if dealer_id else False,
            DeliveryRider.hub_id == my_hub_id if my_hub_id else False
        )
    )
    
    if hub_id:
        stmt = stmt.where(DeliveryRider.hub_id == hub_id)
    
    stmt = stmt.options(selectinload(DeliveryRider.user))
    result = await db.execute(stmt)
    return result.scalars().all()



@router.get("/logistics-partners", response_model=List[LogisticsPartnerSchema])
async def get_dealer_logistics_partners(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all logistics partners mapped to this dealer."""
    if current_user.role not in MANAGEMENT_AND_HUB_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(LogisticsPartner)
        .join(dealer_logistics_mapping, LogisticsPartner.id == dealer_logistics_mapping.c.logistics_partner_id)
        .where(dealer_logistics_mapping.c.dealer_id == dealer.id)
    )
    return result.scalars().all()


class AssignRiderPayload(BaseModel):
    rider_id: int


@router.post("/order-items/{item_id}/assign-rider")
async def assign_rider_to_order_item(
    item_id: int,
    payload: AssignRiderPayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign an available rider to a specific order item."""
    if current_user.role not in DEALER_ROLES_ALL + HUB_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    # Verify order item belongs to this dealer
    result = await db.execute(
        select(OrderItem)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.id == item_id)
        .where(Product.dealer_id == dealer.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found or not owned by you")

    # Verify rider is approved and available
    rider_result = await db.execute(
        select(DeliveryRider).where(
            DeliveryRider.id == payload.rider_id,
            DeliveryRider.is_approved == True
        )
    )
    rider = rider_result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found or not approved")

    item.rider_id = payload.rider_id
    if item.status in ["pending", "order_placed", "confirmed", "packaging", "packed", "undelivered", "at_hub"]:
        item.status = OrderStatus.SHIPPED.value

    # Also update the parent Order status so customer order list reflects correctly
    order_result = await db.execute(
        select(Order).where(Order.id == item.order_id)
    )
    parent_order = order_result.scalar_one_or_none()
    if parent_order and parent_order.status not in [
        OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED
    ]:
        parent_order.status = OrderStatus.SHIPPED

    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_order_status(
            db,
            customer_id=parent_order.customer_id,
            order_number=parent_order.order_number or f"ORD-{parent_order.id}",
            status="out_for_delivery",
            data={"order_id": parent_order.id, "item_id": item_id, "rider_id": payload.rider_id}
        )
    except Exception as e:
        print(f"Error sending out_for_delivery notification: {e}")

    # Capture values BEFORE commit â€” after commit, SQLAlchemy expires the ORM
    # object and accessing attributes outside an async greenlet raises MissingGreenlet
    new_status = item.status
    rider_id = payload.rider_id

    await db.commit()
    return {"message": f"Rider {rider_id} assigned to item {item_id}", "status": new_status}


@router.delete("/order-items/{item_id}/assign-rider")
async def unassign_rider_from_order_item(
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove rider assignment from a specific order item."""
    if current_user.role not in DEALER_ROLES_ALL + HUB_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(OrderItem)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.id == item_id)
        .where(Product.dealer_id == dealer.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found or not owned by you")

    item.rider_id = None
    if item.status == OrderStatus.OUT_FOR_DELIVERY.value:
        item.status = OrderStatus.PACKED.value
    await db.commit()
    return {"message": f"Rider unassigned from item {item_id}"}


@router.get("/pending-dispatch-items")
async def get_pending_dispatch_items(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order items ready for rider assignment (packed/confirmed, no rider yet)."""
    if current_user.role not in DEALER_ROLES_ALL + HUB_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    from sqlalchemy.orm import selectinload
    from models import Order, Address

    query = (
        select(OrderItem)
        .options(
            selectinload(OrderItem.order).selectinload(Order.shipping_address),
            selectinload(OrderItem.order).selectinload(Order.customer),
            selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
        )
        .join(Product, OrderItem.product_id == Product.id)
        .where(Product.dealer_id == dealer.id)
        .where(OrderItem.status.in_(["confirmed", "packaging", "packed", "dispatched", "out_for_delivery", "undelivered"]))
        .order_by(OrderItem.id.desc())
    )
    
    if current_user.role in [UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_DISPATCHER]:
        # If hub user, filter by their hub_id
        hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
        hub = hub_res.scalar_one_or_none()
        if not hub and current_user.hub_id:
            hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.id == current_user.hub_id))
            hub = hub_res.scalar_one_or_none()
        if not hub:
            raise HTTPException(status_code=404, detail="Hub profile not found for this user")
        query = query.where(OrderItem.hub_id == hub.id)

    result = await db.execute(query)
    items = result.scalars().all()

    response = []
    for item in items:
        order = item.order
        rider = item.rider
        response.append({
            "id": item.id,
            "order_number": order.order_number or f"ORD-{order.id}",
            "product_name": item.product.name,
            "quantity": item.quantity,
            "price": item.price,
            "status": item.status,
            "shipping_address": (
                f"{order.shipping_address.address_line1}, {order.shipping_address.city}"
                if order.shipping_address else "N/A"
            ),
            "customer_name": order.customer.full_name or order.customer.email,
            "customer_phone": order.customer.phone,
            "rider_id": item.rider_id,
            "rider_name": rider.user.full_name if rider and rider.user else None,
            "rider_phone": rider.phone_number if rider else None,
            "rider_status": rider.current_status if rider else None,
            "delivery_attempts": getattr(item, 'delivery_attempts', 0),
        })

    return response

class OrderItemUpdatePayload(BaseModel):
    status: str
    reject_reason: Optional[str] = None
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    rider_id: Optional[int] = None
    logistics_partner_id: Optional[int] = None
    delivery_type: Optional[str] = None

@router.put("/order-items/{item_id}", response_model=OrderItemDealer)
async def update_dealer_order_item(
    item_id: int,
    payload: OrderItemUpdatePayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update individual order item status and tracking info (DEALER only)
    """
    # 1. Verify user is a dealer or hub
    if current_user.role not in ALL_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Resolve dealer/hub/logistics
    dealer = await get_current_dealer(current_user, db)
    dealer_id = dealer.id if dealer else None

    # Hub filtering
    hub_id = None
    if current_user.role in HUB_ROLES:
        hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
        hub = hub_result.scalar_one_or_none()
        if not hub and current_user.hub_id:
            hub_result = await db.execute(select(DeliveryHub).where(DeliveryHub.id == current_user.hub_id))
            hub = hub_result.scalar_one_or_none()
        if not hub:
            raise HTTPException(status_code=404, detail="Hub profile not found")
        hub_id = hub.id

    # Logistics filtering
    logistics_partner_id = None
    if current_user.role in [UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER]:
        logistics_partner_id = current_user.logistics_partner_id
        if not logistics_partner_id:
             raise HTTPException(status_code=400, detail="User not associated with a logistics partner")

    query = (
        select(OrderItem)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.id == item_id)
        .options(
             __import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(OrderItem.product).selectinload(Product.dealer),
             __import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(OrderItem.order),
             __import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(OrderItem.rider).selectinload(DeliveryRider.user)
        )
    )

    result = await db.execute(query)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")

    # Access control
    is_admin = current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    is_owner = dealer_id and item.product.dealer_id == dealer_id
    is_assigned_hub = hub_id and item.hub_id == hub_id
    is_assigned_logistics = logistics_partner_id and item.logistics_partner_id == logistics_partner_id

    if not (is_admin or is_owner or is_assigned_hub or is_assigned_logistics):
        raise HTTPException(status_code=403, detail="Not authorized to update this item")

    if payload.status.lower() == "confirmed":
        from models.inventory import ProductInventory
        from sqlalchemy import func
        inventory_result = await db.execute(
            select(func.coalesce(func.sum(ProductInventory.stock), 0))
            .where(ProductInventory.product_id == item.product_id)
        )
        current_stock = inventory_result.scalar() or 0
        if current_stock < item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient stock to confirm this order. Required: {item.quantity}, Available: {current_stock}"
            )
        item.accepted_at = datetime.now(timezone.utc)
    elif payload.status.lower() == "packaging":
        item.hub_arrived_at = datetime.now(timezone.utc)

    item.status = payload.status

    if payload.status.lower() == "undelivered":
        item.delivery_attempts = getattr(item, 'delivery_attempts', 0) + 1
        if item.delivery_attempts >= 3:
             item.status = "returned"
             payload.status = "returned"
    elif payload.status.lower() == "delivered":
        item.delivery_attempts = 0
        item.payment_status = "paid"
        if payload.delivered_at:
            item.delivered_at = payload.delivered_at
        elif not item.delivered_at:
            item.delivered_at = datetime.now(timezone.utc)
    
    if payload.reject_reason is not None: item.reject_reason = payload.reject_reason
    if payload.courier_company is not None: item.courier_company = payload.courier_company
    if payload.tracking_number is not None: item.tracking_number = payload.tracking_number
    if payload.tracking_url is not None: item.tracking_url = payload.tracking_url
    if payload.dispatch_date is not None: item.dispatch_date = payload.dispatch_date
    if payload.estimated_delivery is not None: 
        item.estimated_delivery = payload.estimated_delivery
        # Also update parent order's estimated delivery if it's not set
        if item.order and not item.order.estimated_delivery:
            item.order.estimated_delivery = payload.estimated_delivery
            item.order.tracking_number = payload.tracking_number # Fallback tracking

    if payload.rider_id is not None:
        item.rider_id = payload.rider_id
        if item.status.lower() in ["pending", "order_placed", "confirmed", "packaging", "packed", "at_hub"]:
             item.status = OrderStatus.SHIPPED.value
             
    if payload.logistics_partner_id is not None:
        item.logistics_partner_id = payload.logistics_partner_id
        # Automatically move to shipped if logistics assigned
        if item.status.lower() in ["pending", "order_placed", "confirmed", "packaging", "packed", "shipped", "at_hub", "dispatched"]:
            item.status = OrderStatus.SHIPPED.value
            
    if payload.delivery_type is not None:
        item.delivery_type = payload.delivery_type

    # â”€â”€ Update Order Status & Process Refunds/Stock â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    from sqlalchemy.orm import selectinload
    order_res = await db.execute(
        select(Order).where(Order.id == item.order_id).options(
            selectinload(Order.payment),
            selectinload(Order.items)
        )
    )
    parent_order = order_res.scalar_one_or_none()
    
    from core.order_status_logic import calculate_and_update_order_status

    if parent_order:
        # 1. Handle Rejection/Cancellation (Stock & Refund)
        if payload.status in ["rejected", "cancelled", "returned"]:
            # Restore stock if item becomes invalid
            if item.product:
                item.product.stock += item.quantity
            
            # Process refund if payment was successful
            if parent_order.payment and parent_order.payment.status == PaymentStatus.SUCCESS:
                refund_amt = float(item.price * item.quantity)
                if not parent_order.payment.refund_amount:
                    parent_order.payment.refund_amount = 0.0
                parent_order.payment.refund_amount += refund_amt
                
                # Mark as fully refunded if appropriate
                if parent_order.payment.refund_amount >= parent_order.payment.amount:
                    parent_order.payment.status = PaymentStatus.REFUNDED
                
                reason = payload.reject_reason or payload.status
                name = item.product.name if item.product else f"Product {item.product_id}"
                if parent_order.payment.refund_reason:
                    parent_order.payment.refund_reason += f" | {name}: {reason}"
                else:
                    parent_order.payment.refund_reason = f"{name}: {reason}"
                parent_order.payment.refunded_at = datetime.now(timezone.utc)

        # Use the shared logic to update the Overall Order Status based on all items
        await calculate_and_update_order_status(db, parent_order.id)

        # TRIGGER NOTIFICATION
        try:
            from services.notification import AppNotificationService
            await AppNotificationService.notify_order_status(
                db,
                customer_id=parent_order.customer_id,
                order_number=parent_order.order_number or f"ORD-{parent_order.id}",
                status=payload.status,
                data={"order_id": parent_order.id, "item_id": item.id}
            )
        except Exception as e:
            print(f"Error sending notification: {e}")

    await db.commit()
    await db.refresh(item)
    
    prod = item.product
    
    # Fetch return info if any
    from models.order_return import OrderReturn
    ret_res = await db.execute(
        select(OrderReturn).where(
            (OrderReturn.order_item_id == item.id) | 
            ((OrderReturn.order_item_id.is_(None)) & (OrderReturn.order_id == item.order_id))
        ).order_by(OrderReturn.requested_at.desc())
    )
    item_ret = ret_res.scalar_one_or_none()

    rider_name = None
    rider_phone = None
    if item.rider_id:
        rider_res = await db.execute(
            select(DeliveryRider)
            .options(__import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(DeliveryRider.user))
            .where(DeliveryRider.id == item.rider_id)
        )
        new_rider = rider_res.scalar_one_or_none()
        if new_rider:
            rider_name = new_rider.user.full_name if new_rider.user else None
            rider_phone = new_rider.phone_number

    return OrderItemDealer(
        id=item.id,
        item_order_id=item.item_order_id,
        product_id=prod.id,
        product_name=prod.name,
        quantity=item.quantity,
        price=item.price,
        variant_attributes=item.variant_attributes,
        product_image=prod.images[0] if prod.images else None,
        status=item.status,
        reject_reason=item.reject_reason,
        courier_company=item.courier_company,
        tracking_number=item.tracking_number,
        tracking_url=item.tracking_url,
        dispatch_date=item.dispatch_date,
        estimated_delivery=item.estimated_delivery,
        delivered_at=item.delivered_at,
                      accepted_at=item.accepted_at,
                      hub_id=item.hub_id,
                      hub_arrived_at=item.hub_arrived_at,
                      tax_amount=item.tax_amount,
                      cgst_rate=item.cgst_rate,
                      sgst_rate=item.sgst_rate,
                      igst_rate=item.igst_rate,
                      hsn_code=item.hsn_code,
                      platform_fee=item.platform_fee,
        return_status=item_ret.status.value if item_ret and hasattr(item_ret.status, 'value') else (item_ret.status if item_ret else None),
        return_reason=item_ret.reason if item_ret else None,
        return_id=item_ret.id if item_ret else None,
        return_pickup_date=item_ret.pickup_date if item_ret else None,
        payment_status=item.payment_status,
        rider_id=item.rider_id,
        rider_name=rider_name,
        rider_phone=rider_phone,
        delivery_attempts=getattr(item, 'delivery_attempts', 0),
    )

class ReturnStatusUpdatePayload(BaseModel):
    status: str
    return_id: Optional[int] = None
    order_item_id: Optional[int] = None
    rider_id: Optional[int] = None
    pickup_date: Optional[datetime] = None
    logistics_partner_id: Optional[int] = None

@router.put("/orders/{order_id}/return-status")
async def update_dealer_return_status(
    order_id: int,
    payload: ReturnStatusUpdatePayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update the return status of an order that contains the dealer's products
    """
    if current_user.role not in DEALER_ROLES_ALL + HUB_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
         raise HTTPException(status_code=403, detail="Not authorized")
         
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
         raise HTTPException(status_code=404, detail="Dealer profile not found")

    from models.order_return import OrderReturn, ReturnStatus
    
    # First, check if the order has products from this dealer (simplified permission check)
    order_check = await db.execute(
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(Order.id == order_id)
        .where(Product.dealer_id == dealer.id)
    )
    if not order_check.first():
         raise HTTPException(status_code=403, detail="No authorized products in this order")
         
    # Now get the active return record
    query = select(OrderReturn).where(OrderReturn.order_id == order_id)
    
    if payload.return_id:
        query = query.where(OrderReturn.id == payload.return_id)
    elif payload.order_item_id:
        query = query.where(
            (OrderReturn.order_item_id == payload.order_item_id) | 
            (OrderReturn.order_item_id.is_(None))
        )
    
    # If ambiguous, take the latest
    query = query.order_by(OrderReturn.requested_at.desc())
    
    return_check = await db.execute(query)
    order_return = return_check.scalar_one_or_none()
    
    if not order_return:
         detail = "No matching return request found"
         if payload.return_id: detail += f" for ID {payload.return_id}"
         elif payload.order_item_id: detail += f" for item {payload.order_item_id}"
         raise HTTPException(status_code=404, detail=detail)
         
    # Update Status
    try:
        from sqlalchemy.orm import selectinload
        # Refresh to include order_item
        res = await db.execute(
            select(OrderReturn).where(OrderReturn.id == order_return.id)
            .options(selectinload(OrderReturn.order_item))
        )
        order_return = res.scalar_one()

        new_status = ReturnStatus(payload.status.upper())
        # PROTECTION: Dealers cannot set REFUNDED status manually
        if new_status == ReturnStatus.REFUNDED:
            raise HTTPException(status_code=403, detail="Refund status can only be set by Platform Admin via UTR recording")

        # GATED FLOW: Returns must be APPROVED before processing further
        if new_status not in (ReturnStatus.APPROVED, ReturnStatus.REJECTED) and order_return.status == ReturnStatus.REQUESTED:
             raise HTTPException(status_code=400, detail="Return must be approved by admin or authorized staff before further processing")

        # GATED FLOW: Only Admin can approve online payment returns
        if new_status == ReturnStatus.APPROVED and (order_return.status == ReturnStatus.REQUESTED):
            from core.permissions import is_online_payment_method
            await db.refresh(order_return, attribute_names=['order'])
            if order_return.order and order_return.order.payment_method:
                if is_online_payment_method(order_return.order.payment_method):
                    # This is a Dealer/Showroom staff trying to approve an Online Return
                    raise HTTPException(status_code=403, detail="Online order returns must be approved by Platform Admin")

        order_return.status = new_status
        if payload.rider_id is not None:
            order_return.rider_id = payload.rider_id
        if payload.pickup_date is not None:
            order_return.pickup_date = payload.pickup_date
            
        if payload.logistics_partner_id is not None and order_return.order_item:
            order_return.order_item.logistics_partner_id = payload.logistics_partner_id
            order_return.logistics_partner_id = payload.logistics_partner_id

        if new_status == ReturnStatus.APPROVED:
            order_return.approved_at = datetime.now(timezone.utc)
            order_return.approved_by = current_user.id
            if order_return.order_item:
                order_return.order_item.status = "returning"
        elif new_status == ReturnStatus.REJECTED:
            if order_return.order_item:
                order_return.order_item.status = "delivered" # Restore
        elif new_status == ReturnStatus.COMPLETED:
            order_return.completed_at = datetime.now(timezone.utc)
            
            # Initiate Refund Logic for Dealer's Products
            from sqlalchemy.orm import selectinload
            from models.payment import PaymentStatus
            full_order_res = await db.execute(
                select(Order).where(Order.id == order_id)
                .options(selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.dealer), selectinload(Order.payment))
            )
            full_order = full_order_res.scalar_one_or_none()
            
            if full_order:
                refund_total = 0.0
                for item in full_order.items:
                    # If this return is for a SPECIFIC item, skip others
                    if order_return.order_item_id and item.id != order_return.order_item_id:
                        continue
                        
                    if item.product and item.product.dealer_id == dealer.id:
                        # Restore stock
                        item.product.stock += item.quantity
                        refund_total += (item.price * item.quantity)
                        # Mark item as returned or returning
                        item.status = "returned" if new_status == ReturnStatus.COMPLETED else "returning"
                
                # Update return record
                if order_return.refund_amount is None:
                    order_return.refund_amount = 0.0
                order_return.refund_amount += refund_total
                
                # Mark whole order as returned if all items are returned
                all_returned = all(it.status == "returned" for it in full_order.items)
                if all_returned:
                    full_order.status = OrderStatus.RETURNED
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid return status")

    await db.commit()
    return {"message": f"Return status updated to {new_status.value}"}

@router.get("/riders", response_model=List[RiderSchema])
async def get_dealer_riders(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all riders available to the dealer. Either global or assigned to the dealer."""
    if current_user.role not in DEALER_ROLES_ALL + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
        
    # Get riders assigned to this dealer OR global riders (managed_by="admin")
    query = select(DeliveryRider).where(
        (DeliveryRider.dealer_id == dealer.id) | (DeliveryRider.managed_by == "admin")
    ).where(DeliveryRider.is_approved == True)
    
    result = await db.execute(query)
    riders = result.scalars().all()
    return riders

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Dealer: Refunds Management
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/refunds", response_model=List[dict])
async def get_dealer_refunds(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all returns that require or have processed refunds for the dealer's products
    """
    if current_user.role not in DEALER_ROLES_ALL + HUB_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
         
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
        
    from sqlalchemy.orm import selectinload

    query = (
        select(OrderReturn)
        .join(OrderItem, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        .join(Product, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderReturn.order_id)
        .where(Product.dealer_id == dealer.id)
        .where(OrderReturn.status.in_([ReturnStatus.PICKED_UP, ReturnStatus.COMPLETED]))
        .options(
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(OrderReturn.order_item).selectinload(OrderItem.order),
            selectinload(OrderReturn.user),
            selectinload(OrderReturn.exchange_variant)
        )
    )

    if start_date:
        query = query.where(OrderReturn.requested_at >= start_date)
    if end_date:
        query = query.where(OrderReturn.requested_at <= end_date)

    query = query.order_by(OrderReturn.requested_at.desc())
    
    returns_res = await db.execute(query.distinct())
    returns = returns_res.scalars().all()
    
    result = []
    for r in returns:
        product_name = r.order_item.product.name if r.order_item and r.order_item.product else "Unknown Product"
        product_image = r.order_item.product.images[0] if r.order_item and r.order_item.product and r.order_item.product.images else None
        qty = r.order_item.quantity if r.order_item else 1
        price = r.order_item.price if r.order_item else 0.0
        
        # Verify it really belongs to this dealer for full order returns
        if r.order_item_id is None:
            # Need to find matching items
            order_items_res = await db.execute(
                select(OrderItem)
                .join(Product, Product.id == OrderItem.product_id)
                .where(OrderItem.order_id == r.order_id)
                .where(Product.dealer_id == dealer.id)
            )
            dealer_items = order_items_res.scalars().all()
            if not dealer_items:
                continue
            product_name = "Multiple Items"
            qty = sum(item.quantity for item in dealer_items)
            price = sum(item.price * item.quantity for item in dealer_items)

        result.append({
            "return_id": r.id,
            "order_id": r.order_id,
            "order_item_id": r.order_item_id,
            "item_order_id": r.order_item.item_order_id if r.order_item else f"ORD-{r.order_id}-MULTIPLE",
            "product_name": product_name,
            "product_image": product_image,
            "quantity": qty,
            "price": price,
            "total_refund": r.refund_amount or (price * qty),
            "reason": r.reason,
            "admin_notes": r.admin_notes,
            "return_status": getattr(r.status, "value", str(r.status)),
            "refund_initiated": r.refund_initiated,
            "requested_at": r.requested_at,
            "pickup_date": r.pickup_date,
            "customer_name": r.user.full_name if r.user else "Customer",
            "bank_details": "Customer Wallet/Bank",
            "is_exchange": r.is_exchange,
            "exchange_variant_id": r.exchange_variant_id,
            "exchange_variant": {
                "size": r.exchange_variant.size if hasattr(r.exchange_variant, 'size') else None,
                "color": r.exchange_variant.color if hasattr(r.exchange_variant, 'color') else None
            } if r.exchange_variant else None
        })
        
    return result

class RefundUpdatePayload(BaseModel):
    refund_amount: Optional[float] = None

@router.patch("/refunds/{return_id}/process")
async def process_dealer_refund(
    return_id: int,
    payload: RefundUpdatePayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a return as refunded and trigger any order payment logic
    """
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
        
    from sqlalchemy.orm import selectinload
    try:
        # 1. Fetch Return with thorough loading and dealer ownership verification
        query = (
            select(OrderReturn)
            .join(OrderItem, OrderReturn.order_item_id == OrderItem.id)
            .join(Product, OrderItem.product_id == Product.id)
            .where(OrderReturn.id == return_id, Product.dealer_id == dealer.id)
            .options(
                selectinload(OrderReturn.order).selectinload(Order.payment)
            )
        )
        
        return_res = await db.execute(query)
        r = return_res.scalar_one_or_none()
        
        if not r:
            raise HTTPException(status_code=404, detail="Refund request not found or not assigned to your store.")
            
        if r.status not in [ReturnStatus.PICKED_UP, ReturnStatus.COMPLETED]:
            raise HTTPException(status_code=400, detail="Item must be picked up or completed to process refund explicitly.")
            
        # 2. Update Statuses
        r.refund_initiated = True
        if payload.refund_amount is not None:
            r.refund_amount = payload.refund_amount
        elif r.refund_amount is None and r.order_item:
            # Fallback to item price if not set
            r.refund_amount = r.order_item.price * r.order_item.quantity
            
        # 3. Update Parent Payment Tracking
        if r.order and r.order.payment:
            pay = r.order.payment
            if pay.refund_amount is None:
                pay.refund_amount = 0.0
            
            refund_increment = r.refund_amount or 0.0
            pay.refund_amount += refund_increment
            
            # Determine overall payment status
            total_pay_amount = pay.amount or 0.0
            if total_pay_amount > 0 and pay.refund_amount >= total_pay_amount:
                pay.status = PaymentStatus.REFUNDED
            else:
                pay.status = PaymentStatus.PARTIALLY_REFUNDED
                
            pay.refunded_at = datetime.now(timezone.utc)
            
        await db.commit()
        return {"message": "Refund processed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        print(f"ERROR processing refund: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Dealer: Delivery Settings
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class DeliverySettingsPayload(BaseModel):
    delivery_charge: float = 0.0        # flat fee per order from this dealer
    free_delivery_above: float = 0.0    # 0 = always free; >0 = waived when cart >= this

@router.get("/me/delivery-settings")
async def get_delivery_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dealer: Get their own delivery charge settings"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    return {
        "delivery_charge": dealer.delivery_charge or 0.0,
        "free_delivery_above": dealer.free_delivery_above or 0.0,
    }

@router.put("/me/delivery-settings")
async def update_delivery_settings(
    payload: DeliverySettingsPayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Dealer: Update their delivery charge settings"""
    if payload.delivery_charge < 0 or payload.free_delivery_above < 0:
        raise HTTPException(status_code=400, detail="Charges cannot be negative")
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    dealer.delivery_charge = payload.delivery_charge
    dealer.free_delivery_above = payload.free_delivery_above
    await db.commit()
    return {
        "delivery_charge": dealer.delivery_charge,
        "free_delivery_above": dealer.free_delivery_above,
        "message": "Delivery settings updated successfully"
    }

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Customer: Preview delivery charges (called from checkout)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/delivery-preview")
async def delivery_preview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Customer: Real-time delivery charge breakdown for items currently in cart.
    Returns per-dealer fees + total, so checkout can display them before placing order.
    """
    from models.cart import CartItem as CartItemModel
    from models.product import Product as ProductModel

    # Fetch cart items with their products
    res = await db.execute(
        select(CartItemModel)
        .where(CartItemModel.customer_id == current_user.id)
        .options(__import__('sqlalchemy.orm', fromlist=['selectinload']).selectinload(CartItemModel.product))
    )
    cart_items = res.scalars().all()

    # Group by dealer
    dealer_subtotals: dict[int, float] = {}
    for ci in cart_items:
        if ci.product and ci.product.dealer_id:
            d_id = ci.product.dealer_id
            price = float(ci.product.selling_price or ci.product.mrp or ci.product.dealer_price)
            dealer_subtotals[d_id] = dealer_subtotals.get(d_id, 0.0) + price * ci.quantity

    if not dealer_subtotals:
        return {"dealers": [], "total_delivery_charge": 0.0}

    # Fetch dealer delivery settings
    dealers_res = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id.in_(list(dealer_subtotals.keys())))
    )
    dealers = dealers_res.scalars().all()

    breakdown = []
    total_delivery = 0.0
    for d in dealers:
        subtotal = dealer_subtotals.get(d.id, 0.0)
        fee = float(d.delivery_charge or 0.0)
        threshold = float(d.free_delivery_above or 0.0)
        is_free = fee == 0.0 or (threshold > 0 and subtotal >= threshold)
        charge = 0.0 if is_free else fee
        total_delivery += charge
        # Estimate delivery
        from datetime import datetime, timedelta
        
        # Find maximum delivery days for this dealer's items in the cart
        dealer_items = [ci for ci in cart_items if ci.product and ci.product.dealer_id == d.id]
        max_days = d.estimated_delivery_days or 7
        for ci in dealer_items:
            if ci.product.estimated_delivery_days and ci.product.estimated_delivery_days > max_days:
                max_days = ci.product.estimated_delivery_days
        
        est_date = datetime.now() + timedelta(days=max_days)
        formatted_date = est_date.strftime("%d %b %Y")

        breakdown.append({
            "dealer_id": d.id,
            "dealer_name": d.business_name,
            "items_subtotal": round(subtotal, 2),
            "delivery_charge": round(charge, 2),
            "is_free": is_free,
            "free_above": threshold,
            "remaining_for_free": round(max(0.0, threshold - subtotal), 2) if threshold > 0 and not is_free else 0.0,
            "estimated_delivery_days": max_days,
            "formatted_delivery_date": formatted_date
        })

    return {
        "dealers": breakdown,
        "total_delivery_charge": round(total_delivery, 2)
    }

@router.post("/register", response_model=DealerSchema, status_code=status.HTTP_201_CREATED)
async def register_as_dealer(
    dealer_data: DealerCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Register current user as a dealer (requires authentication)"""
    
    # Check if user is already a dealer
    result = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.user_id == current_user.id))
    existing_dealer = result.scalar_one_or_none()
    
    if existing_dealer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already registered as a dealer"
        )
    
    # Create dealer profile
    dealer = Dealer(
        user_id=current_user.id,
        business_name=dealer_data.business_name,
        business_address=dealer_data.business_address,
        gst_number=dealer_data.gst_number,
        is_approved=False  # Requires admin approval
    )
    
    db.add(dealer)
    
    # Update user role to dealer
    current_user.role = UserRole.DEALER
    
    await db.commit()
    await db.refresh(dealer)
    
    return dealer

@router.get("", response_model=list[DealerSchema])
async def list_dealers(
    skip: int = 0,
    limit: int = 20,
    approved_only: bool = False,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all dealers (admin only)"""
    query = select(Dealer).where(Dealer.is_deleted == False).offset(skip).limit(limit)
    
    if approved_only:
        query = query.where(Dealer.is_approved == True)
    
    result = await db.execute(query)
    dealers = result.scalars().all()
    
    return dealers

@router.get("/me/profile", response_model=DealerSchema)
async def get_my_dealer_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's dealer profile"""
    dealer = await get_current_dealer(current_user, db)
    
    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not registered as a dealer"
        )
    
    return dealer
    

@router.put("/me/complete-profile", response_model=DealerSchema)
async def complete_dealer_profile(
    profile_data: DealerProfileComplete,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Save completed dealer profile fields"""
    dealer = await get_current_dealer(current_user, db)
    
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
        
    data_dict = profile_data.model_dump(exclude_unset=True)
    
    # Handle user name update if provided
    if "owner_name" in data_dict:
        owner_name = data_dict.pop("owner_name")
        if owner_name:
            current_user.full_name = owner_name
            db.add(current_user)
            
    # Apply all fields from DealerProfileComplete
    for key, value in data_dict.items():
        if hasattr(dealer, key):
            setattr(dealer, key, value)
        
    # Mark profile as completed! 
    # Access status remains whatever it was (usually pending admin approval)
    dealer.profile_status = "pending"
    dealer.access_status = "pending"
    
    await db.commit()
    await db.refresh(dealer)
    return dealer


# ======================================================================
# HUB MANAGEMENT ENDPOINTS
# ======================================================================


class HubCreate(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None # Legacy/Manual string
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    notes: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    hub_type: Optional[str] = None
    capacity: Optional[str] = None
    operating_hours: Optional[str] = None
    emergency_phone: Optional[str] = None
    is_showroom: bool = False

class HubUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    hub_type: Optional[str] = None
    capacity: Optional[str] = None
    operating_hours: Optional[str] = None
    emergency_phone: Optional[str] = None
    is_showroom: Optional[bool] = None

class HubResponse(BaseModel):
    id: int
    dealer_id: UUID
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    state_id: Optional[int] = None
    country_id: Optional[int] = None
    pincode: Optional[str] = None
    lat_long: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    notes: Optional[str] = None
    hub_type: Optional[str] = None
    capacity: Optional[str] = None
    operating_hours: Optional[str] = None
    emergency_phone: Optional[str] = None
    is_showroom: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    stock_count: Optional[int] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    item_count: int = 0
    user_id: Optional[int] = None
    email: Optional[str] = None
    auction_reserved: Optional[int] = 0

    class Config:
        from_attributes = True

class AssignToHubPayload(BaseModel):
    hub_id: int
    order_item_ids: List[int]


@router.get("/me/hub-profile", response_model=HubResponse)
async def get_my_hub_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get hub profile for the currently logged-in hub user"""
    if current_user.role not in [UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS]:
        raise HTTPException(status_code=403, detail="Not authorized. Only hub users can access this.")
        
    result = await db.execute(
        select(DeliveryHub)
        .where(DeliveryHub.user_id == current_user.id)
        .options(selectinload(DeliveryHub.user))
    )
    hub = result.scalar_one_or_none()
    
    if not hub and current_user.hub_id:
        result = await db.execute(
            select(DeliveryHub)
            .where(DeliveryHub.id == current_user.hub_id)
            .options(selectinload(DeliveryHub.user))
        )
        hub = result.scalar_one_or_none()

    if not hub:
        raise HTTPException(status_code=404, detail="Hub profile not found for this user")
        
    from sqlalchemy import func as sqlfunc
    cnt_res = await db.execute(
        select(sqlfunc.count(OrderItem.id))
        .where(OrderItem.hub_id == hub.id)
        .where(OrderItem.status.notin_(["delivered", "rejected", "cancelled", "returned"]))
    )
    item_count = cnt_res.scalar() or 0
    
    return {
        "id": hub.id,
        "dealer_id": hub.dealer_id,
        "name": hub.name,
        "address": hub.address,
        "city": hub.city,
        "state": hub.state,
        "state_id": hub.state_id,
        "country_id": hub.country_id,
        "pincode": hub.pincode,
        "lat_long": hub.lat_long,
        "contact_person": hub.contact_person,
        "phone": hub.phone,
        "is_active": hub.is_active,
        "notes": hub.notes,
        "hub_type": hub.hub_type,
        "capacity": hub.capacity,
        "operating_hours": hub.operating_hours,
        "emergency_phone": hub.emergency_phone,
        "created_at": hub.created_at,
        "updated_at": hub.updated_at,
        "created_by": hub.created_by,
        "updated_by": hub.updated_by,
        "item_count": item_count,
        "user_id": hub.user_id,
        "email": current_user.email
    }



@router.get("/hubs", response_model=List[HubResponse])
async def get_dealer_hubs(
    active_only: bool = True,
    product_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Verify user is a dealer or hub
    if current_user.role not in ALL_MANAGEMENT_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    if current_user.role in HUB_ROLES:
        # If a hub user, they can only see their own hub
        query = select(DeliveryHub).options(__import__('sqlalchemy.orm').orm.selectinload(DeliveryHub.user))
        
        conditions = [DeliveryHub.user_id == current_user.id]
        if current_user.hub_id:
            conditions.append(DeliveryHub.id == current_user.hub_id)
            
        from sqlalchemy import or_
        query = query.where(or_(*conditions))
    else:
        query = select(DeliveryHub).where(DeliveryHub.dealer_id == dealer.id).options(__import__('sqlalchemy.orm').orm.selectinload(DeliveryHub.user))
    if active_only:
        query = query.where(DeliveryHub.is_active == True)
    # Removed product_id filter from the main query so we always return ALL hubs, 
    # even if they currently have 0 stock for the given product. 
    # The stock_map will populate stock_count correctly later in the method.
    query = query.order_by(DeliveryHub.created_at.desc())
    result = await db.execute(query)
    hubs = result.scalars().all()

    from sqlalchemy import func as sqlfunc
    count_map = {}
    if hubs:
        try:
            hub_ids = [h.id for h in hubs]
            counts_query = (
                select(OrderItem.hub_id, sqlfunc.count(OrderItem.id))
                .where(OrderItem.hub_id.in_(hub_ids))
                .where(OrderItem.status.notin_(["delivered", "rejected", "cancelled", "returned"]))
                .group_by(OrderItem.hub_id)
            )
            counts_result = await db.execute(counts_query)
            for row in counts_result.all():
                if row[0] is not None:
                    count_map[row[0]] = row[1]
        except Exception as e:
            print(f"Error counting hub items: {e}")

    stock_map = {}
    if hubs and product_id:
        try:
            hub_ids = [h.id for h in hubs]
            
            # Find all variant IDs
            children_query = select(Product.id).where(Product.parent_product_id == product_id)
            children_res = await db.execute(children_query)
            variant_ids = [r for r, in children_res.all()]
            all_ids_to_check = [product_id] + variant_ids
            
            stock_query = select(ProductInventory.hub_id, sqlfunc.sum(ProductInventory.stock)).where(
                ProductInventory.hub_id.in_(hub_ids),
                ProductInventory.product_id.in_(all_ids_to_check)
            ).group_by(ProductInventory.hub_id)
            
            stock_result = await db.execute(stock_query)
            for row in stock_result.all():
                stock_map[row[0]] = row[1] or 0
        except Exception as e:
            print(f"Error fetching stock: {e}")

    auction_map = {}
    if hubs and product_id:
        try:
            from auction.models import AuctionItem, AuctionStatus
            hub_ids = [h.id for h in hubs]
            
            auction_query = select(AuctionItem.hub_id, sqlfunc.sum(AuctionItem.qty)).where(
                AuctionItem.hub_id.in_(hub_ids),
                AuctionItem.product_id == product_id,
                AuctionItem.status.in_([AuctionStatus.ACTIVE, AuctionStatus.PENDING])
            ).group_by(AuctionItem.hub_id)
            
            auction_result = await db.execute(auction_query)
            for row in auction_result.all():
                if row[0] is not None:
                    auction_map[row[0]] = row[1] or 0
        except Exception as e:
            print(f"Error fetching auction stock: {e}")

    response = []
    for hub in hubs:
        # Create a dictionary since we're adding dynamic data (item_count)
        data = {
            "id": hub.id,
            "dealer_id": hub.dealer_id,
            "name": hub.name,
            "address": hub.address,
            "city": hub.city,
            "state": hub.state,
            "state_id": hub.state_id,
            "country_id": hub.country_id,
            "pincode": hub.pincode,
            "lat_long": hub.lat_long,
            "contact_person": hub.contact_person,
            "phone": hub.phone,
            "is_active": hub.is_active,
            "notes": hub.notes,
            "hub_type": hub.hub_type,
            "capacity": hub.capacity,
            "operating_hours": hub.operating_hours,
            "emergency_phone": hub.emergency_phone,
            "created_at": hub.created_at,
            "updated_at": hub.updated_at,
            "created_by": hub.created_by,
            "updated_by": hub.updated_by,
            "item_count": count_map.get(hub.id, 0),
            "user_id": hub.user_id,
            "email": hub.user.email if hub.user else None,
            "is_showroom": hub.is_showroom,
            "stock_count": stock_map.get(hub.id, 0) if product_id else None
        }
        response.append(data)
    return response

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_dealer_audit_logs(
    resource_type: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve audit logs."""
    from models.audit import AuditLog
    d_res = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.user_id == current_user.id))
    dealer = d_res.scalar_one_or_none()
    if not dealer: raise HTTPException(status_code=404, detail="Dealer profile not found")
    query = select(AuditLog).where(AuditLog.dealer_id == dealer.id).options(selectinload(AuditLog.user)).order_by(AuditLog.created_at.desc()).limit(limit)
    if resource_type: query = query.where(AuditLog.resource_type == resource_type)
    result = await db.execute(query)
    logs = result.scalars().all()
    res_data = []
    for log in logs:
        res_data.append({
            "id": log.id, "user_id": log.user_id, "action": log.action,
            "resource_type": log.resource_type, "resource_id": log.resource_id,
            "old_values": log.old_values, "new_values": log.new_values,
            "description": log.description, "ip_address": log.ip_address,
            "created_at": log.created_at, "user_name": log.user.full_name if log.user else "System"
        })
    return res_data


@router.post("/hubs", response_model=HubResponse, status_code=201)
async def create_dealer_hub(
    payload: HubCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new delivery hub for this dealer."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    # Validation
    if payload.state_id and payload.country_id:
        from models.location import State as StateModel
        st_res = await db.execute(select(StateModel).where(StateModel.id == payload.state_id, StateModel.country_id == payload.country_id))
        if not st_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid state for selected country")

    hub = DeliveryHub(
        dealer_id=dealer.id, name=payload.name, address=payload.address,
        city=payload.city, state=payload.state, pincode=payload.pincode,
        lat_long=payload.lat_long, contact_person=payload.contact_person,
        phone=payload.phone, is_active=payload.is_active, notes=payload.notes,
        state_id=payload.state_id, country_id=payload.country_id,
        hub_type=payload.hub_type, capacity=payload.capacity,
        operating_hours=payload.operating_hours, emergency_phone=payload.emergency_phone,
        is_showroom=payload.is_showroom
    )
    
    if payload.email and payload.password:
        from core.security import get_password_hash
        # Check if email already exists
        check_user = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
        if check_user.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already registered")
            
        hub_user = User(
            email=payload.email,
            password_hash=get_password_hash(payload.password),
            full_name=payload.name,
            phone=payload.phone,
            role=UserRole.HUB_MANAGER, # Default to HUB_MANAGER for new hub users
            is_active=True,
            dealer_id=dealer.id
        )
        db.add(hub_user)
        await db.flush()
        hub.user_id = hub_user.id

    hub.created_by = current_user.id
    hub.updated_by = current_user.id
    db.add(hub)
    await db.flush()
    
    from services.audit import log_audit
    await log_audit(
        db, current_user, "CREATE", "hub", hub.id,
        new_values=payload.model_dump(exclude={"password"}),
        description=f"Created hub: {hub.name}",
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    await db.refresh(hub)
    return {
        "id": hub.id,
        "dealer_id": hub.dealer_id,
        "name": hub.name,
        "address": hub.address,
        "city": hub.city,
        "state": hub.state,
        "state_id": hub.state_id,
        "country_id": hub.country_id,
        "pincode": hub.pincode,
        "lat_long": hub.lat_long,
        "contact_person": hub.contact_person,
        "phone": hub.phone,
        "is_active": hub.is_active,
        "notes": hub.notes,
        "hub_type": hub.hub_type,
        "capacity": hub.capacity,
        "operating_hours": hub.operating_hours,
        "emergency_phone": hub.emergency_phone,
        "created_at": hub.created_at,
        "updated_at": hub.updated_at,
        "created_by": hub.created_by,
        "updated_by": hub.updated_by,
        "item_count": 0,
        "user_id": hub.user_id,
        "email": payload.email if hub.user_id else None
    }


@router.put("/hubs/{hub_id}", response_model=HubResponse)
async def update_dealer_hub(
    hub_id: int,
    payload: HubUpdate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a dealer hub."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    hub_result = await db.execute(
        select(DeliveryHub).where(DeliveryHub.id == hub_id, DeliveryHub.dealer_id == dealer.id)
    )
    hub = hub_result.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found")
    # Validation
    validate_country = payload.country_id or hub.country_id
    validate_state = payload.state_id or hub.state_id
    if validate_state and validate_country:
        from models.location import State as StateModel
        st_res = await db.execute(select(StateModel).where(StateModel.id == validate_state, StateModel.country_id == validate_country))
        if not st_res.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Invalid state for selected country")

    old_values = {field: getattr(hub, field) for field in payload.model_dump(exclude_none=True).keys()}
    
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(hub, field, value)
        
    hub.updated_by = current_user.id
        
    from services.audit import log_audit
    await log_audit(
        db, current_user, "UPDATE", "hub", hub.id,
        old_values=old_values,
        new_values=payload.model_dump(exclude_none=True),
        description=f"Updated hub: {hub.name}",
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    await db.refresh(hub)
    from sqlalchemy import func as sqlfunc
    cnt_res = await db.execute(
        select(sqlfunc.count(OrderItem.id))
        .where(OrderItem.hub_id == hub.id)
        .where(OrderItem.status.notin_(["delivered", "rejected", "cancelled", "returned"]))
    )
    item_count = cnt_res.scalar() or 0
    return {
        "id": hub.id,
        "dealer_id": hub.dealer_id,
        "name": hub.name,
        "address": hub.address,
        "city": hub.city,
        "state": hub.state,
        "state_id": hub.state_id,
        "country_id": hub.country_id,
        "pincode": hub.pincode,
        "lat_long": hub.lat_long,
        "contact_person": hub.contact_person,
        "phone": hub.phone,
        "is_active": hub.is_active,
        "notes": hub.notes,
        "hub_type": hub.hub_type,
        "capacity": hub.capacity,
        "operating_hours": hub.operating_hours,
        "emergency_phone": hub.emergency_phone,
        "created_at": hub.created_at,
        "updated_at": hub.updated_at,
        "created_by": hub.created_by,
        "updated_by": hub.updated_by,
        "item_count": item_count
    }


@router.delete("/hubs/{hub_id}", status_code=204)
async def delete_dealer_hub(
    hub_id: int,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete (deactivate) a dealer hub."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    hub_result = await db.execute(
        select(DeliveryHub).where(DeliveryHub.id == hub_id, DeliveryHub.dealer_id == dealer.id)
    )
    hub = hub_result.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found")
    hub.is_active = False
    
    from services.audit import log_audit
    await log_audit(
        db, current_user, "DELETE", "hub", hub.id,
        description=f"Deactivated hub: {hub.name}",
        ip_address=request.client.host if request.client else None
    )
    
    await db.commit()
    return None


@router.get("/hubs/{hub_id}/items")
async def get_hub_items(
    hub_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all active order items currently at a specific hub."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    hub_result = await db.execute(
        select(DeliveryHub).where(DeliveryHub.id == hub_id, DeliveryHub.dealer_id == dealer.id)
    )
    hub = hub_result.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found")
    # Fetch standard items
    items_result = await db.execute(
        select(OrderItem)
        .join(Product, OrderItem.product_id == Product.id)
        .options(
            selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(OrderItem.order).selectinload(Order.customer),
            selectinload(OrderItem.order).selectinload(Order.shipping_address),
            selectinload(OrderItem.rider).selectinload(DeliveryRider.user),
        )
        .where(
            or_(
                OrderItem.hub_id == hub_id,
                and_(OrderItem.hub_id.is_(None), Product.dealer_id == dealer.id)
            )
        )
        .order_by(OrderItem.id.desc())
    )
    items = items_result.scalars().all()
    
    # Fetch returns assigned to this hub or dealer
    returns_result = await db.execute(
        select(OrderReturn)
        .join(OrderItem, OrderReturn.order_item_id == OrderItem.id)
        .join(Product, OrderItem.product_id == Product.id)
        .options(
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product).selectinload(Product.dealer),
            selectinload(OrderReturn.order).selectinload(Order.customer),
            selectinload(OrderReturn.order).selectinload(Order.shipping_address),
            selectinload(OrderReturn.customer),
        )
        .where(
            or_(
                OrderReturn.hub_id == hub_id,
                and_(OrderReturn.hub_id.is_(None), Product.dealer_id == dealer.id)
            )
        )
        .order_by(OrderReturn.id.desc())
    )
    returns = returns_result.scalars().all()

    response = []
    
    # Add standard items
    for item in items:
        order = item.order
        rider = item.rider
        response.append({
            "id": f"item_{item.id}", # Prefix to distinguish from returns
            "raw_id": item.id,
            "type": "order",
            "order_id": order.id if order else None,
            "order_number": (order.order_number or f"ORD-{order.id}") if order else None,
            "product_name": item.product.name if item.product else "Unknown",
            "product_image": item.product.images[0] if item.product and item.product.images else None,
            "quantity": item.quantity,
            "price": item.price,
            "variant_attributes": item.variant_attributes,
            "status": item.status,
            "dispatch_date": item.dispatch_date.isoformat() if item.dispatch_date else None,
            "accepted_at": item.accepted_at.isoformat() if item.accepted_at else None,
            "hub_arrived_at": item.hub_arrived_at.isoformat() if item.hub_arrived_at else None,
            "customer_name": order.customer.full_name if (order and order.customer) else None,
            "customer_phone": order.customer.phone if (order and order.customer) else None,
            "shipping_address": (
                f"{order.shipping_address.address_line1}{', ' + order.shipping_address.address_line2 if order.shipping_address.address_line2 else ''}{', ' + order.shipping_address.landmark if hasattr(order.shipping_address, 'landmark') and order.shipping_address.landmark else ''}, {order.shipping_address.city} - {order.shipping_address.pincode}"
                if (order and order.shipping_address) else None
            ),
            "rider_id": item.rider_id,
            "rider_name": rider.user.full_name if (rider and rider.user) else None,
            "rider_phone": rider.phone_number if rider else None,
            "delivery_attempts": getattr(item, "delivery_attempts", 0),
            "order_notes": order.notes if (order and order.notes) else None,
            "payment_method": order.payment_method if order else None,
            "dealer_name": item.product.dealer.business_name if (item.product and item.product.dealer) else None,
            "is_exchange": False,
        })
        
    # Add returns
    for ret in returns:
        order = ret.order
        item = ret.order_item
        response.append({
            "id": f"return_{ret.id}",
            "raw_id": ret.id,
            "type": "return",
            "order_id": order.id if order else None,
            "order_number": (order.order_number or f"ORD-{order.id}") if order else None,
            "product_name": item.product.name if item and item.product else "Unknown",
            "product_image": item.product.images[0] if item and item.product and item.product.images else None,
            "quantity": item.quantity if item else 1,
            "price": item.price if item else 0,
            "variant_attributes": item.variant_attributes if item else None,
            "status": ret.status.value if hasattr(ret.status, 'value') else ret.status,
            "customer_name": ret.customer.full_name if ret.customer else (order.customer.full_name if (order and order.customer) else None),
            "customer_phone": ret.customer.phone if ret.customer else (order.customer.phone if (order and order.customer) else None),
            "shipping_address": (
                f"{order.shipping_address.address_line1}{', ' + order.shipping_address.address_line2 if order.shipping_address.address_line2 else ''}, {order.shipping_address.city}"
                if (order and order.shipping_address) else None
            ),
            "rider_id": ret.rider_id if hasattr(ret, "rider_id") else None,
            "rider_name": ret.rider.user.full_name if (hasattr(ret, "rider") and ret.rider and ret.rider.user) else None,
            "order_notes": ret.description,
            "payment_method": order.payment_method if order else None,
            "dealer_name": item.product.dealer.business_name if (item and item.product and item.product.dealer) else None,
            "is_exchange": ret.is_exchange or False,
        })
        
    return response


@router.put("/returns/{return_id}/status")
async def update_dealer_return_status(
    return_id: int,
    status: str = Query(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update status of a return order (Hub action)."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    result = await db.execute(
        select(OrderReturn)
        .join(OrderItem, OrderReturn.order_item_id == OrderItem.id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(OrderReturn.id == return_id, Product.dealer_id == dealer.id)
        .options(selectinload(OrderReturn.order_item).selectinload(OrderItem.product).selectinload(Product.dealer), 
                 selectinload(OrderReturn.order).selectinload(Order.customer))
    )
    order_return = result.scalar_one_or_none()
    if not order_return:
        raise HTTPException(status_code=404, detail="Return not found or not belonging to you")

    new_status_str = status.strip().upper()
    try:
        new_status = ReturnStatus(new_status_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid return status: {status}")

    old_status = order_return.status
    order_return.status = new_status
    
    # --- AUTOMATED ASSIGNMENT ON APPROVAL ---
    if new_status == ReturnStatus.APPROVED and old_status == ReturnStatus.REQUESTED:
        order_return.approved_at = datetime.now(timezone.utc)
        order_return.approved_by = current_user.id
        
        # Determine assignment based on original delivery
        if order_return.order_item:
            item = order_return.order_item
            if item.logistics_partner_id:
                # Assign to the same logistics partner
                order_return.logistics_partner_id = item.logistics_partner_id
                print(f"DEBUG: Automated Assignment -> Logistics Partner {item.logistics_partner_id}")
            elif item.rider_id:
                # Assign to the same rider if possible, otherwise dealer handles it
                order_return.rider_id = item.rider_id
                print(f"DEBUG: Automated Assignment -> Rider {item.rider_id}")
            else:
                # Fallback: Dealer will manually assign a rider later or manage it themselves
                print("DEBUG: No automated assignment possible, manual intervention required")

    # --- MULTI-STAGE LOGISTICS LIFECYCLE ---
    if order_return.order_item:
        if new_status == ReturnStatus.COMPLETED:
            order_return.order_item.status = "returned"
            if not order_return.completed_at:
                order_return.completed_at = datetime.now(timezone.utc)
        elif new_status == ReturnStatus.REFUNDED:
            order_return.order_item.status = "returned"
            if not order_return.refund_amount:
                order_return.refund_amount = float(order_return.order_item.price * order_return.order_item.quantity)
            if not order_return.completed_at:
                order_return.completed_at = datetime.now(timezone.utc)
            order_return.refund_initiated = True

    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        order_number = order_return.order.order_number or f"ORD-{order_return.order_id}" if order_return.order else "N/A"
        await AppNotificationService.notify_return_status(
            db, customer_id=order_return.customer_id, order_number=order_number, 
            status=new_status_str, data={"return_id": return_id, "order_id": order_return.order_id}
        )
    except Exception as e:
        print(f"Error sending return status notification: {e}")

    await db.commit()
    return {"message": f"Return status updated to {new_status_str}", "status": new_status_str}


@router.post("/hubs/assign-items")
async def assign_items_to_hub(
    payload: AssignToHubPayload,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign order items to a delivery hub (marks status as 'at_hub')."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    hub_result = await db.execute(
        select(DeliveryHub).where(DeliveryHub.id == payload.hub_id, DeliveryHub.dealer_id == dealer.id)
    )
    hub = hub_result.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=404, detail="Hub not found")
    updated = []
    now = datetime.now(timezone.utc)
    from models.inventory import ProductInventory
    
    for item_id in payload.order_item_ids:
        item_result = await db.execute(
            select(OrderItem)
            .join(Product, OrderItem.product_id == Product.id)
            .where(OrderItem.id == item_id, Product.dealer_id == dealer.id)
        )
        item = item_result.scalar_one_or_none()
        if item:
            # Check hub-specific stock
            inventory_result = await db.execute(
                select(ProductInventory)
                .where(ProductInventory.product_id == item.product_id, ProductInventory.hub_id == payload.hub_id)
            )
            inv = inventory_result.scalar_one_or_none()
            
            if not inv or inv.stock < item.quantity:
                # Fetch product name for error
                product_result = await db.execute(select(Product.name).where(Product.id == item.product_id))
                prod_name = product_result.scalar_one_or_none() or f"Product ID {item.product_id}"
                raise HTTPException(
                    status_code=400, 
                    detail=f"Insufficient stock for '{prod_name}' at hub '{hub.name}'. Requested: {item.quantity}, Available: {inv.stock if inv else 0}"
                )
                
            item.hub_id = payload.hub_id
            item.dispatch_date = now
            if item.status in ["pending", "order_placed", "confirmed", "packaging", "packed", "processing"]:
                item.status = "confirmed"
            updated.append(item_id)
            
    if updated:
        from services.audit import log_audit
        await log_audit(
            db, current_user, "ASSIGN", "hub", payload.hub_id,
            new_values={"order_item_ids": updated},
            description=f"Assigned {len(updated)} items to hub {hub.name}",
            ip_address=request.client.host if request.client else None
        )
            
    hub_name = hub.name
    await db.commit()
    return {"message": f"{len(updated)} item(s) assigned to hub '{hub_name}'", "updated_item_ids": updated}


@router.post("/hubs/unassign-items")
async def unassign_items_from_hub(
    payload: AssignToHubPayload,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove hub assignment from order items."""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    updated = []
    for item_id in payload.order_item_ids:
        item_result = await db.execute(
            select(OrderItem)
            .join(Product, OrderItem.product_id == Product.id)
            .where(OrderItem.id == item_id, Product.dealer_id == dealer.id)
        )
        item = item_result.scalar_one_or_none()
        if item:
            item.hub_id = None
            item.hub_arrived_at = None
            if item.status == "at_hub":
                item.status = "packed"
            updated.append(item_id)
    await db.commit()
    return {"message": f"{len(updated)} item(s) removed from hub", "updated_item_ids": updated}


@router.get("/users", response_model=List[UserManageResponse])
async def list_dealer_users(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all users associated with this dealer (Staff, Hub teams, and Riders)"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized. Only dealers/staff can access this.")
    
    # 1. Get all Hub IDs for this dealer to find Hub Staff
    hubs_query = select(DeliveryHub).where(DeliveryHub.dealer_id == dealer.id)
    hubs_res = await db.execute(hubs_query)
    all_hubs = hubs_res.scalars().all()
    hub_ids = [h.id for h in all_hubs]
    hub_map = {h.user_id: h.id for h in all_hubs if h.user_id} # Map primary managers
    
    # 2. Query Users:
    # - Staff (User.dealer_id == dealer.id)
    # - Hub Team (User.hub_id IN hub_ids)
    # - Showroom Team (User.hub_id IN hub_ids - showrooms are also in delivery_hubs table)
    # - The Dealer Owner themselves (User.id == dealer.user_id)
    from sqlalchemy import or_
    users_query = select(User).where(
        or_(
            User.dealer_id == dealer.id,
            User.hub_id.in_(hub_ids) if hub_ids else False,
            User.id == dealer.user_id
        )
    ).where(User.id != current_user.id) # Don't show self if already showing via dealer.user_id
    
    users_res = await db.execute(users_query)
    related_users = users_res.scalars().all()
    
    # 3. Get Rider Profiles for extra fields
    rider_profiles_query = (
        select(DeliveryRider)
        .where(DeliveryRider.dealer_id == dealer.id)
    )
    rider_profiles_res = await db.execute(rider_profiles_query)
    rider_profiles = rider_profiles_res.scalars().all()
    rider_map = {rp.user_id: rp for rp in rider_profiles}
    
    response = []
    user_ids_processed = set()
    
    for u in related_users:
        if u.id not in user_ids_processed:
            user_ids_processed.add(u.id)
            u_data = UserManageResponse.model_validate(u)
            
            # Hub association priority:
            # 1. User.hub_id (set on hub staff)
            # 2. hub_map (if they are the primary manager of a hub)
            u_data.hub_id = u.hub_id or hub_map.get(u.id)
            
            # Populate rider fields if they have a profile
            if u.id in rider_map:
                rp = rider_map[u.id]
                u_data.license_number = rp.license_number
                u_data.aadhaar_number = rp.aadhaar_number
                u_data.emergency_contact = rp.emergency_contact
                u_data.vehicle_number = rp.vehicle_number
                u_data.vehicle_type = rp.vehicle_type
                u_data.phone = rp.phone_number
                u_data.is_approved = rp.is_approved
                # Use User's address if Rider profile doesn't have it
                u_data.address = rp.address or u.address
                u_data.photo_url = rp.photo_url or u.photo_url
                u_data.vehicle_model = rp.vehicle_model
                u_data.insurance_expiry = rp.insurance_expiry
                u_data.aadhaar_image = rp.aadhaar_image or u.aadhaar_image
                u_data.license_image = rp.license_image
                u_data.bank_name = rp.bank_name
                u_data.account_number = rp.account_number
                u_data.ifsc_code = rp.ifsc_code
                u_data.upi_id = rp.upi_id
                u_data.created_by = rp.created_by
                u_data.updated_by = rp.updated_by
                if not u_data.hub_id:
                    u_data.hub_id = rp.hub_id
            
            response.append(u_data)
            
    return response


# ──────────────────────────────────────────────────────────────────────────────
# Dealer: Manage Serviceable Pincodes
# ──────────────────────────────────────────────────────────────────────────────

from models.location import ServiceablePincode, PincodeMaster

class AddPincodeRequest(BaseModel):
    pincode: str

@router.get("/serviceable-pincodes", tags=["dealers"])
async def get_serviceable_pincodes(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized as dealer")

    res = await db.execute(
        select(ServiceablePincode)
        .where(ServiceablePincode.dealer_id == dealer.id)
        .order_by(ServiceablePincode.created_at.desc())
    )
    pincodes = res.scalars().all()
    
    if not pincodes:
        return []
        
    pincode_strs = [p.pincode for p in pincodes]
    loc_res = await db.execute(
        select(PincodeMaster.pincode, PincodeMaster.office_name, PincodeMaster.state_name)
        .where(PincodeMaster.pincode.in_(pincode_strs))
    )
    locations = loc_res.all()
    
    loc_map = {}
    for loc in locations:
        if loc.pincode not in loc_map:
            office_name = loc.office_name or ""
            for suffix in [" S.O", " B.O", " H.O"]:
                if office_name.endswith(suffix):
                    office_name = office_name[:-len(suffix)]
            loc_map[loc.pincode] = {
                "city": office_name,
                "state": loc.state_name
            }

    result = []
    for p in pincodes:
        loc = loc_map.get(p.pincode, {})
        result.append({
            "id": p.id,
            "pincode": p.pincode,
            "city": loc.get("city", "Unknown"),
            "state": loc.get("state", "Unknown"),
            "is_active": p.is_active,
            "created_at": p.created_at
        })
    return result

@router.post("/serviceable-pincodes", tags=["dealers"])
async def add_serviceable_pincode(
    req: AddPincodeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized as dealer")

    pincode_clean = req.pincode.strip()
    if not pincode_clean:
        raise HTTPException(status_code=400, detail="Pincode cannot be empty")

    # Validate against PincodeMaster
    valid_pincode_res = await db.execute(
        select(PincodeMaster).where(PincodeMaster.pincode == pincode_clean).limit(1)
    )
    if not valid_pincode_res.scalars().first():
        raise HTTPException(status_code=400, detail="Invalid Pincode: Not found in location database")

    res = await db.execute(
        select(ServiceablePincode).where(
            ServiceablePincode.pincode == pincode_clean,
            ServiceablePincode.dealer_id == dealer.id
        )
    )
    existing = res.scalar_one_or_none()
    
    if existing:
        if not existing.is_active:
            existing.is_active = True
            await db.commit()
            return existing
        raise HTTPException(status_code=400, detail="Pincode already added")

    new_pincode = ServiceablePincode(
        pincode=pincode_clean,
        dealer_id=dealer.id,
        is_active=True
    )
    db.add(new_pincode)
    await db.commit()
    await db.refresh(new_pincode)
    return new_pincode

@router.delete("/serviceable-pincodes/{pincode}", tags=["dealers"])
async def remove_serviceable_pincode(
    pincode: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized as dealer")

    res = await db.execute(
        select(ServiceablePincode).where(
            ServiceablePincode.pincode == pincode,
            ServiceablePincode.dealer_id == dealer.id
        )
    )
    existing = res.scalar_one_or_none()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Pincode not found in your list")

    await db.delete(existing)
    await db.commit()
    return {"message": "Pincode removed successfully"}

# Moved dealer_id routes to prevent shadowing
@router.get("/{dealer_id}", response_model=DealerSchema)
async def get_dealer(
    dealer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dealer details"""
    result = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
    dealer = result.scalar_one_or_none()
    
    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dealer not found"
        )
    
    return dealer

@router.put("/{dealer_id}", response_model=DealerSchema)
async def update_dealer(
    dealer_id: UUID,
    dealer_data: DealerUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update dealer profile (dealer owner or admin)"""
    result = await db.execute(select(Dealer).where(Dealer.is_deleted == False).where(Dealer.id == dealer_id))
    dealer = result.scalar_one_or_none()
    
    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dealer not found"
        )
    
    # Check permissions: dealer owner, associated staff, or admin
    is_authorized = (
        dealer.user_id == current_user.id or 
        current_user.dealer_id == dealer.id or
        current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    )
    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this dealer profile"
        )
    
    # Update fields
    if dealer_data.business_name is not None:
        dealer.business_name = dealer_data.business_name
    if dealer_data.business_address is not None:
        dealer.business_address = dealer_data.business_address
    if dealer_data.gst_number is not None:
        dealer.gst_number = dealer_data.gst_number
    
    await db.commit()
    await db.refresh(dealer)
    
    return dealer

@router.put("/{dealer_id}/approve", response_model=DealerSchema)
async def approve_dealer(
    dealer_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve dealer (admin only)"""
    result = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False)
        .options(selectinload(Dealer.user))
        .where(Dealer.id == dealer_id)
    )
    dealer = result.scalar_one_or_none()
    
    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dealer not found"
        )
    
    # Extract email and business name before committing, as commit expires attributes
    dealer_email = dealer.user.email if (dealer.user and dealer.user.email) else None
    business_name = dealer.business_name
    
    dealer.is_approved = True
    dealer.access_status = 'active'
    dealer.profile_status = 'completed'
    
    # Auto-create Default Hub if none exists
    from models.hub import DeliveryHub
    hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.dealer_id == dealer.id))
    existing_hub = hub_res.scalars().first()
    if not existing_hub:
        default_hub = DeliveryHub(
            dealer_id=dealer.id,
            name="Primary Warehouse",
            address=dealer.business_address or "Head Office",
            city=dealer.city,
            state=dealer.state,
            state_id=dealer.state_id,
            country_id=dealer.country_id,
            pincode=dealer.pincode,
            lat_long=dealer.lat_long,
            phone=dealer.business_phone,
            is_active=True,
            is_showroom=False,
            hub_type="Warehouse"
        )
        db.add(default_hub)
    
    await db.commit()
    
    # Send email notification
    if dealer_email:
        from services.notification import EmailService
        await EmailService.send_dealer_status_notification(
            to_email=dealer_email,
            business_name=business_name,
            approved=True
        )
        
    await db.refresh(dealer)
    return dealer

class RejectReasonPayload(BaseModel):
    reason: str

@router.put("/{dealer_id}/reject", response_model=DealerSchema)
async def reject_dealer(
    dealer_id: UUID,
    payload: RejectReasonPayload,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject/unapprove dealer (admin only)"""
    result = await db.execute(
        select(Dealer).where(Dealer.is_deleted == False)
        .options(selectinload(Dealer.user))
        .where(Dealer.id == dealer_id)
    )
    dealer = result.scalar_one_or_none()
    
    if not dealer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dealer not found"
        )
    
    # Extract email and business name before committing, as commit expires attributes
    dealer_email = dealer.user.email if (dealer.user and dealer.user.email) else None
    business_name = dealer.business_name
    
    dealer.is_approved = False
    dealer.access_status = 'reject'
    dealer.profile_status = 'draft'
    dealer.reject_reason = payload.reason
    
    await db.commit()
    
    # Send email notification
    if dealer_email:
        from services.notification import EmailService
        await EmailService.send_dealer_status_notification(
            to_email=dealer_email,
            business_name=business_name,
            approved=False,
            reason=payload.reason
        )
        
    await db.refresh(dealer)
    return dealer

@router.post("/users", response_model=UserManageResponse, status_code=201)
async def create_dealer_user(
    payload: UserManageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new staff or hub user for this dealer"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Valid Roles
    if payload.role not in ALL_MANAGEMENT_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role.")

    # Check email
    check = await db.execute(select(User).where(User.email == payload.email, User.is_active == True))
    if check.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Check employee_id uniqueness
    if payload.employee_id:
        emp_check = await db.execute(select(User).where(User.employee_id == payload.employee_id))
        if emp_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Employee ID already exists")
        
    from core.security import get_password_hash
    new_user = User(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        dealer_id=dealer.id,
        hub_id=payload.hub_id if payload.role in HUB_ROLES + SHOWROOM_ROLES + [UserRole.RIDER, UserRole.DELIVERY_PARTNER] else None,
        phone=payload.phone,
        employee_id=payload.employee_id if payload.employee_id else None,
        shift_type=payload.shift_type,
        dob=payload.dob,
        address=payload.address,
        aadhaar_number=payload.aadhaar_number,
        emergency_contact=payload.emergency_contact,
        photo_url=payload.photo_url,
        aadhaar_image=payload.aadhaar_image
    )
    db.add(new_user)
    await db.flush() # Get user ID
    
    # â”€â”€ Assign to HUB if requested â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if payload.role == UserRole.HUB and payload.hub_id:
        hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.id == payload.hub_id, DeliveryHub.dealer_id == dealer.id))
        hub = hub_res.scalar_one_or_none()
        if not hub:
            raise HTTPException(status_code=404, detail="Hub not found")
        
        # Clear previous manager if any
        hub.user_id = new_user.id
        
    # â”€â”€ Handle Rider Profile creation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if payload.role in [UserRole.RIDER, UserRole.DELIVERY_PARTNER]:
        rider_profile = DeliveryRider(
            user_id=new_user.id,
            dealer_id=dealer.id,
            hub_id=payload.hub_id,
            vehicle_type=payload.vehicle_type,
            vehicle_number=payload.vehicle_number,
            vehicle_model=payload.vehicle_model,
            insurance_expiry=payload.insurance_expiry,
            dob=payload.dob,
            phone_number=payload.phone,
            license_number=payload.license_number,
            aadhaar_number=payload.aadhaar_number,
            emergency_contact=payload.emergency_contact,
            address=payload.address,
            photo_url=payload.photo_url,
            aadhaar_image=payload.aadhaar_image,
            license_image=payload.license_image,
            bank_name=payload.bank_name,
            account_number=payload.account_number,
            ifsc_code=payload.ifsc_code,
            upi_id=payload.upi_id,
            managed_by="dealer",
            is_approved=payload.is_approved if hasattr(payload, 'is_approved') else True,
            is_available=True,
            created_by=current_user.id,
            updated_by=current_user.id
        )
        db.add(rider_profile)
        
    await db.commit()
    await db.refresh(new_user)
    
    # â”€â”€ Populate Response â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    res_data = UserManageResponse.model_validate(new_user)
    
    # Manually attach hub_id if not caught by model_validate
    if not res_data.hub_id:
        res_data.hub_id = new_user.hub_id
        
    # If it's a rider, pull data from the rider profile we just created
    if payload.role in [UserRole.RIDER, UserRole.DELIVERY_PARTNER]:
        rider_res = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == new_user.id))
        rider = rider_res.scalar_one_or_none()
        if rider:
            res_data.vehicle_type = rider.vehicle_type
            res_data.vehicle_number = rider.vehicle_number
            res_data.vehicle_model = rider.vehicle_model
            res_data.insurance_expiry = rider.insurance_expiry
            res_data.dob = rider.dob
            res_data.license_number = rider.license_number
            res_data.aadhaar_number = rider.aadhaar_number
            res_data.emergency_contact = rider.emergency_contact
            res_data.address = rider.address
            res_data.photo_url = rider.photo_url
            res_data.aadhaar_image = rider.aadhaar_image
            res_data.license_image = rider.license_image
            res_data.bank_name = rider.bank_name
            res_data.account_number = rider.account_number
            res_data.ifsc_code = rider.ifsc_code
            res_data.upi_id = rider.upi_id
            res_data.is_approved = rider.is_approved
            res_data.created_by = rider.created_by
            res_data.updated_by = rider.updated_by

    return res_data

@router.put("/users/{user_id}", response_model=UserManageResponse)
async def update_dealer_user(
    user_id: int,
    payload: UserManageUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a staff or hub user"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user_res = await db.execute(select(User).where(User.id == user_id))
    target_user = user_res.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Verify the user belongs to this dealer
    belongs = False
    if target_user.dealer_id == dealer.id:
        belongs = True
    elif target_user.hub_id:
        # Check if the hub belongs to this dealer
        h_res = await db.execute(select(DeliveryHub).where(DeliveryHub.id == target_user.hub_id, DeliveryHub.dealer_id == dealer.id))
        if h_res.scalar_one_or_none():
            belongs = True
    else:
        # Check old hub managers style
        hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == user_id, DeliveryHub.dealer_id == dealer.id))
        if hub_res.scalar_one_or_none():
            belongs = True
            
    if not belongs:
        raise HTTPException(status_code=403, detail="Not authorized to manage this user")

    # Use exclude_unset so we can distinguish "field explicitly set to null" from "field not sent"
    update_fields = payload.model_dump(exclude_unset=True)

    if "full_name" in update_fields and update_fields["full_name"] is not None:
        target_user.full_name = update_fields["full_name"]
    if "is_active" in update_fields and update_fields["is_active"] is not None:
        target_user.is_active = update_fields["is_active"]
    if "phone" in update_fields and update_fields["phone"] is not None:
        target_user.phone = update_fields["phone"]
    if update_fields.get("password"):
        from core.security import get_password_hash
        target_user.password_hash = get_password_hash(update_fields["password"])

    if "employee_id" in update_fields:
        val = update_fields["employee_id"] if update_fields["employee_id"] else None
        if val and val != target_user.employee_id:
            emp_check = await db.execute(select(User).where(User.employee_id == val))
            if emp_check.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Employee ID already exists")
        target_user.employee_id = val
    if "shift_type" in update_fields: target_user.shift_type = update_fields["shift_type"]
    if "dob" in update_fields and update_fields["dob"] is not None: target_user.dob = update_fields["dob"]
    if "address" in update_fields and update_fields["address"] is not None: target_user.address = update_fields["address"]
    if "aadhaar_number" in update_fields and update_fields["aadhaar_number"] is not None: target_user.aadhaar_number = update_fields["aadhaar_number"]
    if "emergency_contact" in update_fields and update_fields["emergency_contact"] is not None: target_user.emergency_contact = update_fields["emergency_contact"]
    if "photo_url" in update_fields and update_fields["photo_url"] is not None: target_user.photo_url = update_fields["photo_url"]
    if "aadhaar_image" in update_fields and update_fields["aadhaar_image"] is not None: target_user.aadhaar_image = update_fields["aadhaar_image"]

    if "role" in update_fields and update_fields["role"] is not None:
        if update_fields["role"] not in ALL_MANAGEMENT_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role.")
        target_user.role = update_fields["role"]

    # hub_id: explicitly sent (even as null) means update the assignment
    if "hub_id" in update_fields:
        new_hub_id = update_fields["hub_id"]
        if new_hub_id and new_hub_id > 0:
            target_user.hub_id = new_hub_id
        else:
            target_user.hub_id = None

        # For old-style HUB managers, sync the DeliveryHub.user_id if needed
        if target_user.role == UserRole.HUB:
            await db.execute(
                __import__('sqlalchemy').text("UPDATE delivery_hubs SET user_id = NULL WHERE user_id = :uid"),
                {"uid": target_user.id}
            )
            if target_user.hub_id:
                hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.id == target_user.hub_id, DeliveryHub.dealer_id == dealer.id))
                hub = hub_res.scalar_one_or_none()
                if hub:
                    hub.user_id = target_user.id

    # Update Rider profile if role is (or becomes) rider
    effective_role = update_fields.get("role", target_user.role)
    if effective_role in [UserRole.RIDER, UserRole.DELIVERY_PARTNER]:
        res = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == target_user.id))
        rider = res.scalar_one_or_none()

        if not rider:
            # Create profile if it doesn't exist but role is now rider
            rider = DeliveryRider(
                user_id=target_user.id,
                dealer_id=dealer.id,
                managed_by="dealer",
                is_approved=payload.is_approved if hasattr(payload, 'is_approved') else True,
                is_available=True,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            db.add(rider)
            await db.flush()

        # hub_id for rider profile â€” same logic
        if "hub_id" in update_fields:
            new_hub_id = update_fields["hub_id"]
            rider.hub_id = new_hub_id if (new_hub_id and new_hub_id > 0) else None
        if "vehicle_type" in update_fields and update_fields["vehicle_type"] is not None: rider.vehicle_type = update_fields["vehicle_type"]
        if "vehicle_number" in update_fields and update_fields["vehicle_number"] is not None: rider.vehicle_number = update_fields["vehicle_number"]
        if "vehicle_model" in update_fields and update_fields["vehicle_model"] is not None: rider.vehicle_model = update_fields["vehicle_model"]
        if "insurance_expiry" in update_fields and update_fields["insurance_expiry"] is not None: rider.insurance_expiry = update_fields["insurance_expiry"]
        if "dob" in update_fields and update_fields["dob"] is not None: rider.dob = update_fields["dob"]

        # Sync phone numbers
        if "phone" in update_fields and update_fields["phone"] is not None:
            rider.phone_number = update_fields["phone"]
            target_user.phone = update_fields["phone"]

        if "license_number" in update_fields and update_fields["license_number"] is not None: rider.license_number = update_fields["license_number"]
        if "aadhaar_number" in update_fields and update_fields["aadhaar_number"] is not None: rider.aadhaar_number = update_fields["aadhaar_number"]
        if "emergency_contact" in update_fields and update_fields["emergency_contact"] is not None: rider.emergency_contact = update_fields["emergency_contact"]
        if "address" in update_fields and update_fields["address"] is not None: rider.address = update_fields["address"]
        if "photo_url" in update_fields and update_fields["photo_url"] is not None: rider.photo_url = update_fields["photo_url"]
        if "aadhaar_image" in update_fields and update_fields["aadhaar_image"] is not None: rider.aadhaar_image = update_fields["aadhaar_image"]
        if "license_image" in update_fields and update_fields["license_image"] is not None: rider.license_image = update_fields["license_image"]
        if "bank_name" in update_fields and update_fields["bank_name"] is not None: rider.bank_name = update_fields["bank_name"]
        if "account_number" in update_fields and update_fields["account_number"] is not None: rider.account_number = update_fields["account_number"]
        if "ifsc_code" in update_fields and update_fields["ifsc_code"] is not None: rider.ifsc_code = update_fields["ifsc_code"]
        if "upi_id" in update_fields and update_fields["upi_id"] is not None: rider.upi_id = update_fields["upi_id"]
        if "is_approved" in update_fields and update_fields["is_approved"] is not None:
            rider.is_approved = update_fields["is_approved"]
        rider.updated_by = current_user.id

    await db.commit()
    await db.refresh(target_user)
    
    # Prepare response
    # Use a fresh fetch to ensure all relations are loaded and fields are updated
    user_final_res = await db.execute(select(User).where(User.id == target_user.id))
    user_final = user_final_res.scalar_one()
    
    res_data = UserManageResponse.model_validate(user_final)
    if user_final.hub_id:
        res_data.hub_id = user_final.hub_id
        
    # If it's a rider, pull data from the rider profile
    if user_final.role in [UserRole.DELIVERY_PARTNER, UserRole.RIDER]:
        res_res = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == target_user.id))
        rider = res_res.scalar_one_or_none()
        if rider:
            res_data.vehicle_type = rider.vehicle_type
            res_data.vehicle_number = rider.vehicle_number
            res_data.vehicle_model = rider.vehicle_model
            res_data.insurance_expiry = rider.insurance_expiry
            res_data.dob = rider.dob
            res_data.license_number = rider.license_number
            res_data.aadhaar_number = rider.aadhaar_number
            res_data.emergency_contact = rider.emergency_contact
            res_data.address = rider.address
            res_data.photo_url = rider.photo_url
            res_data.aadhaar_image = rider.aadhaar_image
            res_data.license_image = rider.license_image
            res_data.bank_name = rider.bank_name
            res_data.account_number = rider.account_number
            res_data.ifsc_code = rider.ifsc_code
            res_data.upi_id = rider.upi_id
            res_data.is_approved = rider.is_approved
            res_data.created_by = rider.created_by
            res_data.updated_by = rider.updated_by

    return res_data

@router.delete("/users/{user_id}")
async def delete_dealer_user(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate or remove a user (Dealer choice, here we just deactivate for safety)"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    user_res = await db.execute(select(User).where(User.id == user_id))
    target_user = user_res.scalar_one_or_none()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check ownership
    if target_user.dealer_id != dealer.id:
        hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == user_id, DeliveryHub.dealer_id == dealer.id))
        if not hub_res.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not authorized")

    target_user.is_active = False
    await db.commit()
    return {"status": "success", "message": "User deactivated"}

@router.post("/products/{product_id}/stock", status_code=status.HTTP_200_OK)
async def update_dealer_stock(
    product_id: UUID,
    payload: DealerStockUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update stock for a specific product (dealer only).
    Handles both stock-in and stock-out and records the movement.
    """
    if payload.product_id != product_id:
        raise HTTPException(status_code=400, detail="Product ID mismatch")

    # Resolve dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Not authorized. Dealer profile not found.")

    # Fetch product
    result = await db.execute(select(Product).where(Product.id == product_id, Product.dealer_id == dealer.id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not owned by you")

    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    stock_before = product.stock
    quantity_change = 0
    movement_type = None
    
    if payload.update_type.lower() == 'in':
        quantity_change = payload.quantity
        product.stock += payload.quantity
        movement_type = MovementType.RESTOCK
    elif payload.update_type.lower() == 'out':
        if product.stock < payload.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock for adjustment")
        quantity_change = -payload.quantity
        product.stock -= payload.quantity
        movement_type = MovementType.ADJUSTMENT
    else:
        raise HTTPException(status_code=400, detail="Invalid update type. Must be 'in' or 'out'")

    # Create stock movement record
    movement = StockMovement(
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity_change,
        stock_before=stock_before,
        stock_after=product.stock,
        user_id=current_user.id,
        notes=payload.notes or (payload.reason if payload.update_type.lower() == 'out' else "Dealer stock update")
    )
    db.add(movement)
    await db.commit()
    await db.refresh(product)
    
    return {
        "status": "success",
        "message": f"Stock {'added' if quantity_change > 0 else 'removed'} successfully",
        "current_stock": product.stock
    }
