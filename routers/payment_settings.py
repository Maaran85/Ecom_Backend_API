"""
Platform-level Payment Settings (Admin only)
All UPI / online payment configurations go here.
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.permissions import require_admin
from models.user import User
from models.payment_settings import PlatformPaymentSettings

router = APIRouter(prefix="/admin/payment-settings", tags=["payment-settings"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class PaymentSettingCreate(BaseModel):
    provider_name: str
    provider_type: str                      # upi | razorpay | stripe | paytm | other
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    merchant_id: Optional[str] = None
    upi_vpa: Optional[str] = None
    webhook_secret: Optional[str] = None
    is_live: bool = False
    is_active: bool = True
    platform_fee_amount: float = 0.0


class PaymentSettingUpdate(BaseModel):
    provider_name: Optional[str] = None
    provider_type: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    merchant_id: Optional[str] = None
    upi_vpa: Optional[str] = None
    webhook_secret: Optional[str] = None
    is_live: Optional[bool] = None
    is_active: Optional[bool] = None
    platform_fee_amount: Optional[float] = None


def _serialize(s: PlatformPaymentSettings) -> dict:
    return {
        "id": s.id,
        "provider_name": s.provider_name,
        "provider_type": s.provider_type,
        # Mask secrets in list responses
        "api_key": ("*" * 8 + s.api_key[-4:]) if s.api_key and len(s.api_key) > 4 else s.api_key,
        "api_secret": "••••••••" if s.api_secret else None,
        "merchant_id": s.merchant_id,
        "upi_vpa": s.upi_vpa,
        "webhook_secret": "••••••••" if s.webhook_secret else None,
        "is_live": s.is_live,
        "is_active": s.is_active,
        "platform_fee_amount": s.platform_fee_amount,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_payment_settings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(PlatformPaymentSettings).order_by(PlatformPaymentSettings.id))
    settings = result.scalars().all()
    return [_serialize(s) for s in settings]


@router.post("", status_code=201)
async def create_payment_setting(
    payload: PaymentSettingCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    setting = PlatformPaymentSettings(**payload.model_dump())
    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return _serialize(setting)


@router.get("/{setting_id}")
async def get_payment_setting(
    setting_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlatformPaymentSettings).where(PlatformPaymentSettings.id == setting_id)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Payment setting not found")
    # Return full (unmasked) for single-fetch
    return {
        "id": setting.id,
        "provider_name": setting.provider_name,
        "provider_type": setting.provider_type,
        "api_key": setting.api_key,
        "api_secret": setting.api_secret,
        "merchant_id": setting.merchant_id,
        "upi_vpa": setting.upi_vpa,
        "webhook_secret": setting.webhook_secret,
        "is_live": setting.is_live,
        "is_active": setting.is_active,
        "platform_fee_amount": setting.platform_fee_amount,
        "created_at": setting.created_at,
        "updated_at": setting.updated_at,
    }


@router.patch("/{setting_id}")
async def update_payment_setting(
    setting_id: int,
    payload: PaymentSettingUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlatformPaymentSettings).where(PlatformPaymentSettings.id == setting_id)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Payment setting not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(setting, field, value)
    await db.commit()
    await db.refresh(setting)
    return _serialize(setting)


@router.put("/{setting_id}/toggle")
async def toggle_payment_setting(
    setting_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlatformPaymentSettings).where(PlatformPaymentSettings.id == setting_id)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Payment setting not found")
    setting.is_active = not setting.is_active
    await db.commit()
    await db.refresh(setting)
    return {"is_active": setting.is_active, "message": f"{setting.provider_name} is now {'active' if setting.is_active else 'inactive'}"}


@router.delete("/{setting_id}")
async def delete_payment_setting(
    setting_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PlatformPaymentSettings).where(PlatformPaymentSettings.id == setting_id)
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Payment setting not found")
    await db.delete(setting)
    await db.commit()
    return {"message": f"{setting.provider_name} deleted successfully"}
