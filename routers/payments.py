"""
Mock Payment Integration Router
Simulates payment gateway for testing and development
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
import uuid
import random

from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, CustomerUser, Order, Payment, PaymentWebhook, Product, CartItem, Coupon, CouponUsage
from models.payment import PaymentMethod, PaymentStatus
from models.cart import OrderStatus
from schemas.payment import (
    PaymentInitiateRequest,
    PaymentResponse,
    PaymentStatusResponse,
    PaymentConfirmRequest,
    PaymentRefundRequest,
    PaymentRefundResponse,
    Payment as PaymentSchema,
    PaymentStats,
    RazorpayOrderResponse,
    RazorpayVerifyRequest
)

router = APIRouter()

# Mock test cards for simulation
MOCK_CARDS = {
    "4111111111111111": {"brand": "Visa", "result": "success"},
    "4000000000000002": {"brand": "Visa", "result": "declined"},
    "4000000000000069": {"brand": "Visa", "result": "expired"},
    "4000000000000127": {"brand": "Visa", "result": "incorrect_cvv"},
    "5555555555554444": {"brand": "Mastercard", "result": "success"},
    "378282246310005": {"brand": "Amex", "result": "success"},
}

# Mock UPI IDs
MOCK_UPI = {
    "success@upi": "success",
    "failure@upi": "failed",
    "pending@upi": "pending",
}

def generate_transaction_id():
    """Generate mock transaction ID"""
    return f"TXN{uuid.uuid4().hex[:12].upper()}"

def get_card_brand(card_number: str) -> str:
    """Determine card brand from card number"""
    if card_number in MOCK_CARDS:
        return MOCK_CARDS[card_number]["brand"]
    
    first_digit = card_number[0]
    if first_digit == "4":
        return "Visa"
    elif first_digit == "5":
        return "Mastercard"
    elif first_digit == "3":
        return "Amex"
    return "Unknown"

@router.post("/initiate", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def initiate_payment(
    payment_data: PaymentInitiateRequest,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate payment for an order"""
    
    # Get order
    result = await db.execute(
        select(Order).where(
            Order.id == payment_data.order_id,
            Order.customer_id == current_user.id
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Check if order is in pending status
    if order.status != OrderStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is already {order.status.value}. Cannot initiate payment."
        )
    
    # Check if payment already exists
    existing_payment_result = await db.execute(
        select(Payment).where(Payment.order_id == order.id)
    )
    existing_payment = existing_payment_result.scalar_one_or_none()
    
    if existing_payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment already initiated for this order"
        )
    
    # Create payment record
    transaction_id = generate_transaction_id()
    
    payment = Payment(
        order_id=order.id,
        amount=order.total_amount,
        payment_method=payment_data.payment_method,
        status=PaymentStatus.PENDING,
        transaction_id=transaction_id,
        payment_gateway="MockPay"
    )
    
    # Store payment method specific details
    if payment_data.payment_method == PaymentMethod.CARD:
        payment.card_last4 = payment_data.card_number[-4:]
        payment.card_brand = get_card_brand(payment_data.card_number)
    elif payment_data.payment_method == PaymentMethod.UPI:
        payment.upi_id = payment_data.upi_id
    elif payment_data.payment_method == PaymentMethod.WALLET:
        payment.wallet_provider = payment_data.wallet_provider
    
    # COD is auto-confirmed
    if payment_data.payment_method == PaymentMethod.COD:
        payment.status = PaymentStatus.SUCCESS
        payment.completed_at = datetime.utcnow()
        order.status = OrderStatus.ORDER_PLACED
        # Update all items to paid for COD
        for item in order.items:
            item.payment_status = "paid"
    
    db.add(payment)
    await db.flush()  # get payment.id

    # Grant spin for COD order (payment placed = order success)
    if payment_data.payment_method == PaymentMethod.COD:
        from routers.rewards import grant_spin
        from models.reward import SpinSource
        await grant_spin(db, customer_id=current_user.id, source=SpinSource.ORDER, source_ref_id=order.id)

    await db.commit()
    await db.refresh(payment)
    
    # Generate mock payment URL
    payment_url = f"http://localhost:8000/mock-payment/{payment.id}" if payment_data.payment_method != PaymentMethod.COD else None
    
    return PaymentResponse(
        id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
        payment_method=payment.payment_method,
        status=payment.status,
        transaction_id=payment.transaction_id,
        payment_gateway=payment.payment_gateway,
        payment_url=payment_url,
        initiated_at=payment.initiated_at
    )

@router.post("/{payment_id}/confirm", response_model=PaymentStatusResponse)
async def confirm_payment(
    payment_id: int,
    confirm_data: PaymentConfirmRequest,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Confirm mock payment (simulates successful payment)"""
    
    # Get payment
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # Get order and verify ownership
    order_result = await db.execute(
        select(Order).where(
            Order.id == payment.order_id,
            Order.customer_id == current_user.id
        )
    )
    order = order_result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    # Check if already processed
    if payment.status in [PaymentStatus.SUCCESS, PaymentStatus.FAILED]:
        return PaymentStatusResponse(
            payment_id=payment.id,
            order_id=payment.order_id,
            status=payment.status,
            transaction_id=payment.transaction_id,
            amount=payment.amount,
            message=f"Payment already {payment.status.value}",
            completed_at=payment.completed_at
        )
    
    # Simulate payment processing
    payment.status = PaymentStatus.PROCESSING
    await db.commit()
    
    # Determine success/failure based on mock data or request
    success = confirm_data.simulate_success
    
    # Check mock card/UPI results
    if payment.payment_method == PaymentMethod.CARD and payment.card_last4:
        # Find full card number in mock data (simplified)
        for card, info in MOCK_CARDS.items():
            if card.endswith(payment.card_last4):
                if info["result"] != "success":
                    success = False
                    payment.failure_reason = f"Card {info['result']}"
                break
    
    if payment.payment_method == PaymentMethod.UPI and payment.upi_id:
        upi_result = MOCK_UPI.get(payment.upi_id, "success")
        if upi_result != "success":
            success = False
            payment.failure_reason = f"UPI payment {upi_result}"
    
    if success:
        # Payment successful
        payment.status = PaymentStatus.SUCCESS
        payment.completed_at = datetime.utcnow()
        
        # Update order
        order.status = OrderStatus.ORDER_PLACED
        # Update all items to paid
        for item in order.items:
            item.payment_status = "paid"
        
        # Deduct stock from products
        order_items_result = await db.execute(
            select(order.items)
        )
        
        # Update coupon usage
        if order.coupon_id:
            coupon_result = await db.execute(select(Coupon).where(Coupon.id == order.coupon_id))
            coupon = coupon_result.scalar_one_or_none()
            if coupon:
                coupon.current_usage += 1
                
                # Record coupon usage
                coupon_usage = CouponUsage(
                    coupon_id=coupon.id,
                    user_id=current_user.id,
                    order_id=order.id,
                    discount_amount=order.discount_amount
                )
                db.add(coupon_usage)
        
        # Create webhook event
        webhook = PaymentWebhook(
            payment_id=payment.id,
            event_type="payment.success",
            payload={"order_id": order.id, "amount": payment.amount},
            processed=True
        )
        db.add(webhook)

        # Grant spin token for successful order payment
        from routers.rewards import grant_spin
        from models.reward import SpinSource
        await grant_spin(db, customer_id=current_user.id, source=SpinSource.ORDER, source_ref_id=order.id)
        
        message = "Payment successful"
    else:
        # Payment failed
        payment.status = PaymentStatus.FAILED
        payment.completed_at = datetime.utcnow()
        if not payment.failure_reason:
            payment.failure_reason = "Payment declined"
        
        # Update all items to failed
        for item in order.items:
            item.payment_status = "failed"
        
        # Update overall order status to FAILED
        order.status = OrderStatus.FAILED
        
        # Create webhook event
        webhook = PaymentWebhook(
            payment_id=payment.id,
            event_type="payment.failed",
            payload={"order_id": order.id, "reason": payment.failure_reason},
            processed=True
        )
        db.add(webhook)
        
        message = f"Payment failed: {payment.failure_reason}"
    
    await db.commit()
    await db.refresh(payment)
    
    return PaymentStatusResponse(
        payment_id=payment.id,
        order_id=payment.order_id,
        status=payment.status,
        transaction_id=payment.transaction_id,
        amount=payment.amount,
        message=message,
        completed_at=payment.completed_at
    )

@router.get("/{payment_id}/status", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment status"""
    
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # Verify ownership
    order_result = await db.execute(
        select(Order).where(
            Order.id == payment.order_id,
            Order.customer_id == current_user.id
        )
    )
    order = order_result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    message = f"Payment is {payment.status.value}"
    if payment.failure_reason:
        message += f": {payment.failure_reason}"
    
    return PaymentStatusResponse(
        payment_id=payment.id,
        order_id=payment.order_id,
        status=payment.status,
        transaction_id=payment.transaction_id,
        amount=payment.amount,
        message=message,
        completed_at=payment.completed_at
    )

@router.get("/order/{order_id}", response_model=PaymentSchema)
async def get_payment_by_order(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment for an order"""
    
    # Verify order ownership
    order_result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.customer_id == current_user.id
        )
    )
    order = order_result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    result = await db.execute(select(Payment).where(Payment.order_id == order_id))
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found for this order"
        )
    
    return payment

@router.get("/history", response_model=list[PaymentSchema])
async def get_payment_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's payment history"""
    
    # Get user's orders
    orders_result = await db.execute(
        select(Order.id).where(Order.customer_id == current_user.id)
    )
    order_ids = [row[0] for row in orders_result.all()]
    
    # Get payments for those orders
    result = await db.execute(
        select(Payment).where(Payment.order_id.in_(order_ids)).offset(skip).limit(limit)
    )
    payments = result.scalars().all()
    
    return payments

@router.get("", response_model=list[PaymentSchema])
async def list_all_payments(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all payments (admin only)"""
    
    result = await db.execute(select(Payment).offset(skip).limit(limit))
    payments = result.scalars().all()
    
    return payments

@router.post("/{payment_id}/refund", response_model=PaymentRefundResponse)
async def process_refund(
    payment_id: int,
    refund_data: PaymentRefundRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Process refund (admin only)"""
    
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    if payment.status != PaymentStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only refund successful payments"
        )
    
    # Calculate refund amount
    refund_amount = refund_data.amount if refund_data.amount else payment.amount
    
    if refund_amount > (payment.amount - payment.refund_amount):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount exceeds available amount"
        )
    
    # Process refund
    payment.refund_amount += refund_amount
    payment.refund_reason = refund_data.reason
    payment.refunded_at = datetime.utcnow()
    
    if payment.refund_amount >= payment.amount:
        payment.status = PaymentStatus.REFUNDED
    else:
        payment.status = PaymentStatus.PARTIALLY_REFUNDED
    
    # Update order status
    order_result = await db.execute(select(Order).where(Order.id == payment.order_id))
    order = order_result.scalar_one_or_none()
    if order:
        order.status = OrderStatus.REFUNDED
    
    # Create webhook event
    webhook = PaymentWebhook(
        payment_id=payment.id,
        event_type="refund.processed",
        payload={"amount": refund_amount, "reason": refund_data.reason},
        processed=True
    )
    db.add(webhook)
    
    await db.commit()
    await db.refresh(payment)
    
    return PaymentRefundResponse(
        payment_id=payment.id,
        refund_amount=refund_amount,
        status=payment.status,
        message=f"Refund of ₹{refund_amount} processed successfully"
    )

@router.get("/stats", response_model=PaymentStats)
async def get_payment_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get payment statistics (admin only)"""
    
    # Total payments
    total_result = await db.execute(select(func.count(Payment.id)))
    total_payments = total_result.scalar()
    
    # Successful payments
    success_result = await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.SUCCESS)
    )
    successful_payments = success_result.scalar()
    
    # Failed payments
    failed_result = await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.FAILED)
    )
    failed_payments = failed_result.scalar()
    
    # Total amount
    amount_result = await db.execute(
        select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.SUCCESS)
    )
    total_amount = amount_result.scalar() or 0.0
    
    # Total refunded
    refund_result = await db.execute(
        select(func.sum(Payment.refund_amount))
    )
    total_refunded = refund_result.scalar() or 0.0
    
    # Payment method breakdown
    method_result = await db.execute(
        select(Payment.payment_method, func.count(Payment.id)).group_by(Payment.payment_method)
    )
    payment_method_breakdown = {method.value: count for method, count in method_result.all()}
    
    return PaymentStats(
        total_payments=total_payments,
        successful_payments=successful_payments,
        failed_payments=failed_payments,
        total_amount=total_amount,
        total_refunded=total_refunded,
        payment_method_breakdown=payment_method_breakdown
    )

# ==================== MOCK RAZORPAY INTEGRATION ====================

@router.post("/razorpay/create-order", response_model=RazorpayOrderResponse)
async def create_razorpay_order(
    receipt: str, # passed as order_id string
    amount: int, # in paise
    currency: str = "INR",
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a mock Razorpay order.
    Amount is in paise (100 paise = 1 INR).
    """
    order_id = int(receipt)
    
    # Verify order exists
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Generate mock Razorpay Order ID
    razorpay_order_id = f"order_{uuid.uuid4().hex[:14]}"
    
    return RazorpayOrderResponse(
        id=razorpay_order_id,
        currency=currency,
        amount=amount,
        receipt=receipt,
        status="created",
        order_id=order_id
    )

@router.post("/razorpay/verify", response_model=PaymentStatusResponse)
async def verify_razorpay_payment(
    verify_data: RazorpayVerifyRequest,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify mock Razorpay payment signature and mark order as paid.
    """
    # Logic to verify signature would go here (skip for mock)
    # verify_signature(verify_data.razorpay_order_id, verify_data.razorpay_payment_id, verify_data.razorpay_signature)
    
    order_id = verify_data.order_id
    
    # Get order
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Check if payment already recorded
    existing_payment_result = await db.execute(select(Payment).where(Payment.order_id == order_id))
    existing_payment = existing_payment_result.scalar_one_or_none()
    
    if existing_payment:
         return PaymentStatusResponse(
            payment_id=existing_payment.id,
            order_id=order_id,
            status=existing_payment.status,
            transaction_id=existing_payment.transaction_id,
            amount=existing_payment.amount,
            message="Payment already processed",
            completed_at=existing_payment.completed_at
        )

    # Mark as Paid
    payment = Payment(
        order_id=order.id,
        amount=order.total_amount,
        payment_method=PaymentMethod.CARD, # Assume card for razorpay
        status=PaymentStatus.SUCCESS,
        transaction_id=verify_data.razorpay_payment_id,
        payment_gateway="Razorpay (Mock)",
        completed_at=datetime.utcnow()
    )
    
    order.status = OrderStatus.ORDER_PLACED
    for item in order.items:
        item.payment_status = "paid"
    
    # Stock deduction etc should be shared logic, but for now duplicate or assume handled by order flow if not already
    # Note: If reusing confirm_payment logic, better to refactor.
    # For MVP, we'll just deduct stock here as well.
    for item in order.items:
        prod_result = await db.execute(select(Product).where(Product.id == item.product_id))
        prod = prod_result.scalar_one_or_none()
        if prod:
            # prod.stock -= item.quantity # Already deducted in create_order in cart.py ?? 
            # WAIT: cart.py's create_order DEDUCTS stock. 
            # If so, we don't need to deduct here.
            # Let's check cart.py... create_order DOES deduct stock.
            # So we only need to update status.
            pass

    db.add(payment)
    await db.flush()  # get payment.id

    # Grant spin token for Razorpay order success
    from routers.rewards import grant_spin
    from models.reward import SpinSource
    await grant_spin(db, customer_id=current_user.id, source=SpinSource.ORDER, source_ref_id=order.id)

    await db.commit()
    await db.refresh(payment)
    
    return PaymentStatusResponse(
        payment_id=payment.id,
        order_id=order_id,
        status=payment.status,
        transaction_id=payment.transaction_id,
        amount=payment.amount,
        message="Payment verified and order confirmed",
        completed_at=payment.completed_at
    )
