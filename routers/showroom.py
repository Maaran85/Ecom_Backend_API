from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func, desc, case
from sqlalchemy.orm import selectinload, aliased
from typing import List, Optional
from datetime import datetime, timezone
import random
import string

from core.database import get_db
from core.permissions import get_current_active_user
from models import User, DeliveryHub, Product, LocationInventory, UserRole, Order, OrderItem, OrderStatus, StockMovement, MovementType, Category
from schemas.showroom import (
    ShowroomCreate, ShowroomUpdate, LocationInventoryResponse, 
    StockTransferRequest, ShowroomSaleRequest, ShowroomSaleHistory,
    ShowroomSalesResponse
)
from schemas.dealer import Hub as HubSchema
from routers.dealers import get_current_dealer

router = APIRouter()

@router.post("/", response_model=HubSchema, status_code=status.HTTP_201_CREATED)
async def create_showroom(
    showroom_data: ShowroomCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new showroom for the dealer"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    new_showroom = DeliveryHub(
        **showroom_data.model_dump(),
        dealer_id=dealer.id,
        is_showroom=True
    )
    db.add(new_showroom)
    await db.commit()
    await db.refresh(new_showroom)
    return new_showroom

@router.get("/", response_model=List[HubSchema])
async def list_showrooms(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all showrooms for the dealer"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    print(f"DEBUG: Listing showrooms for dealer_id={dealer.id}")
    result = await db.execute(
        select(DeliveryHub).where(
            and_(DeliveryHub.dealer_id == dealer.id, DeliveryHub.is_showroom == True)
        )
    )
    showrooms = result.scalars().all()
    print(f"DEBUG: Found {len(showrooms)} showrooms")
    return showrooms

@router.get("/sales", response_model=ShowroomSalesResponse)
async def get_all_showroom_sales(
    showroom_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get sales history for showrooms of the dealer with pagination and search"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    skip = (page - 1) * limit

    # Base query for orders starting with SR- that belong to this dealer's products
    base_query = (
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .join(Product, OrderItem.product_id == Product.id)
        .where(Product.dealer_id == dealer.id)
        .where(Order.order_number.ilike("SR-%"))
    )

    if showroom_id:
        base_query = base_query.where(OrderItem.hub_id == showroom_id)
        
    if start_date:
        base_query = base_query.where(Order.created_at >= start_date)
    if end_date:
        base_query = base_query.where(Order.created_at <= end_date)

    base_query = base_query.distinct()
    
    if search:
        search_query = f"%{search}%"
        base_query = base_query.where(
            (Order.order_number.ilike(search_query)) |
            (Order.customer_name.ilike(search_query)) |
            (Order.customer_phone.ilike(search_query))
        )
        
    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    # Get paginated results
    query = (
        base_query
        .order_by(desc(Order.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    sales_history = []
    for order in orders:
        # Get item count and total for THIS dealer specifically
        item_stats_query = (
            select(func.count(OrderItem.id), func.sum(OrderItem.price * OrderItem.quantity))
            .join(Product, OrderItem.product_id == Product.id)
            .where(and_(OrderItem.order_id == order.id, Product.dealer_id == dealer.id))
        )
        if showroom_id:
            item_stats_query = item_stats_query.where(OrderItem.hub_id == showroom_id)
            
        stats_res = await db.execute(item_stats_query)
        items_count, dealer_subtotal = stats_res.one()
        
        # Get showroom name (if any item has hub_id)
        showroom_name = "Various"
        hub_res = await db.execute(
            select(DeliveryHub.name).join(OrderItem, OrderItem.hub_id == DeliveryHub.id).where(OrderItem.order_id == order.id).limit(1)
        )
        found_hub = hub_res.scalar_one_or_none()
        if found_hub:
            showroom_name = found_hub

        sales_history.append(ShowroomSaleHistory(
            id=order.id,
            order_number=order.order_number,
            customer_name=order.customer_name or "Direct Customer",
            customer_phone=order.customer_phone,
            subtotal=dealer_subtotal or 0.0,
            discount_amount=0.0, # Showroom direct discount logic might need refinement if shared, but for now 0
            total_amount=dealer_subtotal or 0.0,
            payment_method=order.payment_method,
            created_at=order.created_at,
            items_count=items_count or 0,
            showroom_name=showroom_name
        ))
    
    return {
        "items": sales_history,
        "total": total_count,
        "page": page,
        "limit": limit
    }

@router.get("/{showroom_id}", response_model=HubSchema)
async def get_showroom_details(
    showroom_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get details for a specific showroom"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    result = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    showroom = result.scalar_one_or_none()
    if not showroom:
        raise HTTPException(status_code=404, detail="Showroom not found")
    return showroom

@router.post("/{showroom_id}/transfer", status_code=status.HTTP_200_OK)
async def transfer_stock(
    showroom_id: int,
    transfer_data: StockTransferRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Transfer stock from dealer main pool or another hub to a showroom"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # 1. Verify product exists and belongs to dealer
    product_result = await db.execute(
        select(Product).where(and_(Product.id == transfer_data.product_id, Product.dealer_id == dealer.id))
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or not owned by dealer")
    
    # 2. Verify target showroom exists and belongs to dealer
    showroom_result = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    showroom = showroom_result.scalar_one_or_none()
    if not showroom:
        raise HTTPException(status_code=404, detail="Showroom not found")
    
    # 3. Deduct from source (Main pool or Source Hub)
    if transfer_data.from_hub_id is None:
        if product.stock < transfer_data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock in main pool")
        product.stock -= transfer_data.quantity
        
        # Log movement for main pool
        movement = StockMovement(
            product_id=product.id,
            movement_type=MovementType.ADJUSTMENT,
            quantity=-transfer_data.quantity,
            stock_before=product.stock + transfer_data.quantity,
            stock_after=product.stock,
            user_id=current_user.id,
            notes=f"Transfer to showroom {showroom.name}. {transfer_data.notes or ''}"
        )
        db.add(movement)
    else:
        # Transfer from another hub/showroom
        source_inv_result = await db.execute(
            select(LocationInventory).where(
                and_(LocationInventory.product_id == product.id, LocationInventory.hub_id == transfer_data.from_hub_id)
            )
        )
        source_inv = source_inv_result.scalar_one_or_none()
        if not source_inv or source_inv.quantity < transfer_data.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock in source hub")
        source_inv.quantity -= transfer_data.quantity
    
    # 4. Add to target showroom
    target_inv_result = await db.execute(
        select(LocationInventory).where(
            and_(LocationInventory.product_id == product.id, LocationInventory.hub_id == showroom_id)
        )
    )
    target_inv = target_inv_result.scalar_one_or_none()
    if target_inv:
        target_inv.quantity += transfer_data.quantity
    else:
        target_inv = LocationInventory(
            product_id=product.id,
            hub_id=showroom_id,
            quantity=transfer_data.quantity
        )
        db.add(target_inv)
    
    await db.commit()
    return {"message": "Stock transferred successfully"}

@router.post("/{showroom_id}/sales", status_code=status.HTTP_201_CREATED)
async def record_showroom_sale(
    showroom_id: int,
    sale_data: ShowroomSaleRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a direct sale from a showroom"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # 1. Verify showroom
    showroom_result = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    showroom = showroom_result.scalar_one_or_none()
    if not showroom:
        raise HTTPException(status_code=404, detail="Showroom not found")
    
    # 2. Process items and check inventory
    total_amount = 0
    order_items = []
    
    for item in sale_data.items:
        # Check dealer ownership
        product_result = await db.execute(
            select(Product).where(and_(Product.id == item.product_id, Product.dealer_id == dealer.id))
        )
        product = product_result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        
        # Check showroom inventory
        inv_result = await db.execute(
            select(LocationInventory).where(
                and_(LocationInventory.product_id == item.product_id, LocationInventory.hub_id == showroom_id)
            )
        )
        inv = inv_result.scalar_one_or_none()
        if not inv or inv.quantity < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient inventory for product {product.name} at this showroom")
        
        # Deduct inventory
        inv.quantity -= item.quantity
        
        # Prepare order item
        total_amount += item.price * item.quantity
        order_items.append(OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price,
            size=item.size,
            status="delivered",
            payment_status="paid",
            hub_id=showroom_id,
            delivered_at=datetime.now(timezone.utc)
        ))
    
    # 3. Create Order
    subtotal = total_amount
    discount = sale_data.discount_amount or 0.0
    final_total = max(0.0, float(subtotal - discount))
    
    # Unique order number with random suffix (limit 20 chars)
    timestamp = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S') 
    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=2))
    order_num = f"SR-{timestamp}-{random_suffix}"

    # 3. Find or create a CustomerUser for this walk-in sale
    # This is important because Order requires a customer_id (ForeignKey to customer_users.id)
    # and NO longer has a user_id (staff) column.
    from models.customer_user import CustomerUser
    customer_phone = sale_data.customer_phone or "0000000000" # fallback if missing
    
    # Try finding existing customer
    res = await db.execute(select(CustomerUser).where(CustomerUser.phone == customer_phone))
    customer = res.scalar_one_or_none()
    
    if not customer:
        # Create a new mini-profile for this walk-in customer
        customer = CustomerUser(
            phone=customer_phone,
            full_name=sale_data.customer_name or "Showroom Walk-in",
            is_active=True
        )
        db.add(customer)
        await db.flush() # get customer.id
    
    new_order = Order(
        customer_id=customer.id,
        subtotal=subtotal,
        discount_amount=discount,
        total_amount=final_total,
        status=OrderStatus.DELIVERED,
        payment_method=sale_data.payment_method,
        delivered_at=datetime.now(timezone.utc),
        order_number=order_num,
        customer_name=sale_data.customer_name or customer.full_name,
        customer_phone=sale_data.customer_phone or customer.phone,
        notes=sale_data.notes
    )
    
    # Associate items
    for oi in order_items:
        oi.order = new_order
    
    db.add(new_order)
    # No need for manual add of order_items if relationship is correct, 
    # but let's be safe and add them to session
    for oi in order_items:
        db.add(oi)
        
    try:
        await db.commit()
        await db.refresh(new_order)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    return {
        "message": "Sale recorded successfully", 
        "order_id": new_order.id, 
        "order_number": new_order.order_number
    }

@router.get("/{showroom_id}/inventory", response_model=List[LocationInventoryResponse])
async def get_showroom_inventory(
    showroom_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get inventory levels for a specific showroom"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # Verify showroom belongs to dealer
    showroom_check = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    if not showroom_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Showroom not found")
        
    parent_cat = aliased(Category)
    query = (
        select(
            LocationInventory.id,
            LocationInventory.product_id,
            LocationInventory.hub_id,
            LocationInventory.quantity,
            LocationInventory.created_at,
            LocationInventory.updated_at,
            Product.name.label("product_name"),
            Product.price.label("product_price"),
            Product.images.label("product_image"),
            Product.category_id,
            Category.name.label("category_name"),
            func.coalesce(parent_cat.name, Category.name).label("main_category_name")
        )
        .join(Product, LocationInventory.product_id == Product.id, isouter=True)
        .join(Category, Product.category_id == Category.id, isouter=True)
        .join(parent_cat, Category.parent_id == parent_cat.id, isouter=True)
        .where(LocationInventory.hub_id == showroom_id)
    )
    result = await db.execute(query)
    return result.mappings().all()


@router.get("/{showroom_id}/sales", response_model=ShowroomSalesResponse)
async def get_showroom_sales(
    showroom_id: int,
    search: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get sales history for a specific showroom with pagination and search"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # Verify showroom belongs to dealer
    res = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    showroom = res.scalar_one_or_none()
    if not showroom:
        raise HTTPException(status_code=404, detail="Showroom not found")

    skip = (page - 1) * limit

    # Base query for orders linked to this showroom via items
    base_query = (
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .where(OrderItem.hub_id == showroom_id)
    )

    if start_date:
        base_query = base_query.where(Order.created_at >= start_date)
    if end_date:
        base_query = base_query.where(Order.created_at <= end_date)

    base_query = base_query.distinct()
    
    if search:
        search_query = f"%{search}%"
        base_query = base_query.where(
            (Order.order_number.ilike(search_query)) |
            (Order.customer_name.ilike(search_query)) |
            (Order.customer_phone.ilike(search_query))
        )
        
    # Get total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    # Get paginated results
    query = (
        base_query
        .order_by(desc(Order.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    sales_history = []
    for order in orders:
        # Count items and total for this specific showroom/dealer in this order
        item_stats_query = (
            select(func.count(OrderItem.id), func.sum(OrderItem.price * OrderItem.quantity))
            .join(Product, OrderItem.product_id == Product.id)
            .where(and_(
                OrderItem.order_id == order.id, 
                OrderItem.hub_id == showroom_id,
                Product.dealer_id == dealer.id
            ))
        )
        stats_res = await db.execute(item_stats_query)
        items_count, dealer_subtotal = stats_res.one()
        
        sales_history.append(ShowroomSaleHistory(
            id=order.id,
            order_number=order.order_number,
            customer_name=order.customer_name or "Direct Customer",
            customer_phone=order.customer_phone,
            subtotal=dealer_subtotal or 0.0,
            discount_amount=0.0,
            total_amount=dealer_subtotal or 0.0,
            payment_method=order.payment_method,
            created_at=order.created_at,
            items_count=items_count or 0,
            showroom_name=showroom.name
        ))
    
    return {
        "items": sales_history,
        "total": total_count,
        "page": page,
        "limit": limit
    }


@router.get("/{showroom_id}/sales/{order_id}")
async def get_showroom_sale_detail(
    showroom_id: int,
    order_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information for a specific showroom sale"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
        
    # Verify order and showroom linkage
    query = (
        select(Order)
        .join(OrderItem, Order.id == OrderItem.order_id)
        .where(and_(Order.id == order_id, OrderItem.hub_id == showroom_id))
        .options(
            selectinload(Order.items).selectinload(OrderItem.product)
        )
    )
    
    result = await db.execute(query)
    order = result.scalar_one_or_none()
    
    if not order:
        # Try finding without user_id if it's a dealer checking staff sales
        query = (
            select(Order)
            .join(OrderItem, Order.id == OrderItem.order_id)
            .join(Product, OrderItem.product_id == Product.id)
            .where(and_(Order.id == order_id, OrderItem.hub_id == showroom_id, Product.dealer_id == dealer.id))
            .options(
                selectinload(Order.items).selectinload(OrderItem.product)
            )
        )
        result = await db.execute(query)
        order = result.scalar_one_or_none()
        
    if not order:
        raise HTTPException(status_code=404, detail="Sale record not found")
        
    # Filter items to only show this dealer's products
    dealer_items = [
        item for item in order.items 
        if item.product.dealer_id == dealer.id
    ]
    
    # Update order object temporarily for serialization or create a dict
    order_dict = {
        "id": order.id,
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "subtotal": sum(item.price * item.quantity for item in dealer_items),
        "total_amount": sum(item.price * item.quantity for item in dealer_items),
        "payment_method": order.payment_method,
        "status": order.status,
        "created_at": order.created_at,
        "items": dealer_items
    }
    
    return order_dict


@router.get("/{showroom_id}/dashboard")
async def get_showroom_dashboard_stats(
    showroom_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard stats for a specific showroom"""
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # Verify showroom
    res = await db.execute(
        select(DeliveryHub).where(and_(DeliveryHub.id == showroom_id, DeliveryHub.dealer_id == dealer.id))
    )
    showroom = res.scalar_one_or_none()
    if not showroom:
        raise HTTPException(status_code=404, detail="Showroom not found")

    # Today's boundaries
    today = datetime.utcnow().date()
    start_of_today = datetime.combine(today, datetime.min.time())
    
    # 1. Today's Sales & Total Customers Today
    sales_query = (
        select(func.sum(Order.total_amount), func.count(func.distinct(Order.customer_phone)))
        .where(
            and_(
                Order.created_at >= start_of_today,
                Order.status != OrderStatus.CANCELLED,
                Order.id.in_(
                    select(OrderItem.order_id).where(OrderItem.hub_id == showroom_id)
                )
            )
        )
    )
    sales_res = await db.execute(sales_query)
    today_sales, total_customers = sales_res.one()
    
    inv_query = (
        select(
            func.sum(LocationInventory.quantity),
            func.sum(case((and_(LocationInventory.quantity <= 5, LocationInventory.quantity > 0), 1), else_=0)),
            func.sum(case((LocationInventory.quantity == 0, 1), else_=0))
        )
        .where(LocationInventory.hub_id == showroom_id)
    )
    inv_res = await db.execute(inv_query)
    total_stock, low_stock, out_of_stock = inv_res.one()
    
    return {
        "todaySales": today_sales or 0.0,
        "totalCustomers": total_customers or 0,
        "totalStock": int(total_stock or 0),
        "lowStockItems": int(low_stock or 0),
        "outOfStockItems": int(out_of_stock or 0),
        "pendingTransfers": 0  # Stock transfers are currently immediate
    }
