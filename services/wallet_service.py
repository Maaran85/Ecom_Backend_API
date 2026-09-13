from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException

from models.referral import (
    CustomerWallet,
    WalletTransaction,
    WalletRedemption,
    WalletTxnType,
    CommissionStatus
)


async def get_or_create_wallet(db: AsyncSession, customer_id: int) -> CustomerWallet:
    """Retrieve existing wallet or initialize a new wallet for the customer."""
    res = await db.execute(
        select(CustomerWallet).where(CustomerWallet.customer_id == customer_id)
    )
    wallet = res.scalar_one_or_none()
    if not wallet:
        wallet = CustomerWallet(
            customer_id=customer_id,
            available_points=0.0,
            available_amount=0.0,
            on_hold_points=0.0,
            on_hold_amount=0.0,
            redeemed_points=0.0,
            redeemed_amount=0.0,
            lifetime_earned_points=0.0,
            lifetime_earned_amount=0.0,
            available_balance=0.0,
            lifetime_earned=0.0,
            order_placed_count=0,
            order_delivered_count=0,
            order_canceled_count=0,
            order_returned_count=0,
            ref_com_status=CommissionStatus.PENDING,
            updated_at=datetime.utcnow()
        )
        db.add(wallet)
        await db.flush()
    return wallet


async def credit_wallet_points(
    db: AsyncSession,
    customer_id: int,
    points: float,
    amount: float,
    txn_type: WalletTxnType,
    order_id: Optional[int] = None,
    source_user_id: Optional[int] = None,
    description: Optional[str] = None
) -> WalletTransaction:
    """Directly credit spendable points and amount to the customer wallet and log to ledger."""
    wallet = await get_or_create_wallet(db, customer_id)
    
    wallet.available_points += points
    wallet.available_amount += amount
    wallet.lifetime_earned_points += points
    wallet.lifetime_earned_amount += amount
    
    # Keep legacy columns in sync
    wallet.available_balance = wallet.available_amount
    wallet.lifetime_earned = wallet.lifetime_earned_amount
    wallet.updated_at = datetime.utcnow()

    tx = WalletTransaction(
        customer_id=customer_id,
        order_id=order_id,
        source_user_id=source_user_id,
        points=points,
        amount=amount,
        transaction_type=txn_type,
        status=CommissionStatus.CREDITED,
        description=description or f"Credited {points} points (₹{amount:.2f})",
        created_at=datetime.utcnow()
    )
    db.add(tx)
    await db.flush()
    return tx


async def redeem_wallet_points_for_order(
    db: AsyncSession,
    customer_id: int,
    order_id: int,
    points_to_redeem: float,
    conversion_ratio: float = 100.0,
    transaction_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Redeems available wallet points during checkout using row-level locking.
    100 Points = ₹1.00.
    """
    if points_to_redeem <= 0:
        return {"discount_amount": 0.0, "points_redeemed": 0.0}

    # Fetch wallet with row-level lock (with_for_update) to prevent race conditions
    res = await db.execute(
        select(CustomerWallet)
        .where(CustomerWallet.customer_id == customer_id)
        .with_for_update()
    )
    wallet = res.scalar_one_or_none()
    if not wallet or wallet.available_points < points_to_redeem:
        available = wallet.available_points if wallet else 0.0
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet points. Requested: {points_to_redeem}, Available: {available}"
        )

    redeem_amount = round(points_to_redeem / conversion_ratio, 2)

    # Deduct from available, add to redeemed
    wallet.available_points -= points_to_redeem
    wallet.available_amount = max(0.0, wallet.available_amount - redeem_amount)
    wallet.redeemed_points += points_to_redeem
    wallet.redeemed_amount += redeem_amount
    
    # Sync legacy balance
    wallet.available_balance = wallet.available_amount
    wallet.updated_at = datetime.utcnow()

    # Record ledger transaction
    tx = WalletTransaction(
        customer_id=customer_id,
        order_id=order_id,
        points=-points_to_redeem,
        amount=-redeem_amount,
        transaction_type=WalletTxnType.REDEEM,
        status=CommissionStatus.REDEEMED,
        description=f"Redeemed {points_to_redeem} points (₹{redeem_amount:.2f}) on Order #{order_id}",
        created_at=datetime.utcnow()
    )
    db.add(tx)

    # Record redemption header
    redemption = WalletRedemption(
        customer_id=customer_id,
        order_id=order_id,
        transaction_id=transaction_id,
        redeem_points=points_to_redeem,
        redeem_amount=redeem_amount,
        status=CommissionStatus.REDEEMED,
        created_at=datetime.utcnow()
    )
    db.add(redemption)
    await db.flush()

    return {
        "discount_amount": redeem_amount,
        "points_redeemed": points_to_redeem,
        "remaining_points": wallet.available_points,
        "remaining_amount": wallet.available_amount
    }


async def refund_wallet_redemption_for_order(
    db: AsyncSession,
    customer_id: int,
    order_id: int
) -> bool:
    """Reverses a prior redemption if the order is cancelled before shipping."""
    res = await db.execute(
        select(WalletRedemption).where(
            WalletRedemption.order_id == order_id,
            WalletRedemption.customer_id == customer_id,
            WalletRedemption.status == CommissionStatus.REDEEMED
        )
    )
    redemption = res.scalar_one_or_none()
    if not redemption:
        return False

    wallet = await get_or_create_wallet(db, customer_id)
    
    # Restore points
    wallet.available_points += redemption.redeem_points
    wallet.available_amount += redemption.redeem_amount
    wallet.redeemed_points = max(0.0, wallet.redeemed_points - redemption.redeem_points)
    wallet.redeemed_amount = max(0.0, wallet.redeemed_amount - redemption.redeem_amount)
    wallet.available_balance = wallet.available_amount
    wallet.updated_at = datetime.utcnow()

    redemption.status = CommissionStatus.CANCELLED

    # Record compensatory ledger entry
    tx = WalletTransaction(
        customer_id=customer_id,
        order_id=order_id,
        points=redemption.redeem_points,
        amount=redemption.redeem_amount,
        transaction_type=WalletTxnType.CREDIT,
        status=CommissionStatus.CREDITED,
        description=f"Restored {redemption.redeem_points} redeemed points from cancelled Order #{order_id}",
        created_at=datetime.utcnow()
    )
    db.add(tx)
    await db.flush()
    return True
