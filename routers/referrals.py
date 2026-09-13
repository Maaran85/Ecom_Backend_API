from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from typing import List, Optional, Any, Dict
from datetime import datetime, timedelta
from pydantic import BaseModel
import secrets
import string

from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models.customer_user import CustomerUser
from models.product import Category as CategoryModel
from models.referral import (
    CustomerReferralProfile,
    ReferralOrderCommission,
    ReferralItemCommission,
    CustomerWallet,
    WalletTransaction,
    WalletTxnType,
    CommissionStatus
)
from models.reward import RewardConfiguration
from services.wallet_service import get_or_create_wallet
from services.reward_service import get_or_create_reward_configuration, run_daily_reward_maturity_evaluation

router = APIRouter(prefix="/referrals", tags=["Referrals"])


class ApplyCodeRequest(BaseModel):
    referral_code: str


class CategoryRateUpdate(BaseModel):
    referral_commission_rate: Optional[float] = None


class RewardConfigUpdate(BaseModel):
    points_to_rupee_ratio: Optional[float] = None
    referral_amount_points: Optional[float] = None
    referral_qualifying_orders_count: Optional[int] = None
    purchase_commission_slabs: Optional[List[Dict[str, Any]]] = None
    spin_and_win_slabs: Optional[List[Dict[str, Any]]] = None


def _generate_referral_code(customer_id: int) -> str:
    rand_suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"REF{customer_id}{rand_suffix}"


@router.get("/my-profile")
@router.get("/profile-summary")
async def get_my_referral_profile(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get or create the referral profile and wallet for the logged-in customer."""
    customer_id = int(current_user.id)

    # Check existing profile
    res_profile = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == customer_id)
    )
    profile = res_profile.scalar_one_or_none()

    if not profile:
        profile = CustomerReferralProfile(
            customer_id=customer_id,
            referral_code=_generate_referral_code(customer_id)
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    elif not profile.referral_code:
        profile.referral_code = _generate_referral_code(customer_id)
        await db.commit()
        await db.refresh(profile)

    wallet = await get_or_create_wallet(db, customer_id)

    referred_by_name = None
    referred_by_code = None
    if profile.referred_by_id:
        res_ref_user = await db.execute(
            select(CustomerUser).where(CustomerUser.id == profile.referred_by_id)
        )
        ref_user = res_ref_user.scalar_one_or_none()
        if ref_user:
            referred_by_name = ref_user.full_name

        res_ref_prof = await db.execute(
            select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == profile.referred_by_id)
        )
        ref_prof = res_ref_prof.scalar_one_or_none()
        if ref_prof:
            referred_by_code = ref_prof.referral_code

    return {
        "status": "success",
        "referral_code": profile.referral_code,
        "referred_by_id": profile.referred_by_id,
        "referred_by_name": referred_by_name,
        "referred_by_code": referred_by_code,
        "available_points": wallet.available_points,
        "available_amount": wallet.available_amount,
        "on_hold_points": wallet.on_hold_points,
        "on_hold_amount": wallet.on_hold_amount,
        "redeemed_points": wallet.redeemed_points,
        "redeemed_amount": wallet.redeemed_amount,
        "lifetime_earned_points": wallet.lifetime_earned_points,
        "lifetime_earned_amount": wallet.lifetime_earned_amount,
        "available_balance": wallet.available_amount,
        "lifetime_earned": wallet.lifetime_earned_amount,
        "order_placed_count": wallet.order_placed_count,
        "order_delivered_count": wallet.order_delivered_count,
        "order_canceled_count": wallet.order_canceled_count,
        "order_returned_count": wallet.order_returned_count,
        "ref_com_status": wallet.ref_com_status.value if hasattr(wallet.ref_com_status, 'value') else wallet.ref_com_status
    }


@router.get("/wallet-transactions")
async def get_wallet_transactions(
    txn_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve complete points and ₹ credit, debit, on-hold, and refund ledger history."""
    query = select(WalletTransaction).where(WalletTransaction.customer_id == int(current_user.id))
    
    if txn_type:
        query = query.where(WalletTransaction.transaction_type == txn_type)
    if status:
        query = query.where(WalletTransaction.status == status)

    query = query.order_by(WalletTransaction.created_at.desc())
    res = await db.execute(query)
    transactions = res.scalars().all()
    
    return [
        {
            "id": t.id,
            "points": t.points,
            "amount": t.amount,
            "transaction_type": t.transaction_type.value if hasattr(t.transaction_type, 'value') else t.transaction_type,
            "status": t.status.value if hasattr(t.status, 'value') else t.status,
            "description": t.description,
            "order_id": t.order_id,
            "source_user_id": t.source_user_id,
            "created_at": t.created_at.isoformat() if t.created_at else None
        }
        for t in transactions
    ]


@router.get("/validate-code/{code}")
async def validate_referral_code(
    code: str,
    db: AsyncSession = Depends(get_db)
):
    """Validate a referral code during public registration."""
    clean_code = code.strip().upper()
    res_referrer = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.referral_code == clean_code)
    )
    referrer_profile = res_referrer.scalar_one_or_none()
    if not referrer_profile:
        return {"valid": False, "detail": "Invalid referral code."}

    referrer_customer_id = int(referrer_profile.customer_id)
    res_user = await db.execute(
        select(CustomerUser).where(CustomerUser.id == referrer_customer_id)
    )
    referrer_user = res_user.scalar_one_or_none()
    referrer_name = referrer_user.full_name if referrer_user and referrer_user.full_name else "Partner"

    return {
        "valid": True,
        "referral_code": clean_code,
        "referrer_name": referrer_name
    }


@router.post("/preview-code")
async def preview_referral_code(
    payload: ApplyCodeRequest,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Preview referrer details before confirming application."""
    customer_id = int(current_user.id)
    code = payload.referral_code.strip().upper()

    res_referrer = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.referral_code == code)
    )
    referrer_profile = res_referrer.scalar_one_or_none()

    if not referrer_profile:
        raise HTTPException(status_code=404, detail="Invalid referral code.")

    referrer_customer_id = int(referrer_profile.customer_id)
    if referrer_customer_id == customer_id:
        raise HTTPException(status_code=400, detail="You cannot refer yourself.")

    # Fetch referrer name
    res_user = await db.execute(
        select(CustomerUser).where(CustomerUser.id == referrer_customer_id)
    )
    referrer_user = res_user.scalar_one_or_none()
    referrer_name = referrer_user.full_name if referrer_user and referrer_user.full_name else f"Customer #{referrer_customer_id}"

    return {
        "status": "success",
        "referral_code": code,
        "referrer_id": referrer_customer_id,
        "referrer_name": referrer_name
    }


@router.post("/apply-code")
async def apply_referral_code(
    payload: ApplyCodeRequest,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Link the logged-in customer to a referrer using a referral code."""
    customer_id = int(current_user.id)

    # Ensure profile exists
    res_profile = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == customer_id)
    )
    profile = res_profile.scalar_one_or_none()
    if not profile:
        profile = CustomerReferralProfile(
            customer_id=customer_id,
            referral_code=_generate_referral_code(customer_id)
        )
        db.add(profile)

    if profile.referred_by_id:
        raise HTTPException(status_code=400, detail="You have already applied a referral code.")

    # Find referrer profile
    code = payload.referral_code.strip().upper()
    res_referrer = await db.execute(
        select(CustomerReferralProfile).where(CustomerReferralProfile.referral_code == code)
    )
    referrer_profile = res_referrer.scalar_one_or_none()

    if not referrer_profile:
        raise HTTPException(status_code=404, detail="Invalid referral code.")

    referrer_customer_id = int(referrer_profile.customer_id)
    referrer_code = referrer_profile.referral_code

    if referrer_customer_id == customer_id:
        raise HTTPException(status_code=400, detail="You cannot refer yourself.")

    # Fetch referrer name
    res_user = await db.execute(
        select(CustomerUser).where(CustomerUser.id == referrer_customer_id)
    )
    referrer_user = res_user.scalar_one_or_none()
    referrer_name = referrer_user.full_name if referrer_user and referrer_user.full_name else "Referrer"

    profile.referred_by_id = referrer_customer_id
    await db.commit()

    return {
        "status": "success",
        "message": "Referral code applied successfully.",
        "referred_by_id": referrer_customer_id,
        "referred_by_name": referrer_name,
        "referred_by_code": referrer_code
    }


@router.get("/my-commissions")
async def get_my_commissions(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all referral commissions earned by the logged-in customer."""
    customer_id = int(current_user.id)
    res = await db.execute(
        select(ReferralOrderCommission)
        .where(ReferralOrderCommission.referrer_id == customer_id)
        .options(selectinload(ReferralOrderCommission.items))
        .order_by(ReferralOrderCommission.created_at.desc())
    )
    commissions = res.scalars().all()

    return {
        "status": "success",
        "commissions": [
            {
                "id": c.id,
                "order_id": c.order_id,
                "referee_id": c.referee_id,
                "total_commission_points": c.total_commission_points,
                "total_commission_amount": c.total_commission_amount,
                "status": c.status.value if hasattr(c.status, "value") else c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "items": [
                    {
                        "id": i.id,
                        "order_item_id": i.order_item_id,
                        "category_id": i.category_id,
                        "item_price": i.item_price,
                        "applied_rate_percent": i.applied_rate_percent,
                        "commission_points": i.commission_points,
                        "commission_amount": i.commission_amount,
                        "status": i.status.value if hasattr(i.status, "value") else i.status,
                    }
                    for i in c.items
                ]
            }
            for c in commissions
        ]
    }


# ─────────────────────────────────────────────────────────────
# ADMIN CONFIGURATION ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("/admin/reward-config")
async def get_admin_reward_config(
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Fetch current dynamic reward and referral configuration."""
    cfg = await get_or_create_reward_configuration(db)
    return {
        "status": "success",
        "id": cfg.id,
        "points_to_rupee_ratio": cfg.points_to_rupee_ratio,
        "referral_amount_points": cfg.referral_amount_points,
        "referral_qualifying_orders_count": cfg.referral_qualifying_orders_count,
        "purchase_commission_slabs": cfg.purchase_commission_slabs,
        "spin_and_win_slabs": cfg.spin_and_win_slabs,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None
    }


@router.put("/admin/reward-config")
async def update_admin_reward_config(
    payload: RewardConfigUpdate,
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update dynamic reward and referral slabs."""
    cfg = await get_or_create_reward_configuration(db)
    
    if payload.points_to_rupee_ratio is not None:
        cfg.points_to_rupee_ratio = payload.points_to_rupee_ratio
    if payload.referral_amount_points is not None:
        cfg.referral_amount_points = payload.referral_amount_points
    if payload.referral_qualifying_orders_count is not None:
        cfg.referral_qualifying_orders_count = payload.referral_qualifying_orders_count
    if payload.purchase_commission_slabs is not None:
        cfg.purchase_commission_slabs = payload.purchase_commission_slabs
    if payload.spin_and_win_slabs is not None:
        cfg.spin_and_win_slabs = payload.spin_and_win_slabs

    cfg.updated_at = datetime.utcnow()
    cfg.updated_by = current_user.id
    await db.commit()
    await db.refresh(cfg)

    return {
        "status": "success",
        "message": "Reward configuration updated successfully.",
        "config": {
            "points_to_rupee_ratio": cfg.points_to_rupee_ratio,
            "referral_amount_points": cfg.referral_amount_points,
            "referral_qualifying_orders_count": cfg.referral_qualifying_orders_count,
            "purchase_commission_slabs": cfg.purchase_commission_slabs,
            "spin_and_win_slabs": cfg.spin_and_win_slabs
        }
    }


@router.post("/admin/run-maturity-batch")
async def trigger_admin_reward_maturity_batch(
    current_user = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger the daily reward maturity evaluation batch."""
    result = await run_daily_reward_maturity_evaluation(db)
    return {
        "status": "success",
        "message": "Reward maturity evaluation completed successfully.",
        "result": result
    }


# Admin endpoints for managing Category Commission Rates
@router.get("/admin/category-rates")
async def get_admin_category_rates(
    db: AsyncSession = Depends(get_db)
):
    """List all categories with their configured referral commission rate."""
    res = await db.execute(
        select(CategoryModel).order_by(CategoryModel.name.asc())
    )
    categories = res.scalars().all()
    return {
        "status": "success",
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "parent_id": c.parent_id,
                "referral_commission_rate": c.referral_commission_rate
            }
            for c in categories
        ]
    }


@router.put("/admin/category-rates/{category_id}")
async def update_admin_category_rate(
    category_id: int,
    payload: CategoryRateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update referral commission rate for a category."""
    res = await db.execute(
        select(CategoryModel).where(CategoryModel.id == category_id)
    )
    category = res.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")

    category.referral_commission_rate = payload.referral_commission_rate
    await db.commit()
    await db.refresh(category)

    return {
        "status": "success",
        "message": f"Updated referral commission rate for {category.name}",
        "category_id": category.id,
        "referral_commission_rate": category.referral_commission_rate
    }

