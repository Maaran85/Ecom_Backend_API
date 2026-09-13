from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
import random
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func

from models.reward import RewardConfiguration, SpinConfig, SpinToken, SpinResult, SpinSource
from models.referral import (
    CustomerReferralProfile,
    ReferralOrderCommission,
    ReferralItemCommission,
    CustomerWallet,
    WalletTransaction,
    WalletTxnType,
    CommissionStatus
)
from models.cart import Order, OrderItem, OrderStatus
from models.customer_user import CustomerUser
from services.wallet_service import get_or_create_wallet, credit_wallet_points
from services.return_policy_service import resolve_item_return_policy

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. Configuration Helpers
# ─────────────────────────────────────────────────────────────

async def get_or_create_reward_configuration(db: AsyncSession) -> RewardConfiguration:
    """Retrieve or initialize the system dynamic reward configurations."""
    res = await db.execute(select(RewardConfiguration).limit(1))
    cfg = res.scalar_one_or_none()
    if not cfg:
        cfg = RewardConfiguration(
            points_to_rupee_ratio=100.0,
            referral_amount_points=100.0,
            referral_qualifying_orders_count=3,
            purchase_commission_slabs=[
                {"min": 1, "max": 500, "rate_percent": 0.20},
                {"min": 501, "max": 1000, "rate_percent": 0.15},
                {"min": 1001, "max": None, "rate_percent": 0.20}
            ],
            spin_and_win_slabs=[
                {"min": 1, "max": 500, "min_points": 1, "max_points": 5},
                {"min": 501, "max": 1000, "min_points": 6, "max_points": 10},
                {"min": 1001, "max": None, "min_points": 11, "max_points": 15}
            ]
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


# ─────────────────────────────────────────────────────────────
# 2. Calculation Engines
# ─────────────────────────────────────────────────────────────

def calculate_purchase_commission(
    order_amount: float,
    config: RewardConfiguration
) -> Tuple[float, float, float]:
    """
    Calculates Commission B based on order billing slabs:
      - 1 - 500: 0.20%
      - 501 - 1000: 0.15%
      - > 1001: 0.20%
    Returns: (commission_amount_in_inr, commission_points, applied_rate_percent)
    """
    if order_amount <= 0:
        return 0.0, 0.0, 0.0

    slabs = config.purchase_commission_slabs or []
    applied_rate = 0.20  # Fallback default

    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order_amount >= s_min and (s_max is None or order_amount <= s_max):
            applied_rate = float(slab.get("rate_percent", 0.20))
            break

    commission_amount = round(order_amount * (applied_rate / 100.0), 3)
    commission_points = round(commission_amount * config.points_to_rupee_ratio, 2)
    return commission_amount, commission_points, applied_rate


def calculate_spin_and_win_reward(
    order_amount: float,
    config: RewardConfiguration
) -> Tuple[int, float]:
    """
    Calculates Spin & Win reward points & ₹ amount based on order value slabs:
      - 1 - 500: 1 to 5 Points
      - 501 - 1000: 6 to 10 Points
      - > 1001: 11 to 15 Points
    Returns: (points_won, amount_in_inr)
    """
    slabs = config.spin_and_win_slabs or []
    min_pts, max_pts = 1, 5

    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order_amount >= s_min and (s_max is None or order_amount <= s_max):
            min_pts = int(slab.get("min_points", 1))
            max_pts = int(slab.get("max_points", 5))
            break

    points_won = random.randint(min_pts, max_pts)
    amount_in_inr = round(points_won / config.points_to_rupee_ratio, 3)
    return points_won, amount_in_inr


# ─────────────────────────────────────────────────────────────
# 3. Order Lifecycle Event Hooks
# ─────────────────────────────────────────────────────────────

async def on_order_placed_rewards(
    db: AsyncSession,
    order: Order,
    buyer_id: int
) -> Dict[str, Any]:
    """
    Triggered when an order is placed and payment is initiated/completed.
    1. Checks if buyer has a referrer.
    2. Snapshots referrer_id and calculates referral purchase commission (Commission B) in PENDING status.
    3. Pre-calculates / authorizes a Spin & Win opportunity for the buyer.
    4. Increments order_placed_count on buyer wallet.
    """
    config = await get_or_create_reward_configuration(db)
    buyer_wallet = await get_or_create_wallet(db, buyer_id)
    buyer_wallet.order_placed_count += 1

    # 1. Referral Linkage
    res_prof = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == buyer_id)
    )
    buyer_profile = res_prof.scalar_one_or_none()
    referrer_id = buyer_profile.referred_by_id if buyer_profile else None

    # Snapshot referrer on order
    order.referrer_id = referrer_id

    # 2. Commission B (Purchase Commission)
    if referrer_id:
        comm_amt, comm_pts, rate = calculate_purchase_commission(order.total_amount, config)
        order.referral_reward_points = comm_pts
        order.referral_reward_amount = comm_amt
        order.referral_reward_status = "pending"

        # Create detailed commission header
        ref_comm = ReferralOrderCommission(
            referrer_id=referrer_id,
            referee_id=buyer_id,
            order_id=order.id,
            total_commission_points=comm_pts,
            total_commission_amount=comm_amt,
            status=CommissionStatus.PENDING,
            created_at=datetime.utcnow()
        )
        db.add(ref_comm)
    else:
        order.referral_reward_status = "na"

    # 3. Setup Spin & Win Opportunity (Pending until customer plays the wheel)
    spin_pts, spin_amt = calculate_spin_and_win_reward(order.total_amount, config)
    order.spin_reward_points = spin_pts
    order.spin_reward_amount = spin_amt
    order.spin_reward_status = "pending"

    await db.flush()

    return {
        "referrer_id": referrer_id,
        "referral_reward_points": order.referral_reward_points,
        "referral_reward_amount": order.referral_reward_amount,
        "spin_reward_points": spin_pts,
        "spin_reward_amount": spin_amt
    }


async def on_order_cancelled_rewards(
    db: AsyncSession,
    order: Order
) -> None:
    """Cancels pending purchase commissions and removes on-hold spin points."""
    buyer_wallet = await get_or_create_wallet(db, order.customer_id)
    buyer_wallet.order_canceled_count += 1

    # Cancel Commission B
    if order.referral_reward_status == "pending":
        order.referral_reward_status = "cancelled"
        await db.execute(
            update(ReferralOrderCommission)
            .where(ReferralOrderCommission.order_id == order.id)
            .values(status=CommissionStatus.CANCELLED)
        )

    # Cancel Spin & Win
    if order.spin_reward_status == "on_hold":
        order.spin_reward_status = "cancelled"
        buyer_wallet.on_hold_points = max(0.0, buyer_wallet.on_hold_points - order.spin_reward_points)
        buyer_wallet.on_hold_amount = max(0.0, buyer_wallet.on_hold_amount - order.spin_reward_amount)
        
        await db.execute(
            update(WalletTransaction)
            .where(
                WalletTransaction.order_id == order.id,
                WalletTransaction.transaction_type == WalletTxnType.SPIN_AND_WIN,
                WalletTransaction.status == CommissionStatus.ON_HOLD
            )
            .values(status=CommissionStatus.CANCELLED)
        )
    await db.flush()


async def on_order_returned_rewards(
    db: AsyncSession,
    order: Order,
    refund_amount: float
) -> None:
    """Handles returns: cancels on-hold points or injects negative ledger adjustments if already settled."""
    config = await get_or_create_reward_configuration(db)
    buyer_wallet = await get_or_create_wallet(db, order.customer_id)
    buyer_wallet.order_returned_count += 1

    # If commission B was already credited, record refund deduction
    if order.referral_reward_status == "credited" and order.referrer_id:
        comm_amt, comm_pts, _ = calculate_purchase_commission(refund_amount, config)
        ref_wallet = await get_or_create_wallet(db, order.referrer_id)
        
        ref_wallet.available_points = max(0.0, ref_wallet.available_points - comm_pts)
        ref_wallet.available_amount = max(0.0, ref_wallet.available_amount - comm_amt)
        ref_wallet.available_balance = ref_wallet.available_amount
        
        tx = WalletTransaction(
            customer_id=order.referrer_id,
            source_user_id=order.customer_id,
            order_id=order.id,
            points=-comm_pts,
            amount=-comm_amt,
            transaction_type=WalletTxnType.ORDER_REFUND,
            status=CommissionStatus.REFUND,
            description=f"Refund adjustment for return on Order #{order.order_number or order.id}",
            created_at=datetime.utcnow()
        )
        db.add(tx)
        order.referral_reward_status = "refunded"

    elif order.referral_reward_status == "pending":
        order.referral_reward_status = "cancelled"
        await db.execute(
            update(ReferralOrderCommission)
            .where(ReferralOrderCommission.order_id == order.id)
            .values(status=CommissionStatus.CANCELLED)
        )

    # If Spin was on hold, cancel it
    if order.spin_reward_status == "on_hold":
        order.spin_reward_status = "cancelled"
        buyer_wallet.on_hold_points = max(0.0, buyer_wallet.on_hold_points - order.spin_reward_points)
        buyer_wallet.on_hold_amount = max(0.0, buyer_wallet.on_hold_amount - order.spin_reward_amount)
        await db.execute(
            update(WalletTransaction)
            .where(
                WalletTransaction.order_id == order.id,
                WalletTransaction.transaction_type == WalletTxnType.SPIN_AND_WIN,
                WalletTransaction.status == CommissionStatus.ON_HOLD
            )
            .values(status=CommissionStatus.CANCELLED)
        )
    await db.flush()


# ─────────────────────────────────────────────────────────────
# 4. Daily Background Evaluation Batch (Maturity & Settlement)
# ─────────────────────────────────────────────────────────────

async def run_daily_reward_maturity_evaluation(
    db: AsyncSession,
    as_of: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Executes the daily EOD reward maturation process:
      1. Finds delivered orders past the return window (delivered_at + return_window_days <= as_of).
      2. Releases Referral Purchase Commission (B) -> Credits to Referrer wallet.
      3. Releases Spin & Win (C) -> Moves from ON_HOLD to CREDITED in Buyer wallet.
      4. Increments order_delivered_count on buyer wallet.
      5. Evaluates 3-order threshold for Referral Signup Bonus (A) -> Credits 100 Pts to Referrer.
    """
    cutoff = as_of or datetime.now(timezone.utc)
    config = await get_or_create_reward_configuration(db)

    # 1. Fetch delivered orders with pending rewards
    q = (
        select(Order)
        .where(
            Order.status == OrderStatus.DELIVERED,
            Order.delivered_at.isnot(None),
            (Order.referral_reward_status == "pending") | (Order.spin_reward_status == "on_hold")
        )
    )
    res = await db.execute(q)
    orders = res.scalars().all()

    matured_b_count = 0
    matured_c_count = 0
    total_b_pts = 0.0
    total_c_pts = 0.0

    from models.cart import OrderItem
    from models.product import Product
    from services.return_policy_service import resolve_item_return_policy

    for ord_obj in orders:
        # Resolve return window dynamically from order items & products
        max_ret_days = 0
        has_returnable_items = False
        res_items = await db.execute(
            select(OrderItem, Product)
            .outerjoin(Product, OrderItem.product_id == Product.id)
            .where(OrderItem.order_id == ord_obj.id)
        )
        item_rows = res_items.all()
        if item_rows:
            for itm, prod in item_rows:
                pol = resolve_item_return_policy(itm, product=prod)
                if pol["is_returnable"] or pol["is_exchangeable"]:
                    has_returnable_items = True
                    max_ret_days = max(max_ret_days, pol["return_window_days"])
        else:
            max_ret_days = 7
            has_returnable_items = True

        ret_days = max_ret_days if has_returnable_items else 0
        if ord_obj.delivered_at:
            # Handle naive or aware datetime
            deliv_at = ord_obj.delivered_at
            if deliv_at.tzinfo is None:
                deliv_at = deliv_at.replace(tzinfo=timezone.utc)
            maturity_date = deliv_at + timedelta(days=ret_days)
            
            if cutoff < maturity_date:
                continue  # Not matured yet

        # A. Release Referral Purchase Commission (B)
        if ord_obj.referral_reward_status == "pending" and ord_obj.referrer_id:
            ref_wallet = await get_or_create_wallet(db, ord_obj.referrer_id)
            pts = ord_obj.referral_reward_points
            amt = ord_obj.referral_reward_amount

            ref_wallet.available_points += pts
            ref_wallet.available_amount += amt
            ref_wallet.lifetime_earned_points += pts
            ref_wallet.lifetime_earned_amount += amt
            ref_wallet.available_balance = ref_wallet.available_amount
            ref_wallet.lifetime_earned = ref_wallet.lifetime_earned_amount
            ref_wallet.updated_at = datetime.utcnow()

            tx = WalletTransaction(
                customer_id=ord_obj.referrer_id,
                source_user_id=ord_obj.customer_id,
                order_id=ord_obj.id,
                points=pts,
                amount=amt,
                transaction_type=WalletTxnType.REFERRAL_PURCHASE,
                status=CommissionStatus.CREDITED,
                description=f"Purchase commission from referred order #{ord_obj.order_number or ord_obj.id}",
                created_at=datetime.utcnow()
            )
            db.add(tx)
            ord_obj.referral_reward_status = "credited"

            await db.execute(
                update(ReferralOrderCommission)
                .where(ReferralOrderCommission.order_id == ord_obj.id)
                .values(status=CommissionStatus.CREDITED, settled_at=datetime.utcnow())
            )
            matured_b_count += 1
            total_b_pts += pts

        # B. Release Spin & Win Reward (C)
        if ord_obj.spin_reward_status == "on_hold":
            b_wallet = await get_or_create_wallet(db, ord_obj.customer_id)
            s_pts = ord_obj.spin_reward_points
            s_amt = ord_obj.spin_reward_amount

            b_wallet.on_hold_points = max(0.0, b_wallet.on_hold_points - s_pts)
            b_wallet.on_hold_amount = max(0.0, b_wallet.on_hold_amount - s_amt)
            b_wallet.available_points += s_pts
            b_wallet.available_amount += s_amt
            b_wallet.lifetime_earned_points += s_pts
            b_wallet.lifetime_earned_amount += s_amt
            b_wallet.available_balance = b_wallet.available_amount
            b_wallet.lifetime_earned = b_wallet.lifetime_earned_amount
            b_wallet.updated_at = datetime.utcnow()

            await db.execute(
                update(WalletTransaction)
                .where(
                    WalletTransaction.order_id == ord_obj.id,
                    WalletTransaction.transaction_type == WalletTxnType.SPIN_AND_WIN,
                    WalletTransaction.status == CommissionStatus.ON_HOLD
                )
                .values(
                    status=CommissionStatus.CREDITED,
                    description=f"Spin & Win on Order #{ord_obj.order_number or ord_obj.id} (Credited)"
                )
            )
            ord_obj.spin_reward_status = "credited"
            matured_c_count += 1
            total_c_pts += s_pts

    # 2. Evaluate Referral Signup Bonus (A) for users reaching 3 completed delivered orders
    # Find customers with ref_com_status == PENDING
    res_wallets = await db.execute(
        select(CustomerWallet).where(CustomerWallet.ref_com_status == CommissionStatus.PENDING)
    )
    pending_wallets = res_wallets.scalars().all()
    bonus_a_count = 0
    total_a_pts = 0.0

    for w in pending_wallets:
        # Calculate actual successfully completed delivered orders count (excluding cancelled or refunded)
        cnt_res = await db.execute(
            select(func.count(Order.id)).where(
                Order.customer_id == w.customer_id,
                Order.status == OrderStatus.DELIVERED,
                Order.delivered_at.isnot(None),
                Order.referral_reward_status.notin_(["refunded", "cancelled"])
            )
        )
        delivered_count = cnt_res.scalar() or 0
        w.order_delivered_count = delivered_count

        if delivered_count >= config.referral_qualifying_orders_count:
            # Check if this user was referred by someone
            res_p = await db.execute(
                select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == w.customer_id)
            )
            prof = res_p.scalar_one_or_none()
            
            if prof and prof.referred_by_id:
                referrer_wallet = await get_or_create_wallet(db, prof.referred_by_id)
                bonus_pts = config.referral_amount_points  # 100 Pts
                bonus_amt = round(bonus_pts / config.points_to_rupee_ratio, 2)  # ₹1.00

                referrer_wallet.available_points += bonus_pts
                referrer_wallet.available_amount += bonus_amt
                referrer_wallet.lifetime_earned_points += bonus_pts
                referrer_wallet.lifetime_earned_amount += bonus_amt
                referrer_wallet.available_balance = referrer_wallet.available_amount
                referrer_wallet.lifetime_earned = referrer_wallet.lifetime_earned_amount
                referrer_wallet.updated_at = datetime.utcnow()

                tx_bonus = WalletTransaction(
                    customer_id=prof.referred_by_id,
                    source_user_id=w.customer_id,
                    points=bonus_pts,
                    amount=bonus_amt,
                    transaction_type=WalletTxnType.REFERRAL,
                    status=CommissionStatus.CREDITED,
                    description=f"Referral Bonus (A) for referred customer #{w.customer_id} reaching {delivered_count} delivered orders",
                    created_at=datetime.utcnow()
                )
                db.add(tx_bonus)
                w.ref_com_status = CommissionStatus.PAID
                bonus_a_count += 1
                total_a_pts += bonus_pts
            else:
                w.ref_com_status = CommissionStatus.NA

    await db.commit()

    logger.info(
        f"Daily Reward Maturity Run Complete: [B] Matured: {matured_b_count} ({total_b_pts} pts), "
        f"[C] Spins Matured: {matured_c_count} ({total_c_pts} pts), [A] Referral Bonuses Awarded: {bonus_a_count} ({total_a_pts} pts)"
    )

    return {
        "status": "success",
        "purchase_commissions_matured_count": matured_b_count,
        "purchase_commissions_points_credited": total_b_pts,
        "spins_matured_count": matured_c_count,
        "spins_points_credited": total_c_pts,
        "referral_bonuses_awarded_count": bonus_a_count,
        "referral_bonuses_points_credited": total_a_pts
    }
