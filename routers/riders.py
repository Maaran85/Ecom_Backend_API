from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_
from sqlalchemy.orm import selectinload
from core.database import get_db
from core.permissions import get_current_active_user
from models import (
    User, OrderItem, DeliveryRider, OrderStatus, UserRole, 
    PaymentStatus, Order, OrderReturn, ReturnStatus, Product, Address, RiderEarning
)
from schemas.rider import Rider, RiderUpdate, OrderItemForRider, RiderReturnTask, RiderEarningSchema
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import traceback

RIDER_ROLES = ["delivery_partner", "rider"]

router = APIRouter()

@router.get("/me", response_model=Rider)
async def get_rider_profile(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the profile of the current delivery rider."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        print(f"DEBUG: Rider auth failure - User {current_user.email} has role {current_user.role} (type: {type(current_user.role)})")
        raise HTTPException(status_code=403, detail="Not authorized as a delivery partner")
    
    result = await db.execute(
        select(DeliveryRider)
        .where(DeliveryRider.user_id == current_user.id)
        .options(selectinload(DeliveryRider.user))
    )
    rider = result.scalar_one_or_none()
    
    if not rider:
        # Self-healing: If user has rider role but no profile, create one
        print(f"DEBUG: Self-healing missing rider profile for {current_user.email}")
        rider = DeliveryRider(
            user_id=current_user.id,
            is_approved=True,
            is_available=True,
            current_status="active",
            dealer_id=current_user.dealer_id,
            hub_id=current_user.hub_id
        )
        db.add(rider)
        await db.commit()
        # Re-fetch with relationship
        result = await db.execute(
            select(DeliveryRider)
            .where(DeliveryRider.user_id == current_user.id)
            .options(selectinload(DeliveryRider.user))
        )
        rider = result.scalar_one_or_none()
        
    return rider

@router.put("/me", response_model=Rider)
async def update_rider_profile(
    update_data: RiderUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update rider profile (e.g., set availability or update location)."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Capture user_id as plain int NOW - after db.commit() current_user is expired;
    # accessing current_user.id then triggers a lazy sync load => MissingGreenlet.
    user_id: int = int(current_user.id)

    result = await db.execute(
        select(DeliveryRider)
        .where(DeliveryRider.user_id == user_id)
        .options(selectinload(DeliveryRider.user))
    )
    rider = result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(rider, key, value)
    
    await db.commit()
    
    # Re-fetch with relationship loaded (use saved user_id, not current_user.id)
    result2 = await db.execute(
        select(DeliveryRider)
        .where(DeliveryRider.user_id == user_id)
        .options(selectinload(DeliveryRider.user))
    )
    rider = result2.scalar_one()
    return rider

@router.get("/tasks", response_model=List[OrderItemForRider])
async def get_assigned_tasks(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all delivery tasks (outbound) assigned to the current rider."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    if not rider:
        print(f"DEBUG: Rider profile not found for user {current_user.id} ({current_user.email})")
        return []
    
    # query items assigned to this rider that are not yet delivered/failed/cancelled
    # We include 'undelivered' if they are still assigned to the rider and might be retried
    # We use a robust filter including dispatched/shipped/packaging
    query = (
        select(OrderItem)
        .options(
            selectinload(OrderItem.order).selectinload(Order.shipping_address),
            selectinload(OrderItem.order).selectinload(Order.customer),
            selectinload(OrderItem.product)
        )
        .where(OrderItem.rider_id == rider.id)
        .where(func.lower(OrderItem.status).notin_([
            "delivered", 
            "failed", 
            "cancelled",
            "returned",
            "rejected"
        ]))
    )
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    response = []
    for item in items:
        try:
            order = item.order
            if not order:
                print(f"DEBUG: Skipping Item ID {item.id} - Parent Order ID {item.order_id} missing")
                continue
            
            # Use safer attribute access
            customer = getattr(order, 'customer', None)
            shipping_addr = getattr(order, 'shipping_address', None)
            product = getattr(item, 'product', None)
            
            # Format shipping address nicely
            addr_str = "N/A"
            if shipping_addr:
                components = [
                    getattr(shipping_addr, 'address_line1', ''),
                    getattr(shipping_addr, 'address_line2', ''),
                    getattr(shipping_addr, 'city', ''),
                    getattr(shipping_addr, 'state', ''),
                    getattr(shipping_addr, 'pincode', '')
                ]
                addr_str = ", ".join([str(c) for c in components if c])

            # Safety first: check if product exists for naming
            p_name = "Product Not Found"
            if product:
                p_name = product.name
            elif hasattr(item, 'product_name') and item.product_name:
                p_name = item.product_name

            response.append(OrderItemForRider(
                id=item.id,
                order_number=getattr(order, 'order_number', f"ORD-{order.id}"),
                product_name=p_name,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.price,
                size=item.size,
                shipping_address=addr_str,
                customer_name=customer.full_name if (customer and customer.full_name) else (getattr(order, 'customer_name', "No Name")),
                customer_phone=customer.phone if (customer and customer.phone) else (getattr(order, 'customer_phone', "")),
                status=item.status,
                payment_status=item.payment_status or getattr(order, 'payment_status', "pending"),
                payment_method=getattr(order, 'payment_method', "COD"),
                total_amount=float(item.price * item.quantity),
                delivery_attempts=item.delivery_attempts or 0,
                color=getattr(product, 'color', None) if product else None,
                product_image=product.images[0] if (product and hasattr(product, 'images') and product.images) else None,
                rider_payment_method=item.rider_payment_method,
                is_exchange=(getattr(order, 'payment_method', "").lower() == "exchange"),
                replacement_for_return_id=None
            ))
        except Exception as e:
            print(f"DEBUG: Error processing Item {item.id} for rider {rider.id}: {e}")
            traceback.print_exc()
            continue
    
    print(f"DEBUG: Final task list size for Rider {rider.id}: {len(response)} (Found {len(items)} items in DB)")
    return response


@router.get("/tasks/history", response_model=List[OrderItemForRider])
async def get_task_history(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all completed/failed delivery tasks for the current rider."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    from sqlalchemy.orm import selectinload
    from models import Order, Product, Address
    
    query = (
        select(OrderItem)
        .options(
            selectinload(OrderItem.order).selectinload(Order.shipping_address),
            selectinload(OrderItem.order).selectinload(Order.customer),
            selectinload(OrderItem.product)
        )
        .where(OrderItem.rider_id == rider.id)
        .where(OrderItem.status.in_([
            OrderStatus.DELIVERED.value, 
            OrderStatus.FAILED.value, 
            OrderStatus.CANCELLED.value,
            OrderStatus.UNDELIVERED.value,
            OrderStatus.RETURNED.value
        ]))
        .order_by(OrderItem.updated_at.desc().nulls_last(), OrderItem.id.desc())
    )
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    response = []
    for item in items:
        order = item.order
        response.append(OrderItemForRider(
            id=item.id,
            order_number=order.order_number or f"ORD-{order.id}",
            product_name=item.product.name,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price,
            size=item.size,
            shipping_address=f"{order.shipping_address.address_line1}, {order.shipping_address.city}" if order.shipping_address else "N/A",
            customer_name=order.customer.full_name or order.customer.email,
            customer_phone=order.customer.phone,
            status=item.status,
            payment_status=item.payment_status,
            payment_method=order.payment_method or "COD",
            total_amount=float(item.price * item.quantity),
            delivery_attempts=item.delivery_attempts or 0,
            color=getattr(item.product, 'color', None) if item.product else None,
            product_image=item.product.images[0] if (item.product and item.product.images) else None,
            rider_payment_method=item.rider_payment_method
        ))
    
    return response

@router.put("/tasks/{item_id}/status")
async def update_task_status(
    item_id: int,
    status: OrderStatus = Query(...),
    rider_payment_method: Optional[str] = Query(None, description="Payment method rider used to collect: online, cash, upi"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    print(f"DEBUG: update_task_status - Item ID: {item_id}, Status: {status}")
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        print(f"DEBUG: Auth failure - User is not a rider (Role: {current_user.role})")
        raise HTTPException(status_code=403, detail="Not authorized as a delivery partner")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    
    if not rider:
        print(f"DEBUG: Rider profile not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(OrderItem)
        .where(OrderItem.id == item_id, OrderItem.rider_id == rider.id)
        .options(selectinload(OrderItem.product))
    )
    item = result.scalar_one_or_none()
    if not item:
        print(f"DEBUG: Task {item_id} not found or not assigned to rider {rider.id}")
        raise HTTPException(status_code=404, detail="Task not assigned to you")
    
    new_status_str = str(status.value).lower()
    old_status_str = (item.status or "").lower()
    print(f"DEBUG: Item {item_id} changing from {old_status_str} to {new_status_str}, payment_method={rider_payment_method}")
    
    # Check if already delivered to avoid double earnings
    already_delivered = (old_status_str == "delivered")

    if new_status_str == "undelivered":
        # Increment delivery attempts
        item.delivery_attempts = (item.delivery_attempts or 0) + 1
        if item.delivery_attempts >= 3:
            print(f"DEBUG: Max delivery attempts (3) reached for {item_id}. Auto-returning item.")
            new_status_str = "returned"
            
            # Since we are returning the item directly due to max attempts (no dealer approval needed)
            # We can optionally restore product stock here, matching dealer logic
            if item.product:
                item.product.stock += item.quantity
    elif new_status_str == "delivered":
        # Reset delivery attempts if successfully delivered
        item.delivery_attempts = 0

    item.status = new_status_str
    
    # Persist the rider's payment method if provided
    if rider_payment_method:
        item.rider_payment_method = rider_payment_method.lower()
    
    if new_status_str == "delivered":
        item.delivered_at = datetime.now(timezone.utc)
        item.payment_status = "paid"
        
        if not already_delivered:
            print(f"DEBUG: Processing earnings for rider {rider.id}")
            from models import RiderEarning
            earning = RiderEarning(
                rider_id=rider.id, order_item_id=item.id, amount=40.0,
                type="delivery", description=f"Delivery of item {item.id}"
            )
            db.add(earning)
            rider.current_balance += 40.0
            rider.total_earnings += 40.0

    order_id = item.order_id
    item_id_val = item.id
    
    from core.order_status_logic import calculate_and_update_order_status

    # Flush changes to the session so subsequent queries see the new status (since autoflush=False)
    await db.flush()

    # TRIGGER PARENT ORDER SYNC (Using shared logic)
    try:
        await calculate_and_update_order_status(db, order_id)
        # Re-fetch parent order for notification context if needed
        order_res = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        parent_order = order_res.scalar_one_or_none()

        # 2. Trigger Notification (Before final commit for consistency)
        if parent_order:
            try:
                from services.notification import AppNotificationService
                await AppNotificationService.notify_order_status(
                    db, customer_id=parent_order.customer_id, status=new_status_str,
                    order_number=parent_order.order_number or f"ORD-{parent_order.id}",
                    data={"order_id": parent_order.id, "item_id": item_id_val}
                )
            except Exception as e:
                print(f"DEBUG: Notification error: {e}")

        # Final commit for everything (item status + rider earnings + parent order + notification log)
        await db.commit()
        print(f"DEBUG: Final commit successful for Order {order_id}")

    except Exception as e:
        await db.rollback()
        print(f"DEBUG: Critical error in update_task_status: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")

    return {"message": f"Successfully updated to {new_status_str}"}

from schemas.rider import RiderEarningSchema

@router.get("/earnings", response_model=List[RiderEarningSchema])
async def get_rider_earnings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """View earning history for the current rider."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    
    from models import RiderEarning
    result = await db.execute(
        select(RiderEarning)
        .where(RiderEarning.rider_id == rider.id)
        .order_by(RiderEarning.created_at.desc())
    )
    return result.scalars().all()

@router.get("/returns", response_model=List[RiderReturnTask])
async def get_rider_return_tasks(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all return pickup tasks assigned to the current rider."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    from sqlalchemy.orm import selectinload
    
    # query returns assigned to this rider that are not yet completed/rejected
    query = (
        select(OrderReturn)
        .options(
            selectinload(OrderReturn.order).selectinload(Order.shipping_address),
            selectinload(OrderReturn.order).selectinload(Order.customer),
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product),
            selectinload(OrderReturn.exchange_variant)
        )
        .where(OrderReturn.rider_id == rider.id)
        .where(OrderReturn.status.notin_([
            ReturnStatus.COMPLETED,
            ReturnStatus.REJECTED
        ]))
    )
    
    result = await db.execute(query)
    returns = result.scalars().all()
    print(f"DEBUG: Found {len(returns)} pending return tasks for rider {rider.id}")
    for r in returns:
        print(f"  - Return {r.id}: status={r.status}")
    
    response = []
    for ret in returns:
        order = ret.order
        # For pickup address, we usually use the same shipping address where it was delivered
        addr = "N/A"
        if order.shipping_address:
            addr = f"{order.shipping_address.address_line1}, {order.shipping_address.city}"
            
        product_name = "Unknown Product"
        quantity = 0
        product_image = None
        size = None
        color = None
        
        if ret.order_item:
            if ret.order_item.product:
                product_name = ret.order_item.product.name
                product_image = ret.order_item.product.images[0] if ret.order_item.product.images else None
            
            quantity = ret.order_item.quantity
            size = ret.order_item.size
            # For color, we might look at Product if not on Item directly
            color = getattr(ret.order_item.product, 'color', None) if ret.order_item.product else None

        payment_method = order.payment_method or "COD"
        # Calculated refund amount = price * quantity
        refund_amount = float(ret.order_item.price * ret.order_item.quantity) if ret.order_item else 0.0

        response.append(RiderReturnTask(
            id=ret.id, # Using return ID
            return_id=ret.id,
            order_number=order.order_number or f"ORD-{order.id}",
            product_name=product_name,
            product_id=ret.order_item.product_id if ret.order_item else 0,
            quantity=quantity,
            product_image=product_image,
            size=size,
            color=color,
            pickup_address=addr,
            customer_name=order.customer.full_name or order.customer.email,
            customer_phone=order.customer.phone,
            status=ret.status.value.lower(),
            reason=ret.reason or "No reason provided",
            is_exchange=ret.is_exchange or False,
            exchange_size=ret.exchange_variant.size if ret.exchange_variant else None,
            exchange_color=ret.exchange_variant.color if ret.exchange_variant else None,
            pickup_attempts=ret.pickup_attempts or 0,
            pickup_date=ret.pickup_date,
            created_at=ret.requested_at,
            payment_method=payment_method,
            refund_amount=refund_amount,
            extra_amount_to_collect=ret.extra_amount_to_collect or 0.0,
            logistics_partner_id=ret.order_item.logistics_partner_id if ret.order_item else None
        ))
    
    return response

@router.put("/returns/{return_id}/status")
async def update_return_pickup_status(
    return_id: int,
    status: str = Query(...),
    payment_collected: bool = Query(False, description="Flag for rider to confirm if exchange payment was collected"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update status for a return pickup task."""
    role_str = str(current_user.role.value if hasattr(current_user.role, 'value') else current_user.role).lower()
    if role_str not in RIDER_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.user_id == current_user.id))
    rider = rider_result.scalar_one_or_none()
    
    if not rider:
        raise HTTPException(status_code=404, detail="Rider profile not found")
    
    result = await db.execute(
        select(OrderReturn)
        .where(OrderReturn.id == return_id, OrderReturn.rider_id == rider.id)
        .options(
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product),
            selectinload(OrderReturn.order).selectinload(Order.customer),
            selectinload(OrderReturn.order).selectinload(Order.shipping_address)
        )
    )
    order_return = result.scalar_one_or_none()
    
    if not order_return:
        print(f"DEBUG: Return task {return_id} not found or not assigned to rider {rider.id}")
        raise HTTPException(status_code=404, detail="Return task not found or not assigned to you")
    
    try:
        # 1. Robust status mapping with normalization
        status_map = {
            "out_for_pickup": ReturnStatus.OUT_FOR_PICKUP,
            "out-for-pickup": ReturnStatus.OUT_FOR_PICKUP,
            "out for pickup": ReturnStatus.OUT_FOR_PICKUP,
            "out_for_swap": ReturnStatus.OUT_FOR_SWAP,
            "out-for-swap": ReturnStatus.OUT_FOR_SWAP,
            "out for swap": ReturnStatus.OUT_FOR_SWAP,
            "picked_up": ReturnStatus.PICKED_UP,
            "picked-up": ReturnStatus.PICKED_UP,
            "picked up": ReturnStatus.PICKED_UP,
            "swap_completed": ReturnStatus.SWAP_COMPLETED,
            "swap-completed": ReturnStatus.SWAP_COMPLETED,
            "swap completed": ReturnStatus.SWAP_COMPLETED,
            "pickup_failed": "pickup_failed", # Special marker
            "pickup-failed": "pickup_failed",
            "pickup failed": "pickup_failed",
        }
        
        lookup_key = status.strip().lower()
        if lookup_key not in status_map:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
            
        new_status = status_map[lookup_key]
        
        # Auto-translate for exchanges
        if new_status == ReturnStatus.OUT_FOR_PICKUP and order_return.is_exchange:
            new_status = ReturnStatus.OUT_FOR_SWAP
            
        new_status_str = new_status.value if hasattr(new_status, 'value') else new_status
        old_status = order_return.status

        # 2. Update Statuses
        if new_status == "pickup_failed":
            order_return.pickup_attempts = (order_return.pickup_attempts or 0) + 1
            order_return.status = ReturnStatus.PICKUP_FAILED
            if order_return.order_item:
                order_return.order_item.status = "pickup_failed"
            new_status = ReturnStatus.PICKUP_FAILED 
        else:
            order_return.status = new_status
        
        if order_return.order_item:
            if new_status in [ReturnStatus.OUT_FOR_PICKUP, ReturnStatus.OUT_FOR_SWAP]:
                order_return.order_item.status = "out_for_pickup"
            elif new_status == ReturnStatus.PICKED_UP:
                order_return.order_item.status = "picked_up"
            elif new_status == ReturnStatus.SWAP_COMPLETED:
                order_return.order_item.status = "exchanged"
                # Record payment collection
                if order_return.extra_amount_to_collect > 0:
                    if payment_collected:
                        order_return.refund_initiated = True # Flag as payment recorded
                        order_return.admin_notes = (order_return.admin_notes or "") + f"\n[Payment] Extra amount ₹{order_return.extra_amount_to_collect} collected by rider {rider.id}."
                    else:
                        # Should have been collected but wasn't? Maybe throw error or just log
                        order_return.admin_notes = (order_return.admin_notes or "") + f"\n[Payment] Extra amount ₹{order_return.extra_amount_to_collect} NOT confirmed by rider."

        # Extract IDs before objects expire
        order_id = order_return.order_id
        customer_id = order_return.customer_id
        order_number = order_return.order.order_number or f"ORD-{order_id}"
        
        # Trigger Notification
        try:
            from services.notification import AppNotificationService
            if hasattr(AppNotificationService, 'notify_return_status'):
                await AppNotificationService.notify_return_status(
                    db, customer_id=customer_id, order_number=order_number, 
                    status=new_status_str, data={"return_id": return_id, "order_id": order_id}
                )
        except Exception as e:
            print(f"DEBUG: Notification error: {e}")

        # Single final commit for consistency
        await db.commit()
        print(f"DEBUG: Status transition committed successfully for Return {return_id}")

    except Exception as e:
        await db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
    return {"message": f"Return marked as {status.replace('_', ' ')}", "status": status.lower()}

