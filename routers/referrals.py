from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import secrets
import string

from core.database import get_db
from core.permissions import get_current_active_user
from models.customer_user import CustomerUser
from models.product import Category as CategoryModel
from models.referral import (
    CustomerReferralProfile,
    ReferralOrderCommission,
    ReferralItemCommission,
    CustomerWallet,
    CommissionStatus
)

router = APIRouter(prefix="/api/referrals", tags=["Referrals"])


class ApplyCodeRequest(BaseModel):
    referral_code: str


class CategoryRateUpdate(BaseModel):
    referral_commission_rate: Optional[float] = None


def _generate_referral_code(customer_id: int) -> str:
    rand_suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"REF{customer_id}{rand_suffix}"


@router.get("/my-profile")
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

    # Check existing wallet
    res_wallet = await db.execute(
        select(CustomerWallet).where(CustomerWallet.customer_id == customer_id)
    )
    wallet = res_wallet.scalar_one_or_none()

    if not wallet:
        wallet = CustomerWallet(
            customer_id=customer_id,
            available_balance=0.0,
            lifetime_earned=0.0
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

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
        "available_balance": wallet.available_balance,
        "lifetime_earned": wallet.lifetime_earned
    }


@router.get("/wallet-transactions")
async def get_wallet_transactions(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve complete credit & debit history for the customer's wallet."""
    from models.referral import WalletTransaction
    res = await db.execute(
        select(WalletTransaction)
        .where(WalletTransaction.customer_id == int(current_user.id))
        .order_by(WalletTransaction.created_at.desc())
    )
    transactions = res.scalars().all()
    return [
        {
            "id": t.id,
            "amount": t.amount,
            "transaction_type": t.transaction_type.value if hasattr(t.transaction_type, 'value') else t.transaction_type,
            "description": t.description,
            "order_id": t.order_id,
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
                        "commission_amount": i.commission_amount,
                        "status": i.status.value if hasattr(i.status, "value") else i.status,
                    }
                    for i in c.items
                ]
            }
            for c in commissions
        ]
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
