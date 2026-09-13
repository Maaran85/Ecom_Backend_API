from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from pydantic import BaseModel
from datetime import datetime, timedelta
from models import User, CustomerUser
from models.reward import SpinConfig, SpinToken, SpinResult, RewardPrize, MonthlyLeaderboard, SpinSource, RewardSession, RewardSessionStatus
from core.database import get_db
from core.permissions import get_current_active_user, require_admin
import random

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Pydantic Schemas
# ─────────────────────────────────────────────────────────────

class SpinConfigOut(BaseModel):
    id: int
    is_active: bool
    top_x_winners: int
    spins_per_order: int
    spins_per_recharge: int
    spins_per_bill: int
    min_rank: int
    max_rank: int

    class Config:
        from_attributes = True

class SpinConfigUpdate(BaseModel):
    is_active: Optional[bool] = None
    top_x_winners: Optional[int] = None
    spins_per_order: Optional[int] = None
    spins_per_recharge: Optional[int] = None
    spins_per_bill: Optional[int] = None
    min_rank: Optional[int] = None
    max_rank: Optional[int] = None

class SpinPlayResult(BaseModel):
    token_id: int
    rank_earned: int
    source: str
    month_year: str
    spun_at: datetime
    message: str

class SpinAvailableOut(BaseModel):
    available_spins: int
    tokens: List[dict]

class PrizeCreate(BaseModel):
    month_year: str           # e.g. "2026-03"
    rank_position: int
    name: str
    description: Optional[str] = None
    prize_value: Optional[float] = None

class PrizeTemplateIn(BaseModel):
    month_year: str
    pool_amount: float = 250000.0

class PrizeOut(BaseModel):
    id: int
    month_year: str
    rank_position: int
    name: str
    description: Optional[str]
    prize_value: Optional[float]

    class Config:
        from_attributes = True

class LeaderboardEntry(BaseModel):
    customer_id: int
    customer_name: str
    total_score: int
    total_spins: int
    rank_position: int

class MyStatsOut(BaseModel):
    month_year: str
    my_rank: Optional[int]
    total_score: int
    total_spins: int
    available_spins: int
    best_rank: Optional[int]   # lowest (best) rank_earned this month
    spin_history: List[dict]

class RewardSessionCreate(BaseModel):
    month_year: str
    net_profit: float = 0.0
    reward_pool: float = 0.0
    status: str = "draft"

class RewardSessionUpdate(BaseModel):
    net_profit: Optional[float] = None
    reward_pool: Optional[float] = None
    status: Optional[str] = None

class RewardSessionOut(BaseModel):
    id: int
    month_year: str
    net_profit: float
    reward_pool: float
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

# ─────────────────────────────────────────────────────────────
# Helper: get or create default config
# ─────────────────────────────────────────────────────────────
async def _get_config(db: AsyncSession) -> SpinConfig:
    result = await db.execute(select(SpinConfig).limit(1))
    cfg = result.scalars().first()
    if not cfg:
        cfg = SpinConfig()
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg

# ─────────────────────────────────────────────────────────────
# CUSTOMER ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("/config", response_model=SpinConfigOut)
async def get_public_config(db: AsyncSession = Depends(get_db)):
    """Get the current spin game configuration for the frontend."""
    return await _get_config(db)

@router.get("/spins/available", response_model=SpinAvailableOut)
async def get_available_spins(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """How many unplayed spins the customer currently has."""
    q = select(SpinToken).where(
        SpinToken.customer_id == current_user.id,
        SpinToken.is_played == False
    ).order_by(SpinToken.granted_at.desc())
    result = await db.execute(q)
    tokens = result.scalars().all()
    return SpinAvailableOut(
        available_spins=len(tokens),
        tokens=[
            {"id": t.id, "source": t.source.value, "granted_at": t.granted_at.isoformat()}
            for t in tokens
        ]
    )

@router.post("/spins/play", response_model=SpinPlayResult)
async def play_spin(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Play one spin — returns a random rank number from the wheel."""
    cfg = await _get_config(db)
    if not cfg.is_active:
        raise HTTPException(status_code=403, detail="Reward spin game is currently paused.")

    # Get oldest unplayed token
    q = select(SpinToken).where(
        SpinToken.customer_id == current_user.id,
        SpinToken.is_played == False
    ).order_by(SpinToken.granted_at.asc()).limit(1)
    result = await db.execute(q)
    token = result.scalars().first()
    if not token:
        raise HTTPException(status_code=400, detail="No spins available. Complete an order, recharge, or bill payment to earn spins.")

    # Generate random rank
    rank_earned = random.randint(cfg.min_rank, cfg.max_rank)
    month_year = datetime.utcnow().strftime("%Y-%m")

    # Mark token as played
    token.is_played = True
    token.played_at = datetime.utcnow()
    
    # Extract values before commit to prevent MissingGreenlet lazy-load errors
    token_id = token.id
    token_source_value = token.source.value if hasattr(token.source, 'value') else token.source

    # Record spin result
    spin_result = SpinResult(
        token_id=token_id,
        customer_id=current_user.id,
        rank_earned=rank_earned,
        source=token.source,
        month_year=month_year,
        spun_at=datetime.utcnow()
    )
    db.add(spin_result)
    await db.commit()
    await db.refresh(spin_result)

    return SpinPlayResult(
        token_id=token_id,
        rank_earned=rank_earned,
        source=token_source_value,
        month_year=month_year,
        spun_at=spin_result.spun_at,
        message=f"🎉 You got rank #{rank_earned} this spin!"
    )


# ─────────────────────────────────────────────────────────────
# ORDER SPIN & WIN (SLAB-BASED WHEEL REWARD & HUB)
# ─────────────────────────────────────────────────────────────

def _generate_wheel_segments(min_pts: int, max_pts: int, ratio: float = 100.0) -> List[Dict[str, Any]]:
    """Generate 6-8 visually distinct wheel slices spanning between min_pts and max_pts."""
    colors = [
        "#FF5722", "#4CAF50", "#2196F3", "#9C27B0", 
        "#FF9800", "#E91E63", "#00BCD4", "#8BC34A"
    ]
    # Build list of points to distribute across 8 sectors
    step = max(1, (max_pts - min_pts) // 4)
    raw_points = []
    curr = min_pts
    while curr <= max_pts:
        raw_points.append(curr)
        curr += step
    if max_pts not in raw_points:
        raw_points.append(max_pts)

    # Pad or tile to 8 sectors
    while len(raw_points) < 8:
        raw_points.extend(raw_points[:8 - len(raw_points)])
    raw_points = raw_points[:8]
    random.seed(42)  # consistent layout structure
    random.shuffle(raw_points)

    segments = []
    for idx, pts in enumerate(raw_points):
        segments.append({
            "index": idx,
            "points": pts,
            "amount_inr": round(pts / ratio, 3),
            "label": f"{pts} Pts",
            "sub_label": f"₹{pts / ratio:.2f}",
            "color": colors[idx % len(colors)]
        })
    return segments


@router.get("/hub")
@router.get("/spins/summary")
async def get_spins_and_rewards_hub(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete My Spins & Rewards Hub (Amazon / GPay / CRED Card-List Architecture).
    Returns:
      - Wallet balances (Available vs On-Hold)
      - Ready to Play active cards (Unspun Orders & Tokens)
      - Claimed Rewards History cards (Won Points, ₹ Amount, On-Hold/Credited status)
    """
    customer_id = int(current_user.id)

    from models.cart import Order
    from services.reward_service import get_or_create_reward_configuration, run_daily_reward_maturity_evaluation
    from services.wallet_service import get_or_create_wallet

    # Real-time auto-evaluation: Release any matured rewards before returning wallet and claimed history
    try:
        await run_daily_reward_maturity_evaluation(db)
        await db.commit()
    except Exception as e:
        print(f"DEBUG: Error auto-evaluating reward maturity: {e}")

    config = await get_or_create_reward_configuration(db)
    slabs = config.spin_and_win_slabs or []
    wallet = await get_or_create_wallet(db, customer_id)

    # 1. Fetch unspun orders (Ready to Play)
    res_unspun = await db.execute(
        select(Order)
        .where(
            Order.customer_id == customer_id,
            Order.spin_reward_status.in_(["pending", "unspun", "na", None])
        )
        .order_by(Order.id.desc())
    )
    unspun_orders_raw = res_unspun.scalars().all()

    ready_to_play = []
    for o in unspun_orders_raw:
        min_pts, max_pts = 1, 5
        for slab in slabs:
            s_min = slab.get("min", 0)
            s_max = slab.get("max")
            if o.total_amount >= s_min and (s_max is None or o.total_amount <= s_max):
                min_pts = int(slab.get("min_points", 1))
                max_pts = int(slab.get("max_points", 5))
                break
        
        max_inr = round(max_pts / config.points_to_rupee_ratio, 2)
        ready_to_play.append({
            "card_type": "order_spin",
            "order_id": o.id,
            "order_number": o.order_number or f"ORD-{o.id}",
            "order_amount": float(o.total_amount or 0.0),
            "order_date": o.created_at.isoformat() if hasattr(o, "created_at") and o.created_at else None,
            "wheel_min_points": min_pts,
            "wheel_max_points": max_pts,
            "wheel_max_inr": max_inr,
            "title": f"Order #{o.order_number or o.id}",
            "subtitle": f"Win up to {max_pts} Points (₹{max_inr:.2f}) into Wallet",
            "button_text": "Spin Now",
            "claim_url": f"/rewards/order-spin/{o.id}/claim"
        })

    # 2. Fetch generic spin tokens (if any from recharges/promos)
    res_tokens = await db.execute(
        select(SpinToken).where(
            SpinToken.customer_id == customer_id,
            SpinToken.is_played == False
        ).order_by(SpinToken.granted_at.desc())
    )
    tokens = res_tokens.scalars().all()
    for t in tokens:
        ready_to_play.append({
            "card_type": "token_spin",
            "token_id": t.id,
            "source": t.source.value if hasattr(t.source, 'value') else str(t.source),
            "granted_at": t.granted_at.isoformat() if t.granted_at else None,
            "wheel_min_points": 1,
            "wheel_max_points": 100,
            "wheel_max_inr": 1.00,
            "title": f"Special Promo Spin",
            "subtitle": f"Earned from {t.source.value if hasattr(t.source, 'value') else t.source}",
            "button_text": "Spin Now",
            "claim_url": "/rewards/spins/play"
        })

    # 3. Fetch Claimed Rewards History (Spun Orders)
    from models.cart import Order, OrderItem
    from models.product import Product
    from services.return_policy_service import resolve_item_return_policy

    res_claimed = await db.execute(
        select(Order)
        .where(
            Order.customer_id == customer_id,
            Order.spin_reward_status.in_(["on_hold", "credited", "refunded", "cancelled"])
        )
        .order_by(Order.updated_at.desc() if hasattr(Order, "updated_at") else Order.id.desc())
    )
    claimed_orders_raw = res_claimed.scalars().all()

    claimed_history = []
    for o in claimed_orders_raw:
        status_code = o.spin_reward_status or "credited"
        
        # Human-readable status mapping
        if status_code == "on_hold":
            status_label = "On Hold (Pending Delivery & Return Window)"
            status_badge = "warning"
            is_spendable = False
        elif status_code == "credited":
            status_label = "Credited to Available Balance"
            status_badge = "success"
            is_spendable = True
        elif status_code == "refunded":
            status_label = "Refunded / Returned"
            status_badge = "secondary"
            is_spendable = False
        else:
            status_label = "Cancelled"
            status_badge = "danger"
            is_spendable = False

        # Resolve dynamic return window from order items & products
        max_ret_days = 0
        has_returnable_items = False
        res_items = await db.execute(
            select(OrderItem, Product)
            .outerjoin(Product, OrderItem.product_id == Product.id)
            .where(OrderItem.order_id == o.id)
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

        effective_days = max_ret_days if has_returnable_items else 0

        # Estimated settlement text
        if status_code == "on_hold":
            if o.delivered_at:
                est_date = o.delivered_at + timedelta(days=effective_days)
                if effective_days == 0:
                    est_settlement_text = "Matures on Delivery (Non-Returnable)"
                else:
                    est_settlement_text = f"Matures on {est_date.strftime('%b %d, %Y')}"
            else:
                if effective_days == 0:
                    est_settlement_text = "Matures on delivery (Non-Returnable)"
                else:
                    est_settlement_text = f"Available {effective_days} days after delivery"
        elif status_code == "credited":
            est_settlement_text = "Ready to Spend at Checkout"
        else:
            est_settlement_text = "-"

        claimed_history.append({
            "order_id": o.id,
            "order_number": o.order_number or f"ORD-{o.id}",
            "order_amount": float(o.total_amount or 0.0),
            "points_won": o.spin_reward_points or 0,
            "amount_won": float(o.spin_reward_amount or 0.0),
            "spin_reward_status": status_code,
            "status_label": status_label,
            "status_badge": status_badge,
            "is_spendable": is_spendable,
            "order_status": o.status.value if hasattr(o.status, 'value') else str(o.status),
            "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
            "estimated_settlement": est_settlement_text
        })

    return {
        "status": "success",
        "wallet_summary": {
            "available_points": wallet.available_points,
            "available_amount": wallet.available_amount,
            "on_hold_points": wallet.on_hold_points,
            "on_hold_amount": wallet.on_hold_amount,
            "redeemed_points": wallet.redeemed_points,
            "redeemed_amount": wallet.redeemed_amount,
            "lifetime_earned_points": wallet.lifetime_earned_points,
            "lifetime_earned_amount": wallet.lifetime_earned_amount,
            "points_to_rupee_ratio": config.points_to_rupee_ratio
        },
        "stats": {
            "total_spins_ready": len(ready_to_play),
            "unspun_orders_count": len(unspun_orders_raw),
            "unplayed_tokens_count": len(tokens),
            "total_claimed_rewards": len(claimed_history),
        },
        "ready_to_play": ready_to_play,
        "claimed_history": claimed_history
    }


@router.get("/order-spin/{order_id}/wheel")
async def get_order_spin_wheel(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve wheel configuration and slice definitions for a specific order."""
    from models.cart import Order
    from services.reward_service import get_or_create_reward_configuration

    res = await db.execute(
        select(Order).where(Order.id == order_id, Order.customer_id == current_user.id)
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    config = await get_or_create_reward_configuration(db)
    slabs = config.spin_and_win_slabs or []
    min_pts, max_pts = 1, 5
    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order.total_amount >= s_min and (s_max is None or order.total_amount <= s_max):
            min_pts = int(slab.get("min_points", 1))
            max_pts = int(slab.get("max_points", 5))
            break

    is_spun = order.spin_reward_status in ["on_hold", "credited"]
    segments = _generate_wheel_segments(min_pts, max_pts, config.points_to_rupee_ratio)

    return {
        "status": "success",
        "order_id": order.id,
        "order_number": order.order_number or f"ORD-{order.id}",
        "order_amount": float(order.total_amount or 0.0),
        "is_spun": is_spun,
        "points_earned": order.spin_reward_points if is_spun else None,
        "amount_earned": order.spin_reward_amount if is_spun else None,
        "spin_reward_status": order.spin_reward_status,
        "wheel_min_points": min_pts,
        "wheel_max_points": max_pts,
        "segments": segments
    }


@router.get("/order-spin/latest/unspun")
async def get_latest_unspun_order(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the customer's most recent order that has not had its spin claimed yet."""
    from models.cart import Order
    from services.reward_service import get_or_create_reward_configuration

    res = await db.execute(
        select(Order)
        .where(
            Order.customer_id == current_user.id,
            Order.spin_reward_status.in_(["na", "pending", "unspun", None])
        )
        .order_by(Order.id.desc())
        .limit(1)
    )
    order = res.scalar_one_or_none()
    if not order:
        return {"status": "none", "order_id": None}

    config = await get_or_create_reward_configuration(db)
    slabs = config.spin_and_win_slabs or []
    min_pts, max_pts = 1, 5
    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order.total_amount >= s_min and (s_max is None or order.total_amount <= s_max):
            min_pts = int(slab.get("min_points", 1))
            max_pts = int(slab.get("max_points", 5))
            break

    return {
        "status": "success",
        "order_id": order.id,
        "order_number": order.order_number,
        "order_amount": order.total_amount,
        "wheel_min_points": min_pts,
        "wheel_max_points": max_pts,
        "is_spun": False,
        "points_earned": None,
        "amount_earned": None,
        "spin_reward_status": order.spin_reward_status or "na"
    }


@router.get("/order-spin/{order_id}")
async def get_order_spin_status(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve spin wheel parameters and status for a placed order."""
    from models.cart import Order
    from services.reward_service import get_or_create_reward_configuration

    res = await db.execute(
        select(Order).where(Order.id == order_id, Order.customer_id == current_user.id)
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    config = await get_or_create_reward_configuration(db)
    slabs = config.spin_and_win_slabs or []
    min_pts, max_pts = 1, 5
    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order.total_amount >= s_min and (s_max is None or order.total_amount <= s_max):
            min_pts = int(slab.get("min_points", 1))
            max_pts = int(slab.get("max_points", 5))
            break

    is_spun = order.spin_reward_status in ["on_hold", "credited"]
    return {
        "status": "success",
        "order_id": order.id,
        "order_number": order.order_number,
        "order_amount": order.total_amount,
        "wheel_min_points": min_pts,
        "wheel_max_points": max_pts,
        "is_spun": is_spun,
        "points_earned": order.spin_reward_points if is_spun else None,
        "amount_earned": order.spin_reward_amount if is_spun else None,
        "spin_reward_status": order.spin_reward_status
    }


@router.post("/order-spin/{order_id}/claim")
async def claim_order_spin(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Play the spin wheel for a completed order.
    The points won are securely generated based on the order value slab (1-5, 6-10, 11-15)
    and stored in ON_HOLD status in customer wallet during the return window.
    """
    from models.cart import Order
    from models.referral import WalletTransaction, WalletTxnType, CommissionStatus
    from services.reward_service import get_or_create_reward_configuration, calculate_spin_and_win_reward
    from services.wallet_service import get_or_create_wallet

    res = await db.execute(
        select(Order).where(Order.id == order_id, Order.customer_id == current_user.id)
    )
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    if order.spin_reward_status in ["on_hold", "credited"]:
        return {
            "status": "success",
            "message": "Spin reward already claimed for this order.",
            "points_earned": order.spin_reward_points,
            "amount_earned": order.spin_reward_amount,
            "spin_reward_status": order.spin_reward_status,
            "is_already_claimed": True
        }

    config = await get_or_create_reward_configuration(db)
    points_won, amount_in_inr = calculate_spin_and_win_reward(order.total_amount, config)

    order.spin_reward_points = points_won
    order.spin_reward_amount = amount_in_inr

    # Resolve return window dynamically from order items & products
    from models.cart import OrderItem, OrderStatus
    from models.product import Product
    from services.return_policy_service import resolve_item_return_policy
    from datetime import timezone

    max_ret_days = 0
    has_returnable_items = False
    res_items = await db.execute(
        select(OrderItem, Product)
        .outerjoin(Product, OrderItem.product_id == Product.id)
        .where(OrderItem.order_id == order.id)
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

    effective_days = max_ret_days if has_returnable_items else 0
    is_matured_now = False
    if order.status == OrderStatus.DELIVERED and order.delivered_at:
        deliv_at = order.delivered_at
        if deliv_at.tzinfo is None:
            deliv_at = deliv_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= deliv_at + timedelta(days=effective_days):
            is_matured_now = True

    buyer_wallet = await get_or_create_wallet(db, int(current_user.id))

    if is_matured_now:
        order.spin_reward_status = "credited"
        buyer_wallet.available_points += points_won
        buyer_wallet.available_amount += amount_in_inr
        buyer_wallet.lifetime_earned_points += points_won
        buyer_wallet.lifetime_earned_amount += amount_in_inr
        buyer_wallet.available_balance = buyer_wallet.available_amount
        buyer_wallet.lifetime_earned = buyer_wallet.lifetime_earned_amount
        buyer_wallet.updated_at = datetime.utcnow()
        tx_status = CommissionStatus.CREDITED
        tx_desc = f"Spin & Win on Order #{order.order_number or order.id} (Credited - Matured)"
    else:
        order.spin_reward_status = "on_hold"
        buyer_wallet.on_hold_points += points_won
        buyer_wallet.on_hold_amount += amount_in_inr
        buyer_wallet.updated_at = datetime.utcnow()
        tx_status = CommissionStatus.ON_HOLD
        tx_desc = f"Spin & Win on Order #{order.order_number or order.id} (On-Hold during return window)"

    # Log to wallet transaction ledger
    spin_tx = WalletTransaction(
        customer_id=int(current_user.id),
        order_id=order.id,
        points=points_won,
        amount=amount_in_inr,
        transaction_type=WalletTxnType.SPIN_AND_WIN,
        status=tx_status,
        description=tx_desc,
        created_at=datetime.utcnow()
    )
    db.add(spin_tx)
    await db.commit()
    await db.refresh(order)

    # Find winning slice index for frontend animation
    slabs = config.spin_and_win_slabs or []
    min_pts, max_pts = 1, 5
    for slab in slabs:
        s_min = slab.get("min", 0)
        s_max = slab.get("max")
        if order.total_amount >= s_min and (s_max is None or order.total_amount <= s_max):
            min_pts = int(slab.get("min_points", 1))
            max_pts = int(slab.get("max_points", 5))
            break
    segments = _generate_wheel_segments(min_pts, max_pts, config.points_to_rupee_ratio)
    winning_slice_index = 0
    for seg in segments:
        if seg["points"] == points_won:
            winning_slice_index = seg["index"]
            break

    return {
        "status": "success",
        "message": f"🎉 Congratulations! You won {points_won} points (₹{amount_in_inr:.2f})!",
        "order_id": order.id,
        "order_number": order.order_number or f"ORD-{order.id}",
        "points_earned": points_won,
        "amount_earned": amount_in_inr,
        "winning_slice_index": winning_slice_index,
        "spin_reward_status": order.spin_reward_status,
        "is_already_claimed": False,
        "wallet_update": {
            "on_hold_points": buyer_wallet.on_hold_points,
            "on_hold_amount": buyer_wallet.on_hold_amount,
            "available_points": buyer_wallet.available_points,
            "available_amount": buyer_wallet.available_amount
        }
    }


@router.get("/leaderboard")
async def get_leaderboard(
    month_year: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Current month's public leaderboard — sorted by best (lowest) rank_earned."""
    cfg = await _get_config(db)
    target_month = month_year or datetime.utcnow().strftime("%Y-%m")

    # Aggregate: best rank (min), total spins, per customer
    q = (
        select(
            SpinResult.customer_id,
            CustomerUser.full_name.label("customer_name"),
            func.min(SpinResult.rank_earned).label("best_rank"),
            func.count(SpinResult.id).label("total_spins"),
        )
        .join(CustomerUser, SpinResult.customer_id == CustomerUser.id)
        .where(SpinResult.month_year == target_month)
        .group_by(SpinResult.customer_id, CustomerUser.full_name)
        .order_by(func.min(SpinResult.rank_earned).asc())   # lowest rank = best
        .limit(cfg.top_x_winners)
    )
    rows = (await db.execute(q)).all()

    entries = [
        {
            "rank_position": i + 1,
            "customer_id": row.customer_id,
            "customer_name": row.customer_name,
            "best_rank": row.best_rank,
            "total_spins": row.total_spins,
        }
        for i, row in enumerate(rows)
    ]

    return {
        "month_year": target_month,
        "top_x": cfg.top_x_winners,
        "leaderboard": entries
    }

@router.get("/my-stats", response_model=MyStatsOut)
async def get_my_stats(
    month_year: Optional[str] = None,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Customer's own rank, score, and spin history for the current month."""
    target_month = month_year or datetime.utcnow().strftime("%Y-%m")

    # My monthly score + spins + best rank
    score_q = select(
        func.sum(SpinResult.rank_earned).label("total_score"),
        func.count(SpinResult.id).label("total_spins"),
        func.min(SpinResult.rank_earned).label("best_rank")
    ).where(
        SpinResult.customer_id == current_user.id,
        SpinResult.month_year == target_month
    )
    row = (await db.execute(score_q)).first()
    total_score = row.total_score or 0
    total_spins = row.total_spins or 0
    best_rank = row.best_rank

    # Find my leaderboard rank efficiently in SQL (lower best_rank = better position)
    rank_subquery = (
        select(
            SpinResult.customer_id,
            func.rank().over(order_by=func.min(SpinResult.rank_earned).asc()).label("rank")
        )
        .where(SpinResult.month_year == target_month)
        .group_by(SpinResult.customer_id)
        .subquery()
    )
    rank_q = select(rank_subquery.c.rank).where(rank_subquery.c.customer_id == current_user.id)
    my_rank = (await db.execute(rank_q)).scalar()

    # Spin history
    history_q = (
        select(SpinResult)
        .where(SpinResult.customer_id == current_user.id, SpinResult.month_year == target_month)
        .order_by(SpinResult.spun_at.desc())
        .limit(20)
    )
    history = (await db.execute(history_q)).scalars().all()

    # Available spins
    avail_q = select(func.count(SpinToken.id)).where(
        SpinToken.customer_id == current_user.id,
        SpinToken.is_played == False
    )
    available_spins = (await db.execute(avail_q)).scalar() or 0

    return MyStatsOut(
        month_year=target_month,
        my_rank=my_rank,
        total_score=total_score,
        total_spins=total_spins,
        available_spins=available_spins,
        best_rank=best_rank,
        spin_history=[
            {
                "id": s.id,
                "rank_earned": s.rank_earned,
                "source": s.source.value,
                "spun_at": s.spun_at.isoformat()
            }
            for s in history
        ]
    )

# ─────────────────────────────────────────────────────────────
# ADMIN ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("/admin/config", response_model=SpinConfigOut)
async def admin_get_config(
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get current spin game configuration."""
    return await _get_config(db)

@router.put("/admin/config", response_model=SpinConfigOut)
async def admin_update_config(
    data: SpinConfigUpdate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update spin game configuration."""
    cfg = await _get_config(db)
    update_data = data.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(cfg, field, value)
    cfg.updated_by = current_user.id
    cfg.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(cfg)
    return cfg

@router.get("/admin/leaderboard")
async def admin_get_leaderboard(
    month_year: Optional[str] = None,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Full leaderboard for admin including all customers."""
    target_month = month_year or datetime.utcnow().strftime("%Y-%m")
    cfg = await _get_config(db)

    q = (
        select(
            SpinResult.customer_id,
            CustomerUser.full_name.label("customer_name"),
            CustomerUser.phone.label("customer_phone"),
            func.sum(SpinResult.rank_earned).label("total_score"),
            func.count(SpinResult.id).label("total_spins")
        )
        .join(CustomerUser, SpinResult.customer_id == CustomerUser.id)
        .where(SpinResult.month_year == target_month)
        .group_by(SpinResult.customer_id, CustomerUser.full_name, CustomerUser.phone)
        .order_by(func.sum(SpinResult.rank_earned).desc())
    )
    rows = (await db.execute(q)).all()

    entries = [
        {
            "rank_position": i + 1,
            "customer_id": row.customer_id,
            "customer_name": row.customer_name,
            "customer_phone": row.customer_phone,
            "total_score": row.total_score,
            "total_spins": row.total_spins,
            "is_winner": (i + 1) <= cfg.top_x_winners
        }
        for i, row in enumerate(rows)
    ]

    return {
        "month_year": target_month,
        "top_x": cfg.top_x_winners,
        "total_participants": len(entries),
        "leaderboard": entries
    }

@router.post("/admin/announce-winners")
async def admin_announce_winners(
    month_year: Optional[str] = None,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Announce top-X winners for a month and assign prizes."""
    target_month = month_year or datetime.utcnow().strftime("%Y-%m")
    cfg = await _get_config(db)

    # Get top-X customers for the month with JOIN to avoid N+1
    q = (
        select(
            SpinResult.customer_id,
            CustomerUser.full_name.label("customer_name"),
            func.sum(SpinResult.rank_earned).label("total_score"),
            func.count(SpinResult.id).label("total_spins")
        )
        .join(CustomerUser, SpinResult.customer_id == CustomerUser.id)
        .where(SpinResult.month_year == target_month)
        .group_by(SpinResult.customer_id, CustomerUser.full_name)
        .order_by(func.sum(SpinResult.rank_earned).desc())
        .limit(cfg.top_x_winners)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No spin activity found for this month.")

    # Get prizes for the month
    prizes_q = select(RewardPrize).where(RewardPrize.month_year == target_month).order_by(RewardPrize.rank_position)
    prizes = {p.rank_position: p for p in (await db.execute(prizes_q)).scalars().all()}

    now = datetime.utcnow()
    announced = []
    for i, row in enumerate(rows):
        rank_pos = i + 1
        prize = prizes.get(rank_pos)

        # Check if already announced
        existing_q = select(MonthlyLeaderboard).where(
            MonthlyLeaderboard.customer_id == row.customer_id,
            MonthlyLeaderboard.month_year == target_month
        )
        existing = (await db.execute(existing_q)).scalars().first()

        if existing:
            existing.final_rank = rank_pos
            existing.total_score = row.total_score
            existing.total_spins = row.total_spins
            existing.prize_id = prize.id if prize else None
            existing.announced_at = now
            existing.is_announced = True
        else:
            entry = MonthlyLeaderboard(
                customer_id=row.customer_id,
                month_year=target_month,
                final_rank=rank_pos,
                total_score=row.total_score,
                total_spins=row.total_spins,
                prize_id=prize.id if prize else None,
                announced_at=now,
                is_announced=True
            )
            db.add(entry)

        announced.append({
            "rank_position": rank_pos,
            "customer_name": row.customer_name,
            "total_score": row.total_score,
            "prize": prize.name if prize else "No prize configured"
        })

    await db.commit()
    return {
        "message": f"✅ Winners announced for {target_month}.",
        "announced_count": len(announced),
        "winners": announced
    }

@router.get("/admin/prizes", response_model=List[PrizeOut])
async def admin_list_prizes(
    month_year: Optional[str] = None,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all prizes, optionally filtered by month."""
    q = select(RewardPrize).order_by(RewardPrize.month_year, RewardPrize.rank_position)
    if month_year:
        q = q.where(RewardPrize.month_year == month_year)
    result = await db.execute(q)
    return result.scalars().all()

@router.post("/admin/prizes", response_model=PrizeOut, status_code=201)
async def admin_create_prize(
    data: PrizeCreate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new prize entry for a specific rank position and month."""
    prize = RewardPrize(
        month_year=data.month_year,
        rank_position=data.rank_position,
        name=data.name,
        description=data.description,
        prize_value=data.prize_value,
        created_by=current_user.id
    )
    db.add(prize)
    await db.commit()
    await db.refresh(prize)
    return prize

@router.delete("/admin/prizes/{prize_id}", status_code=204)
async def admin_delete_prize(
    prize_id: int,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a prize entry."""
    prize = await db.get(RewardPrize, prize_id)
    if not prize:
        raise HTTPException(status_code=404, detail="Prize not found.")
    await db.delete(prize)
    await db.commit()

@router.get("/admin/announced-winners")
async def admin_get_announced_winners(
    month_year: Optional[str] = None,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all announced winners (past months)."""
    q = (
        select(
            MonthlyLeaderboard,
            CustomerUser.full_name.label("customer_name"),
            CustomerUser.phone.label("customer_phone"),
            RewardPrize.name.label("prize_name"),
            RewardPrize.prize_value.label("prize_value")
        )
        .join(CustomerUser, MonthlyLeaderboard.customer_id == CustomerUser.id)
        .outerjoin(RewardPrize, MonthlyLeaderboard.prize_id == RewardPrize.id)
        .where(MonthlyLeaderboard.is_announced == True)
    )
    if month_year:
        q = q.where(MonthlyLeaderboard.month_year == month_year)
    q = q.order_by(MonthlyLeaderboard.month_year.desc(), MonthlyLeaderboard.final_rank)
    rows = (await db.execute(q)).all()

    results = [
        {
            "month_year": row.MonthlyLeaderboard.month_year,
            "final_rank": row.MonthlyLeaderboard.final_rank,
            "customer_name": row.customer_name,
            "customer_phone": row.customer_phone,
            "total_score": row.MonthlyLeaderboard.total_score,
            "total_spins": row.MonthlyLeaderboard.total_spins,
            "prize": row.prize_name,
            "prize_value": row.prize_value,
            "announced_at": row.MonthlyLeaderboard.announced_at.isoformat() if row.MonthlyLeaderboard.announced_at else None
        }
        for row in rows
    ]
    return results


    return results


# ─────────────────────────────────────────────────────────────
# Reward Session CRUD
# ─────────────────────────────────────────────────────────────

@router.get("/admin/sessions", response_model=List[RewardSessionOut])
async def admin_list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all monthly reward sessions."""
    result = await db.execute(select(RewardSession).order_by(RewardSession.month_year.desc()))
    return result.scalars().all()

@router.post("/admin/sessions", response_model=RewardSessionOut)
async def admin_create_session(
    data: RewardSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new monthly reward session."""
    # Check if session already exists for this month
    existing = await db.execute(select(RewardSession).where(RewardSession.month_year == data.month_year))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail=f"Session for {data.month_year} already exists.")
    
    session = RewardSession(
        month_year=data.month_year,
        net_profit=data.net_profit,
        reward_pool=data.reward_pool,
        status=data.status,
        created_by=current_user.id
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

@router.put("/admin/sessions/{session_id}", response_model=RewardSessionOut)
async def admin_update_session(
    session_id: int,
    data: RewardSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an existing monthly reward session."""
    session = await db.get(RewardSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if data.net_profit is not None: session.net_profit = data.net_profit
    if data.reward_pool is not None: session.reward_pool = data.reward_pool
    if data.status is not None: session.status = data.status
    
    await db.commit()
    await db.refresh(session)
    return session

@router.delete("/admin/sessions/{session_id}")
async def admin_delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a monthly reward session."""
    session = await db.get(RewardSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    await db.delete(session)
    await db.commit()
    return {"message": "Session deleted"}


@router.post("/admin/generate-prizes-template")
async def admin_generate_prizes_template(
    data: PrizeTemplateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Bulk generate 1000 prizes based on a tiered distribution model."""
    month_year = data.month_year
    pool = data.pool_amount

    # 1. Clear existing prizes for this month for clean slate
    await db.execute(delete(RewardPrize).where(RewardPrize.month_year == month_year))

    new_prizes = []
    created_at = datetime.utcnow()

    # Tier 1: Top 10 (25% of pool)
    top_10_splits = [0.09, 0.05, 0.03, 0.02, 0.015, 0.012, 0.01, 0.009, 0.007, 0.007]
    for i, pct in enumerate(top_10_splits):
        rank = i + 1
        val = pool * pct
        new_prizes.append(RewardPrize(
            month_year=month_year,
            rank_position=rank,
            name=f"Rank {rank} Mega Prize",
            description=f"Top tier reward for rank #{rank}",
            prize_value=round(val, 2),
            created_at=created_at,
            created_by=current_user.id
        ))

    # Tier 2: 11-100 (25% of pool) - 90 winners
    tier2_total = pool * 0.25
    tier2_per = tier2_total / 90
    for r in range(11, 101):
        new_prizes.append(RewardPrize(
            month_year=month_year,
            rank_position=r,
            name="Elite Rewards",
            prize_value=round(tier2_per, 2),
            created_at=created_at,
            created_by=current_user.id
        ))

    # Tier 3: 101-500 (30% of pool) - 400 winners
    tier3_total = pool * 0.30
    tier3_per = tier3_total / 400
    for r in range(101, 501):
        new_prizes.append(RewardPrize(
            month_year=month_year,
            rank_position=r,
            name="Star Rewards",
            prize_value=round(tier3_per, 2),
            created_at=created_at,
            created_by=current_user.id
        ))

    # Tier 4: 501-1000 (20% of pool) - 500 winners
    tier4_total = pool * 0.20
    tier4_per = tier4_total / 500
    for r in range(501, 1001):
        new_prizes.append(RewardPrize(
            month_year=month_year,
            rank_position=r,
            name="Community Prize",
            prize_value=round(tier4_per, 2),
            created_at=created_at,
            created_by=current_user.id
        ))

    db.add_all(new_prizes)
    await db.commit()

    return {
        "message": f"Successfully generated {len(new_prizes)} prizes for {month_year}",
        "count": len(new_prizes),
        "total_pool": pool
    }


# ─────────────────────────────────────────────────────────────
# Internal helper — called from other routers to grant spins
# ─────────────────────────────────────────────────────────────
async def grant_spin(db: AsyncSession, customer_id: int, source: SpinSource, source_ref_id: Optional[int] = None):
    """Grant spin token(s) to a customer based on the event source."""
    cfg = await _get_config(db)
    if not cfg.is_active:
        return

    spins_to_grant = {
        SpinSource.ORDER: cfg.spins_per_order,
        SpinSource.RECHARGE: cfg.spins_per_recharge,
        SpinSource.BILL: cfg.spins_per_bill,
    }.get(source, 1)

    for _ in range(spins_to_grant):
        token = SpinToken(
            customer_id=customer_id,
            source=source,
            source_ref_id=source_ref_id,
            is_played=False,
            granted_at=datetime.utcnow()
        )
        db.add(token)
    # Caller is responsible for commit
