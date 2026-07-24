"""
Inventory Management Router - Stock Alerts, Movement History, Bulk Updates
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Product, StockAlert, StockMovement, MovementType
from schemas.inventory import (
    StockAlertCreate, StockAlertUpdate, StockAlert as StockAlertSchema,
    StockMovementResponse, BulkStockUpdateRequest, BulkStockUpdateResponse
)
from services.notification import EmailService
from fastapi import BackgroundTasks

from models.hub import DeliveryHub
from models.inventory import ProductInventory
from schemas.inventory import HubStockAdd

router = APIRouter()

# ==================== STOCK ALERTS ====================

@router.post("/admin/stock-alerts", response_model=StockAlertSchema, status_code=status.HTTP_201_CREATED)
async def create_stock_alert(
    alert_data: StockAlertCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create low stock alert for a product (admin only)"""
    
    # Check if product exists
    product_result = await db.execute(select(Product).where(Product.id == alert_data.product_id))
    product = product_result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if alert already exists
    existing_result = await db.execute(
        select(StockAlert).where(StockAlert.product_id == alert_data.product_id)
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stock alert already exists for this product"
        )
    
    # Create alert
    stock_alert = StockAlert(**alert_data.model_dump())
    db.add(stock_alert)
    await db.commit()
    await db.refresh(stock_alert)
    
    return stock_alert

@router.get("/admin/stock-alerts", response_model=List[StockAlertSchema])
async def get_stock_alerts(
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all stock alerts (admin only)"""
    
    query = select(StockAlert)
    
    if is_active is not None:
        query = query.where(StockAlert.is_active == is_active)
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    return alerts

@router.get("/admin/stock-alerts/triggered", response_model=List[dict])
async def get_triggered_alerts(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get products that have triggered stock alerts (admin only)"""
    from sqlalchemy.orm import selectinload
    
    # Get all active alerts
    alerts_result = await db.execute(
        select(StockAlert)
        .where(StockAlert.is_active == True)
        .options(selectinload(StockAlert.product))
    )
    alerts = alerts_result.scalars().all()
    
    triggered = []
    for alert in alerts:
        # Product is already eagerly loaded
        product = alert.product
        
        if product and product.stock < alert.threshold:
            triggered.append({
                "alert_id": alert.id,
                "product_id": product.id,
                "product_name": product.name,
                "current_stock": product.stock,
                "threshold": alert.threshold,
                "last_alerted_at": alert.last_alerted_at
            })
    
    return triggered

@router.put("/admin/stock-alerts/{alert_id}", response_model=StockAlertSchema)
async def update_stock_alert(
    alert_id: int,
    alert_data: StockAlertUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update stock alert (admin only)"""
    
    result = await db.execute(select(StockAlert).where(StockAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock alert not found"
        )
    
    # Update fields
    update_data = alert_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(alert, field, value)
    
    await db.commit()
    await db.refresh(alert)
    
    return alert

@router.delete("/admin/stock-alerts/{alert_id}")
async def delete_stock_alert(
    alert_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete stock alert (admin only)"""
    
    result = await db.execute(select(StockAlert).where(StockAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stock alert not found"
        )
    
    await db.delete(alert)
    await db.commit()
    
    return {"message": "Stock alert deleted successfully"}

# ==================== STOCK MOVEMENT HISTORY ====================

@router.get("/admin/products/{product_id}/stock-history", response_model=List[StockMovementResponse])
async def get_product_stock_history(
    product_id: UUID,
    movement_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get stock movement history for a product (admin only)"""
    
    query = select(StockMovement).where(StockMovement.product_id == product_id)
    
    if movement_type:
        try:
            query = query.where(StockMovement.movement_type == MovementType(movement_type))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid movement type: {movement_type}"
            )
    
    query = query.order_by(StockMovement.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    movements = result.scalars().all()
    
    return movements

@router.get("/admin/stock-movements", response_model=List[StockMovementResponse])
async def get_all_stock_movements(
    movement_type: Optional[str] = None,
    product_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all stock movements with filters (admin only)"""
    
    query = select(StockMovement)
    
    if movement_type:
        try:
            query = query.where(StockMovement.movement_type == MovementType(movement_type))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid movement type: {movement_type}"
            )
    
    if product_id:
        query = query.where(StockMovement.product_id == product_id)
    
    query = query.order_by(StockMovement.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    movements = result.scalars().all()
    
    return movements

# ==================== BULK STOCK UPDATE ====================

@router.post("/admin/products/bulk-stock-update", response_model=BulkStockUpdateResponse)
async def bulk_stock_update(
    update_data: BulkStockUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Bulk update product stock (admin only)"""
    
    success_count = 0
    failed_count = 0
    results = []
    
    for item in update_data.updates:
        try:
            # Get product
            product_result = await db.execute(select(Product).where(Product.id == item.product_id))
            product = product_result.scalar_one_or_none()
            
            if not product:
                failed_count += 1
                results.append({
                    "product_id": item.product_id,
                    "success": False,
                    "error": "Product not found"
                })
                continue
            
            # Record stock movement
            stock_before = product.stock
            stock_after = item.quantity
            quantity_change = stock_after - stock_before
            
            movement = StockMovement(
                product_id=product.id,
                movement_type=MovementType.RESTOCK if quantity_change > 0 else MovementType.ADJUSTMENT,
                quantity=quantity_change,
                stock_before=stock_before,
                stock_after=stock_after,
                user_id=current_user.id,
                notes=item.notes or "Bulk stock update"
            )
            db.add(movement)
            
            # Find an inventory record or create one for hub 1 (default hub)
            hub_inv = await db.execute(select(ProductInventory).where(ProductInventory.product_id == product.id).limit(1))
            inv = hub_inv.scalar_one_or_none()
            if inv:
                inv.stock += quantity_change
            else:
                new_inv = ProductInventory(hub_id=1, product_id=product.id, stock=stock_after)
                db.add(new_inv)
            success_count += 1
            results.append({
                "product_id": item.product_id,
                "product_name": product.name,
                "success": True,
                "stock_before": stock_before,
                "stock_after": stock_after,
                "change": quantity_change
            })
            
        except Exception as e:
            failed_count += 1
            results.append({
                "product_id": item.product_id,
                "success": False,
                "error": str(e)
            })
    
    await db.commit()
    
    return BulkStockUpdateResponse(
        success_count=success_count,
        failed_count=failed_count,
        results=results
    )

@router.post("/inventory/hub/add-stock", status_code=status.HTTP_200_OK)
async def add_hub_stock(
    data: HubStockAdd,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Hub User adding stock to their hub"""
    
    # Verify current user is a hub manager
    hub_res = await db.execute(select(DeliveryHub).where(DeliveryHub.user_id == current_user.id))
    hub = hub_res.scalar_one_or_none()
    if not hub:
        raise HTTPException(status_code=403, detail="Not authorized as Hub User")

    # Verify product exists
    prod_res = await db.execute(select(Product).where(Product.id == data.product_id))
    product = prod_res.scalar_one_or_none()
    if not product:
         raise HTTPException(status_code=404, detail="Product not found")

    # Update or create ProductInventory
    inv_res = await db.execute(
        select(ProductInventory).where(ProductInventory.hub_id == hub.id, ProductInventory.product_id == data.product_id)
    )
    hub_inv = inv_res.scalar_one_or_none()

    stock_before = hub_inv.stock if hub_inv else 0
    stock_after = stock_before + data.quantity

    if not hub_inv:
        hub_inv = ProductInventory(hub_id=hub.id, product_id=data.product_id, stock=stock_after)
        db.add(hub_inv)
    else:
        hub_inv.stock = stock_after

    # Log movement
    movement = StockMovement(
        product_id=data.product_id,
        movement_type=MovementType.RESTOCK,
        quantity=data.quantity,
        stock_before=stock_before,
        stock_after=stock_after,
        hub_id=hub.id,
        user_id=current_user.id,
        notes="Hub User added inventory"
    )
    db.add(movement)
    await db.commit()
    return {"message": "Stock added successfully", "new_stock": stock_after}

@router.post("/inventory/run-checks", status_code=status.HTTP_200_OK)
async def run_inventory_checks(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger low stock checks and send email alerts.
    In production, this could be called by a cron job system.
    """
    # 1. Get all active alerts
    alerts_result = await db.execute(select(StockAlert).where(StockAlert.is_active == True))
    alerts = alerts_result.scalars().all()
    
    if not alerts:
        return {"message": "No active stock alerts configured"}
    
    # 2. Check stock levels
    alerts_triggered = []
    
    # Group by owner (Dealer/Admin) to send consolidated emails
    # Since we don't have easy owner lookup on product without join, let's join.
    # Actually Product has dealer_id. If None, it's Admin.
    
    # We need to fetch product info for each alert
    # Optimization: Fetch all products involved in alerts
    product_ids = [a.product_id for a in alerts]
    products_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
    products_map = {p.id: p for p in products_result.scalars().all()}
    
    # Prepare data for emails
    # Map: OwnerEmail -> List[ProductData]
    notifications_map = {}
    
    # helper for admin email
    admin_result = await db.execute(select(User).where(User.role == "admin").limit(1)) # Simplification: Just send to first admin or configured email
    admin_user = admin_result.scalar_one_or_none()
    admin_email = admin_user.email if admin_user else "admin@example.com"
    
    for alert in alerts:
        product = products_map.get(alert.product_id)
        if not product:
            continue
            
        if product.stock < alert.threshold:
            # Alert Triggered!
            
            # Determine Owner Email
            owner_email = admin_email
            if product.dealer_id:
                # Fetch dealer user email
                # This could be N+1 if many dealers. Accepted for now or use join above.
                # Let's do a quick fetch
                from models import Dealer
                dealer_result = await db.execute(
                    select(User.email)
                    .join(Dealer, User.id == Dealer.user_id)
                    .where(Dealer.id == product.dealer_id)
                )
                dealer_email = dealer_result.scalar_one_or_none()
                if dealer_email:
                    owner_email = dealer_email
            
            # Add to map
            if owner_email not in notifications_map:
                notifications_map[owner_email] = []
            
            notifications_map[owner_email].append({
                "name": product.name,
                "stock": product.stock,
                "threshold": alert.threshold
            })
            
            # Update last_alerted_at
            alert.last_alerted_at = datetime.utcnow()
            alerts_triggered.append(f"{product.name} (Stock: {product.stock})")
    
    await db.commit()
    
    # 3. Send Emails
    for email, items in notifications_map.items():
        background_tasks.add_task(
            EmailService.send_low_stock_alert,
            to_email=email,
            products=items
        )
            
    return {
        "message": f"Checks completed. Triggered {len(alerts_triggered)} alerts.",
        "details": alerts_triggered
    }
