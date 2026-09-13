from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import Order, OrderItem, OrderStatus, PaymentStatus
from datetime import datetime, timezone

async def calculate_and_update_order_status(db, order_id: int):
    """
    Recalculates the overall status of an order based on its individual items 
    and updates the parent order record.
    """
    # 1. Fetch Parent Order with items and payment
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.payment),
            selectinload(Order.items)
        )
    )
    parent_order = result.scalar_one_or_none()
    if not parent_order:
        return None

    if not parent_order.items:
        return parent_order

    # 2. Normalize item statuses
    statuses = [(it.status or "pending").lower() for it in parent_order.items]
    
    # Priority 1: All delivered/resolved (terminal states)
    terminal_states = ["delivered", "rejected", "undelivered", "cancelled", "returned"]
    if all(s in terminal_states for s in statuses):
        if any(s == "delivered" for s in statuses):
            parent_order.status = OrderStatus.DELIVERED
            if not parent_order.delivered_at:
                parent_order.delivered_at = datetime.now(timezone.utc)
            if parent_order.payment and parent_order.payment.status != PaymentStatus.REFUNDED:
                parent_order.payment.status = PaymentStatus.SUCCESS
            await settle_referral_commissions_for_order(db, parent_order.id, credit=True)
        else:
            # If all were cancelled/rejected, order is cancelled
            parent_order.status = OrderStatus.CANCELLED
            await settle_referral_commissions_for_order(db, parent_order.id, credit=False)
    
    # Priority 2: Any out for delivery (High priority "transit" status)
    elif any(s == "out_for_delivery" for s in statuses):
        parent_order.status = OrderStatus.OUT_FOR_DELIVERY
    
    # Priority 3: All items have left the dealer (shipped/dispatched/at hub onward)
    elif all(s in ["dispatched", "shipped", "at_hub", "out_for_delivery", "delivered", "rejected", "undelivered", "cancelled", "returned"] for s in statuses):
        if any(s == "out_for_delivery" for s in statuses):
            parent_order.status = OrderStatus.OUT_FOR_DELIVERY
        elif any(s == "shipped" for s in statuses):
            parent_order.status = OrderStatus.SHIPPED
        elif any(s == "at_hub" for s in statuses):
            parent_order.status = OrderStatus.DISPATCHED # Or could be OrderStatus.AT_HUB if mapped
        else:
            parent_order.status = OrderStatus.DISPATCHED
    
    # Priority 4: Any packed
    elif any(s == "packed" for s in statuses):
        parent_order.status = OrderStatus.PACKED
        
    # Priority 5: Any in packaging
    elif any(s == "packaging" for s in statuses):
        parent_order.status = OrderStatus.PACKAGING

    # Priority 6: Any confirmed (Full/Partial)
    elif any(s == "confirmed" for s in statuses):
         # If some are confirmed and some are still placed/pending, order is overall processing
         if any(s in ["order_placed", "pending"] for s in statuses):
             parent_order.status = OrderStatus.PROCESSING
         else:
             parent_order.status = OrderStatus.CONFIRMED
    
    # Priority 7: Mixed stage advancement
    elif any(s in ["dispatched", "shipped", "at_hub", "out_for_delivery", "packaging", "packed"] for s in statuses):
        # Only upgrade status if currently in early stages
        if parent_order.status in [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.ORDER_PLACED]:
            parent_order.status = OrderStatus.PROCESSING
    
    # Priority 8: Partially confirmed
    elif any(s == "confirmed" for s in statuses) and parent_order.status == OrderStatus.ORDER_PLACED:
        parent_order.status = OrderStatus.PROCESSING
    
    # Generate Tax Invoice Number if not already present and order is placed/confirmed or advanced
    if not parent_order.tax_invoice_no and parent_order.status in [
        OrderStatus.ORDER_PLACED,
        OrderStatus.CONFIRMED, 
        OrderStatus.PROCESSING,
        OrderStatus.PACKAGING,
        OrderStatus.PACKED,
        OrderStatus.SHIPPED,
        OrderStatus.DISPATCHED,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED
    ]:
        # Simple unique invoice number generation: INV-YEAR-ORDERID-RANDOM
        curr_year = datetime.now().year
        import random
        import string
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        parent_order.tax_invoice_no = f"INV/{curr_year}/{parent_order.id:05d}/{suffix}"

    # Finally commit if inside a task, or let the caller commit
    db.add(parent_order)
    return parent_order


async def settle_referral_commissions_for_order(db, order_id: int, credit: bool = True):
    """
    Settles pending referral commissions for an order:
    - If credit=True (Order Delivered): Credits commission amount & points to referrer's CustomerWallet balance & marks CREDITED.
    - If credit=False (Order Cancelled/Rejected): Marks pending commission as CANCELLED.
    """
    from models.referral import (
        ReferralOrderCommission,
        CommissionStatus,
        CustomerWallet,
        WalletTransaction,
        WalletTxnType,
        CustomerReferralProfile
    )
    from services.wallet_service import get_or_create_wallet
    from services.reward_service import get_or_create_reward_configuration
    
    # 1. Update Referral Order Commissions
    result = await db.execute(
        select(ReferralOrderCommission)
        .where(ReferralOrderCommission.order_id == order_id)
        .where(ReferralOrderCommission.status == CommissionStatus.PENDING)
        .options(selectinload(ReferralOrderCommission.items))
    )
    commissions = result.scalars().all()
    now_naive = datetime.utcnow()

    for comm in commissions:
        new_status = CommissionStatus.CREDITED if credit else CommissionStatus.CANCELLED
        comm.status = new_status
        comm.settled_at = now_naive
        for item_comm in comm.items:
            item_comm.status = new_status

        if credit and comm.total_commission_amount > 0:
            wallet = await get_or_create_wallet(db, comm.referrer_id)
            pts = float(comm.total_commission_points or round(comm.total_commission_amount * 100.0, 2))
            amt = float(comm.total_commission_amount)

            wallet.available_balance += amt
            wallet.lifetime_earned += amt
            wallet.available_amount += amt
            wallet.available_points += pts
            wallet.lifetime_earned_amount += amt
            wallet.lifetime_earned_points += pts
            wallet.updated_at = now_naive

            db.add(WalletTransaction(
                customer_id=comm.referrer_id,
                source_user_id=comm.referee_id,
                order_id=order_id,
                points=pts,
                amount=amt,
                transaction_type=WalletTxnType.REFERRAL_PURCHASE,
                status=CommissionStatus.CREDITED,
                description=f"Referral commission credited for Order #{order_id}",
                created_at=now_naive
            ))

    # 2. Update buyer wallet delivery counts & evaluate 3-order referral bonus (Bonus A)
    ord_res = await db.execute(select(Order).where(Order.id == order_id))
    order_obj = ord_res.scalar_one_or_none()
    if order_obj:
        if credit:
            order_obj.referral_reward_status = "credited" if commissions else order_obj.referral_reward_status
            
            buyer_wallet = await get_or_create_wallet(db, order_obj.customer_id)
            buyer_wallet.order_delivered_count += 1
            buyer_wallet.updated_at = now_naive
            
            # Check 3 delivered orders threshold for referral signup bonus (A)
            config = await get_or_create_reward_configuration(db)
            if (
                buyer_wallet.order_delivered_count >= config.referral_qualifying_orders_count
                and buyer_wallet.ref_com_status == CommissionStatus.PENDING
            ):
                ref_prof_res = await db.execute(
                    select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == order_obj.customer_id)
                )
                buyer_prof = ref_prof_res.scalar_one_or_none()
                if buyer_prof and buyer_prof.referred_by_id:
                    referrer_wallet = await get_or_create_wallet(db, buyer_prof.referred_by_id)
                    bonus_pts = config.referral_amount_points
                    bonus_amt = round(bonus_pts / config.points_to_rupee_ratio, 2)

                    referrer_wallet.available_points += bonus_pts
                    referrer_wallet.available_amount += bonus_amt
                    referrer_wallet.lifetime_earned_points += bonus_pts
                    referrer_wallet.lifetime_earned_amount += bonus_amt
                    referrer_wallet.available_balance = referrer_wallet.available_amount
                    referrer_wallet.lifetime_earned = referrer_wallet.lifetime_earned_amount
                    referrer_wallet.updated_at = now_naive

                    db.add(WalletTransaction(
                        customer_id=buyer_prof.referred_by_id,
                        source_user_id=order_obj.customer_id,
                        points=bonus_pts,
                        amount=bonus_amt,
                        transaction_type=WalletTxnType.REFERRAL,
                        status=CommissionStatus.CREDITED,
                        description=f"Referral Bonus (A) for referred customer #{order_obj.customer_id} reaching {buyer_wallet.order_delivered_count} delivered orders",
                        created_at=now_naive
                    ))
                    buyer_wallet.ref_com_status = CommissionStatus.PAID
                else:
                    buyer_wallet.ref_com_status = CommissionStatus.NA
        else:
            if order_obj.referral_reward_status == "pending":
                order_obj.referral_reward_status = "cancelled"


