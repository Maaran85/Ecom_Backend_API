"""
Order Management Router - Cancellation, Returns, Tracking
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
from typing import Optional
import csv
import io
from fastapi.responses import StreamingResponse

from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Order, OrderItem, OrderReturn, Product, Category, CategoryAttribute, Dealer, CartItem, Coupon, CouponUsage, Payment, ProductVariant
from models.cart import OrderStatus
from models.order_return import ReturnStatus
from models.payment import PaymentStatus
from schemas.order_management import (
    OrderCancelRequest, OrderCancelResponse,
    ReturnRequest, ReturnResponse, ReturnApprovalRequest, ReturnRejectionRequest,
    OrderReturn as OrderReturnSchema,
    AdminReturnDetail, ProcessRefundRequest,
    TrackingUpdateRequest, TrackingUpdateResponse
)

router = APIRouter()

# ==================== ORDER CANCELLATION ====================

@router.post("/orders/{order_id}/cancel", response_model=OrderCancelResponse)
async def cancel_order(
    order_id: int,
    cancel_data: OrderCancelRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel an order (only if PENDING or CONFIRMED)"""
    
    # Get order
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.customer_id == current_user.id
        ).options(
            selectinload(Order.items),
            selectinload(Order.payment)
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # If already cancelled, return success with info
    if order.status == OrderStatus.CANCELLED:
        return OrderCancelResponse(
            order_id=order.id,
            status=order.status.value,
            message="Order is already cancelled",
            refund_initiated=(order.payment.status == PaymentStatus.REFUNDED) if order.payment else False
        )

    # Check if order can be cancelled (Allow until it is SHIPPED)
    allowed_statuses = [
        OrderStatus.PENDING, 
        OrderStatus.ORDER_PLACED,
        OrderStatus.CONFIRMED, 
        OrderStatus.PROCESSING, 
        OrderStatus.PACKAGING,
        OrderStatus.PACKED
    ]
    if order.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel order with status: {order.status.value}. Order has already been shipped or completed."
        )
    
    # Update order status
    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = cancel_data.reason
    order.cancelled_at = datetime.now(timezone.utc)
    
    # Sync item statuses for dealers
    for item in order.items:
        item.status = OrderStatus.CANCELLED.value
    
    # Restore product stock (from order items)
    for item in order.items:
        product_result = await db.execute(select(Product).where(Product.id == item.product_id))
        product = product_result.scalar_one_or_none()
        if product:
            product.stock += item.quantity
    
    # Reverse coupon usage if applicable
    if order.coupon_id:
        coupon_result = await db.execute(select(Coupon).where(Coupon.id == order.coupon_id))
        coupon = coupon_result.scalar_one_or_none()
        if coupon and coupon.current_usage > 0:
            coupon.current_usage -= 1
        
        # Delete coupon usage record
        usage_result = await db.execute(
            select(CouponUsage).where(
                CouponUsage.order_id == order_id,
                CouponUsage.customer_id == current_user.id
            )
        )
        usage = usage_result.scalar_one_or_none()
        if usage:
            await db.delete(usage)
    
    # Initiate refund if payment was successful
    refund_initiated = False
    if order.payment and order.payment.status == PaymentStatus.SUCCESS:
        # In a real system, this would call payment gateway refund API
        # For mock, we'll just update the payment status
        order.payment.status = PaymentStatus.REFUNDED
        order.payment.refund_amount = order.payment.amount
        order.payment.refund_reason = f"Order cancelled: {cancel_data.reason}"
        order.payment.refunded_at = datetime.now(timezone.utc)
        refund_initiated = True
    
    await db.commit()
    await db.refresh(order)
    
    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_order_status(
            db,
            customer_id=order.customer_id,
            order_number=order.order_number or f"ORD-{order.id}",
            status="cancelled",
            data={"order_id": order.id}
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending cancellation notification: {e}")

    return OrderCancelResponse(
        order_id=order.id,
        status=order.status.value,
        message="Order cancelled successfully",
        refund_initiated=refund_initiated
    )

# ==================== ORDER RETURNS ====================

@router.post("/orders/{order_id}/return", response_model=ReturnResponse, status_code=status.HTTP_201_CREATED)
async def request_return(
    order_id: int,
    return_data: ReturnRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Request return for a delivered order"""
    
    # Get order
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.customer_id == current_user.id
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Check if order is delivered
    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only return delivered orders"
        )
    
    # Check if a return request already exists for this specific item
    existing_return_result = await db.execute(
        select(OrderReturn).where(
            OrderReturn.order_id == order_id,
            OrderReturn.order_item_id == return_data.order_item_id
        )
    )
    if existing_return_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return request already exists for this item"
        )

    # Verify item belongs to this order
    item_result = await db.execute(
        select(OrderItem).where(OrderItem.id == return_data.order_item_id, OrderItem.order_id == order_id)
    )
    order_item = item_result.scalar_one_or_none()
    if not order_item:
        raise HTTPException(status_code=400, detail="Specified item does not belong to this order")
    
    # Check return window (e.g., 7 days from delivery)
    if order.delivered_at:
        days_since_delivery = (datetime.now(timezone.utc) - order.delivered_at).days
        if days_since_delivery > 7:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Return window (7 days) has expired"
            )
    
    # Create return or exchange request
    # Handle virtual variants (negative IDs) by storing None in DB while keeping is_exchange=True
    actual_variant_id = return_data.exchange_variant_id
    if actual_variant_id is not None and actual_variant_id <= 0:
        actual_variant_id = None

    order_return = OrderReturn(
        order_id=order_id,
        order_item_id=return_data.order_item_id,
        customer_id=current_user.id,
        reason=return_data.reason,
        description=return_data.description,
        images=return_data.images,
        is_exchange=return_data.is_exchange,
        exchange_variant_id=actual_variant_id,
        pickup_date=return_data.pickup_date,
        status=ReturnStatus.REQUESTED,
        hub_id=order_item.hub_id,
        logistics_partner_id=order_item.logistics_partner_id
    )
    
    db.add(order_return)
    await db.commit()
    await db.refresh(order_return)
    
    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_return_status(
            db,
            customer_id=order_return.customer_id,
            order_number=order.order_number if order else f"ORD-{order_return.order_id}",
            status="requested",
            data={"order_id": order_return.order_id, "return_id": order_return.id}
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending return approval notification: {e}")
    
    return ReturnResponse(
        id=order_return.id,
        order_id=order_return.order_id,
        order_item_id=order_return.order_item_id,
        reason=order_return.reason,
        status=order_return.status,
        requested_at=order_return.requested_at,
        message="Return request submitted successfully. Admin will review shortly."
    )

@router.get("/orders/returns", response_model=list[OrderReturnSchema])
async def get_my_returns(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's return requests"""
    
    result = await db.execute(
        select(OrderReturn).where(
            OrderReturn.customer_id == current_user.id
        ).offset(skip).limit(limit)
    )
    returns = result.scalars().all()
    
    return returns

@router.get("/admin/returns", response_model=list[AdminReturnDetail])
async def get_all_returns(
    status_filter: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all return requests with enriched info (admin only)"""
    from models import Payment
    from models.payment import PaymentMethod
    
    query = (
        select(OrderReturn)
        .options(
            selectinload(OrderReturn.order).selectinload(Order.customer),
            selectinload(OrderReturn.order).selectinload(Order.payment),
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product),
        )
        .order_by(OrderReturn.requested_at.desc())
    )
    
    if status_filter:
        try:
            query = query.where(OrderReturn.status == ReturnStatus(status_filter.upper()))
        except ValueError:
            pass  # Ignore invalid status filters
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    returns = result.scalars().all()
    
    enriched = []
    for r in returns:
        order = r.order
        customer = order.customer if order else None
        payment = order.payment if order else None
        item = r.order_item
        product = item.product if item else None
        
        # Determine payment method string
        pm = None
        if payment and payment.payment_method:
            pm = payment.payment_method.value if hasattr(payment.payment_method, 'value') else str(payment.payment_method)
        elif order and order.payment_method:
            pm = order.payment_method
        
        enriched.append(AdminReturnDetail(
            id=r.id,
            order_id=r.order_id,
            order_number=order.order_number if order else None,
            order_item_id=r.order_item_id,
            customer_id=r.customer_id,
            customer_name=customer.full_name if customer else None,
            customer_phone=customer.phone if customer else None,
            product_name=product.name if product else None,
            reason=r.reason,
            description=r.description,
            images=r.images,
            is_exchange=r.is_exchange,
            status=r.status,
            admin_notes=r.admin_notes,
            approved_by=r.approved_by,
            refund_amount=r.refund_amount,
            refund_initiated=r.refund_initiated,
            refund_mode=r.refund_mode,
            refund_reference=r.refund_reference,
            payment_method=pm,
            requested_at=r.requested_at,
            approved_at=r.approved_at,
            completed_at=r.completed_at,
        ))
    
    return enriched

@router.post("/admin/returns/{return_id}/approve", response_model=OrderReturnSchema)
async def approve_return(
    return_id: int,
    approval_data: ReturnApprovalRequest,
    current_user: User = Depends(get_current_active_user), # Changed from require_admin to allow both
    db: AsyncSession = Depends(get_db)
):
    """Approve return request and initiate refund for UPI/online orders.
    
    - COD orders: marks approved, no refund initiated (customer keeps cash).
    - UPI/Online orders: marks approved, records refund mode & reference if provided,
      sets Payment.status = REFUNDED.
    - Dealers can only approve returns for their own products.
    """
    from models import Payment, UserRole
    
    # Permission check: Admin or Dealer
    if current_user.role not in [UserRole.ADMIN, UserRole.DEALER]:
        raise HTTPException(status_code=403, detail="Only Admins or Dealers can approve returns")

    result = await db.execute(
        select(OrderReturn)
        .options(
            selectinload(OrderReturn.order).selectinload(Order.payment),
            selectinload(OrderReturn.order_item).selectinload(OrderItem.product)
        )
        .where(OrderReturn.id == return_id)
    )
    order_return = result.scalar_one_or_none()
    
    if not order_return:
        raise HTTPException(status_code=404, detail="Return request not found")

    # Dealer specific check
    if current_user.role == UserRole.DEALER:
        if not order_return.order_item or not order_return.order_item.product or order_return.order_item.product.dealer_id != current_user.id:
             raise HTTPException(status_code=403, detail="Not authorized to approve returns for products from other dealers")
    
    if not order_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found"
        )
    
    if order_return.status != ReturnStatus.REQUESTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve return with status: {order_return.status.value}"
        )
    
    # Update return status
    order_return.status = ReturnStatus.APPROVED
    order_return.approved_by = current_user.id
    order_return.approved_at = datetime.now(timezone.utc)
    order_return.admin_notes = approval_data.admin_notes
    
    order = order_return.order
    
    if order:
        # Determine refund amount (use item-level price if available)
        if approval_data.refund_amount:
            refund_amount = approval_data.refund_amount
        elif order_return.order_item_id:
            # Try to use item-level price
            item_res = await db.execute(
                select(OrderItem).where(OrderItem.id == order_return.order_item_id)
            )
            item = item_res.scalar_one_or_none()
            refund_amount = round(item.price * item.quantity, 2) if item else order.total_amount
        else:
            refund_amount = order.total_amount
        
        order_return.refund_amount = refund_amount
        
        # Determine payment method
        payment = order.payment
        payment_method_str = ""
        if payment and payment.payment_method:
            payment_method_str = (
                payment.payment_method.value
                if hasattr(payment.payment_method, "value")
                else str(payment.payment_method)
            )
        elif order.payment_method:
            payment_method_str = str(order.payment_method).lower()
        
        # Robust check: If we have a successful payment ID, it's likely online (card/upi/net-banking)
        # Even if the method string is empty or missing.
        has_success_payment = payment and payment.status in (PaymentStatus.SUCCESS, PaymentStatus.CAPTURED)
        
        # Any non-COD order with a successful payment is considered ONLINE (requires UTR record)
        is_online_payment = (
            payment_method_str.lower() not in ("cod", "cash_on_delivery", "cash")
            or (has_success_payment and payment_method_str.lower() == "")
        )
        # Final safety: If it's truly empty AND no payment record, treat as COD as fallback
        if not payment_method_str and not has_success_payment:
            is_online_payment = False
        
        if is_online_payment:
            # --- Online / UPI / Card / Net-banking refund ---
            order_return.refund_mode = approval_data.refund_mode or "original_method"
            order_return.refund_reference = approval_data.refund_reference  # Optional at approval
            
            if approval_data.refund_reference:
                # Reference provided immediately — mark as fully initiated
                order_return.refund_initiated = True
                if payment and payment.status == PaymentStatus.SUCCESS:
                    payment.status = PaymentStatus.REFUNDED
                    payment.refund_amount = refund_amount
                    payment.refund_reason = f"Return approved: {order_return.reason}"
                    payment.refunded_at = datetime.now(timezone.utc)
            else:
                # Reference will be provided later via /process-refund
                order_return.refund_initiated = False
        else:
            # --- COD order: no refund needed ---
            order_return.refund_mode = "none"
            order_return.refund_initiated = False
            order_return.refund_amount = 0.0
        
        # Update order status to RETURNED
        order.status = OrderStatus.RETURNED

        # --- EXCHANGE LOGIC ---
        if order_return.is_exchange:
            from models.cart import OrderStatus as CartOrderStatus
            import random
            import string

            # 1. Verify Stock for replacement variant OR base product
            variant = None
            product = None
            
            if order_return.exchange_variant_id and order_return.exchange_variant_id > 0:
                var_res = await db.execute(
                    select(ProductVariant).where(ProductVariant.id == order_return.exchange_variant_id)
                )
                variant = var_res.scalar_one_or_none()
                if variant:
                    prod_res = await db.execute(select(Product).where(Product.id == variant.product_id))
                    product = prod_res.scalar_one_or_none()
            else:
                # Base Product Exchange (None or <= 0)
                oi_res = await db.execute(
                    select(OrderItem).options(selectinload(OrderItem.product))
                    .where(OrderItem.id == order_return.order_item_id)
                )
                oi = oi_res.scalar_one_or_none()
                if oi:
                    product = oi.product
            
            # Use product price as fallback if variant missing or base product exchange
            exchange_price = (variant.price_adjustment + product.price) if (variant and product) else (product.price if product else 0.0)
            exchange_stock = variant.stock if variant else (product.stock if product else 0)
            
            # Calculate extra amount to collect if new item is more expensive
            original_item_price = order_return.order_item.price if order_return.order_item else 0.0
            if exchange_price > original_item_price:
                order_return.extra_amount_to_collect = round(exchange_price - original_item_price, 2)
            else:
                order_return.extra_amount_to_collect = 0.0

            # 2. Create Replacement Order
            new_order_no = "EXC-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            replacement_order = Order(
                order_number=new_order_no,
                customer_id=order.customer_id,
                shipping_address_id=order.shipping_address_id,
                subtotal=exchange_price,
                total_amount=0.0, # Even exchange
                delivery_charge=0.0,
                status=CartOrderStatus.CONFIRMED, # Auto-confirm for exchange
                payment_method="Exchange",
                payment_status="success",
                created_at=datetime.now(timezone.utc)
            )
            db.add(replacement_order)
            await db.flush() # Get replacement_order.id
            
            # 3. Create Replacement Order Item
            new_item = OrderItem(
                order_id=replacement_order.id,
                product_id=product.id if product else (variant.product_id if variant else order_return.order_item.product_id),
                variant_id=order_return.exchange_variant_id if (order_return.exchange_variant_id and order_return.exchange_variant_id > 0) else None,
                quantity=1,
                price=exchange_price,
                status="packaging",
                item_order_id=f"{new_order_no}-1"
            )
            db.add(new_item)
            
            # 4. Link replacement to return record
            order_return.replacement_order_id = replacement_order.id
            
            # 5. Deduct stock
            if variant and variant.stock > 0:
                variant.stock -= 1
            elif product and product.stock > 0 and not variant:
                product.stock -= 1
    
    await db.commit()
    await db.refresh(order_return)
    
    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_return_status(
            db,
            customer_id=order_return.customer_id,
            order_number=order.order_number if order else f"ORD-{order_return.order_id}",
            status="approved",
            data={"order_id": order_return.order_id, "return_id": order_return.id}
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending return approval notification: {e}")
    
    return order_return


@router.put("/admin/returns/{return_id}/process-refund", response_model=OrderReturnSchema)
async def process_return_refund(
    return_id: int,
    refund_data: ProcessRefundRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Record refund details (UTR/reference) after the refund has been sent to the customer.
    
    Use this after the return is approved and the item has been picked up,
    once the admin has sent the refund via UPI/NEFT/bank and has the UTR number.
    Marks the refund as fully initiated and updates Payment status to REFUNDED.
    """
    from models import Payment
    
    result = await db.execute(
        select(OrderReturn)
        .options(
            selectinload(OrderReturn.order).selectinload(Order.payment)
        )
        .where(OrderReturn.id == return_id)
    )
    order_return = result.scalar_one_or_none()
    
    if not order_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found"
        )
    
    allowed_statuses = [
        ReturnStatus.APPROVED, ReturnStatus.PICKED_UP,
        ReturnStatus.RETURN_PICKUP_COMPLETED,
        ReturnStatus.COMPLETED
    ]
    if order_return.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Return must be approved or further along to process refund. Current status: {order_return.status.value}"
        )
    
    # Record info if it was an online refund
    if refund_data.refund_mode:
        order_return.refund_mode = refund_data.refund_mode
    if refund_data.refund_reference:
        order_return.refund_reference = refund_data.refund_reference
    
    order_return.refund_initiated = True
    order_return.status = ReturnStatus.REFUNDED
    order_return.completed_at = datetime.now(timezone.utc)
    
    if refund_data.refund_amount is not None:
        order_return.refund_amount = refund_data.refund_amount
    
    # Update Payment record if it's an online payment
    order = order_return.order
    if order and order.payment and order_return.refund_mode != "none":
        payment = order.payment
        if payment.status in (PaymentStatus.SUCCESS, PaymentStatus.PROCESSING):
            payment.status = PaymentStatus.REFUNDED
        payment.refund_amount = order_return.refund_amount or 0.0
        payment.refund_reason = (
            f"Return #{return_id} finalized via {order_return.refund_mode}. "
            f"Ref: {order_return.refund_reference or 'N/A'}"
        )
        payment.refunded_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(order_return)
    
    return order_return

@router.post("/admin/returns/{return_id}/reject", response_model=OrderReturnSchema)
async def reject_return(
    return_id: int,
    rejection_data: ReturnRejectionRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject return request (admin only)"""
    
    result = await db.execute(select(OrderReturn).where(OrderReturn.id == return_id))
    order_return = result.scalar_one_or_none()
    
    if not order_return:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Return request not found"
        )
    
    if order_return.status != ReturnStatus.REQUESTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject return with status: {order_return.status.value}"
        )
    
    # Update return status
    order_return.status = ReturnStatus.REJECTED
    order_return.approved_by = current_user.id
    order_return.admin_notes = rejection_data.admin_notes
    
    await db.commit()
    await db.refresh(order_return)
    
    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        from models import Order
        order_res = await db.execute(select(Order.order_number).where(Order.id == order_return.order_id))
        order_no = order_res.scalar_one_or_none()
        
        await AppNotificationService.notify_return_status(
            db,
            customer_id=order_return.customer_id,
            order_number=order_no if order_no else f"ORD-{order_return.order_id}",
            status="rejected",
            data={"order_id": order_return.order_id, "return_id": order_return.id}
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending return rejection notification: {e}")
    
    return order_return

# ==================== TRACKING UPDATES ====================

@router.put("/admin/orders/{order_id}/tracking", response_model=TrackingUpdateResponse)
async def update_tracking(
    order_id: int,
    tracking_data: TrackingUpdateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update order tracking information (admin only)"""
    
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.payment),
            selectinload(Order.items)
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Update tracking number
    if tracking_data.tracking_number:
        order.tracking_number = tracking_data.tracking_number
    
    # Update status
    if tracking_data.status:
        try:
            order.status = OrderStatus(tracking_data.status)
            
            # Auto-set delivered_at and payment status if status is DELIVERED
            if order.status == OrderStatus.DELIVERED:
                if not order.delivered_at:
                    order.delivered_at = datetime.now(timezone.utc)
                if order.payment:
                    order.payment.status = PaymentStatus.SUCCESS
                    order.payment.completed_at = datetime.now(timezone.utc)
                for item in order.items:
                    item.status = "delivered"
                    item.payment_status = "paid"
                    if not item.delivered_at:
                        item.delivered_at = datetime.now(timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order status: {tracking_data.status}"
            )
    
    # Update estimated delivery
    if tracking_data.estimated_delivery:
        order.estimated_delivery = tracking_data.estimated_delivery
    
    await db.commit()
    await db.refresh(order)
    
    # TRIGGER NOTIFICATION
    try:
        from services.notification import AppNotificationService
        await AppNotificationService.notify_order_status(
            db,
            customer_id=order.customer_id,
            order_number=order.order_number or f"ORD-{order.id}",
            status=order.status.value,
            data={"order_id": order.id, "tracking_number": order.tracking_number}
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending tracking notification: {e}")
    
    return TrackingUpdateResponse(
        order_id=order.id,
        tracking_number=order.tracking_number,
        status=order.status.value,
        estimated_delivery=order.estimated_delivery,
        message="Tracking information updated successfully"
    )

# ==================== ORDER HISTORY WITH FILTERS ====================

@router.get("/orders/history", response_model=list)
async def get_order_history(
    status_filter: Optional[str] = None,
    payment_status: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order history with filters"""
    
    query = select(Order).where(Order.customer_id == current_user.id).options(
        selectinload(Order.items).joinedload(OrderItem.product).options(
            joinedload(Product.dealer),
            selectinload(Product.category).selectinload(Category.attributes)
        ),
        selectinload(Order.items).joinedload(OrderItem.hub),
        selectinload(Order.returns).selectinload(OrderReturn.exchange_variant),
        selectinload(Order.shipping_address),
        selectinload(Order.payment)
    )
    
    # Status filter
    if status_filter:
        try:
            query = query.where(Order.status == OrderStatus(status_filter))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}"
            )
    
    # Payment status filter (removed since payment_status is on items now, or order.payment)
    # If we need to filter by payment status, we'd join order.payment
    if payment_status:
        from models import Payment
        query = query.join(Payment).where(Payment.status == payment_status)
    
    # Date range filter
    if from_date:
        query = query.where(Order.created_at >= from_date)
    if to_date:
        query = query.where(Order.created_at <= to_date)
    
    # Pagination
    query = query.offset(skip).limit(limit).order_by(Order.created_at.desc())
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    from schemas.cart import Order as OrderSchema
    
    response_list = []
    for o in orders:
        if hasattr(OrderSchema, 'model_validate'):
            o_dict = OrderSchema.model_validate(o).model_dump()
        else:
            o_dict = OrderSchema.from_orm(o).dict()
            
        addr_str = "Home Address"
        if o.shipping_address:
            addr = o.shipping_address
            street = getattr(addr, 'address_line1', getattr(addr, 'street_address', ''))
            city = getattr(addr, 'city', '')
            state = getattr(addr, 'state', '')
            zip_code = getattr(addr, 'pincode', getattr(addr, 'postal_code', ''))
            parts = [p for p in [street, city, state, zip_code] if p]
            if parts:
                addr_str = ", ".join(parts[:3]) + (f" - {zip_code}" if zip_code else "")
        
        o_dict["shipping_address"] = addr_str
        response_list.append(o_dict)
    
    return response_list

@router.get("/admin/orders/export", tags=["admin"])
async def export_orders_csv(
    status_filter: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Export orders to CSV (admin only).
    """
    # Build query with eager loading of items
    query = select(Order).options(selectinload(Order.items), selectinload(Order.payment)).order_by(Order.created_at.desc())
    
    if status_filter:
        try:
            query = query.where(Order.status == OrderStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_filter}")
            
    if from_date:
        query = query.where(Order.created_at >= from_date)
    if to_date:
        query = query.where(Order.created_at <= to_date)
        
    # Execute query
    result = await db.execute(query)
    orders = result.scalars().all()
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Order ID", "User ID", "Date", "Status", 
        "Total Amount", "Payment Status", "Tracking Number", 
        "Items Count", "Items Summary"
    ])
    
    # Write rows
    for order in orders:
        # Fetch items for summary (need simple string repr)
        # Note: In async usage, ensure items are loaded. 
        # If lazy loading is issue, might need eager load in query.
        # Assuming eager load or session availability:
        items_summary = []
        for item in order.items:
             # Ideally fetch product name, but might require extra queries if not joined.
             # For performance, we should have used select details.
             # MVP: Just ID and Qty if product not loaded, or try to access.
             items_summary.append(f"Prod:{item.product_id} x{item.quantity}")
             
        writer.writerow([
            order.id,
            order.customer_id,
            order.created_at.isoformat() if order.created_at else "",
            order.status.value,
            order.total_amount,
            order.payment.status.value if order.payment else "pending",
            order.tracking_number or "",
            len(order.items),
            "; ".join(items_summary)
        ])
        
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders_export.csv"}
    )
