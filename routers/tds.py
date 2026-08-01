from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.permissions import require_admin
from models import User
from models.tds_configuration import TDSConfiguration
from models.fee_configuration import FeeConfiguration
from models.settlement_configuration import SettlementConfiguration
from schemas.tds import (
    TDSConfigurationCreate, TDSConfigurationUpdate, TDSConfigurationOut,
)
from schemas.fee import (
    FeeConfigurationCreate, FeeConfigurationUpdate, FeeConfigurationOut,
)
from services.audit import log_audit
from services.configuration_service import (
    ensure_default_configurations,
    get_settlement_configuration,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# TDS Configuration
# ---------------------------------------------------------------------------

@router.get("/admin/tds-configurations", response_model=List[TDSConfigurationOut])
async def list_tds_configurations(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(TDSConfiguration).order_by(TDSConfiguration.organization_type))
    return result.scalars().all()


@router.post("/admin/tds-configurations", response_model=TDSConfigurationOut, status_code=status.HTTP_201_CREATED)
async def create_tds_configuration(
    data: TDSConfigurationCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = await db.execute(
        select(TDSConfiguration).where(TDSConfiguration.organization_type == data.organization_type)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"TDS configuration for '{data.organization_type}' already exists",
        )
    config = TDSConfiguration(section=data.section, **data.model_dump(exclude={"section"}))
    db.add(config)
    await db.flush()
    await log_audit(
        db, admin, "CREATE", "tds_configuration",
        resource_id=str(config.id),
        new_values={"organization_type": config.organization_type, **data.model_dump()},
    )
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/admin/tds-configurations/{config_id}", response_model=TDSConfigurationOut)
async def update_tds_configuration(
    config_id: int,
    data: TDSConfigurationUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    config = await db.get(TDSConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="TDS configuration not found")

    old = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    await db.flush()
    new = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    await log_audit(
        db, admin, "UPDATE", "tds_configuration",
        resource_id=str(config.id),
        old_values=old, new_values=new,
    )
    await db.commit()
    await db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# Fee Configuration
# ---------------------------------------------------------------------------

@router.get("/admin/fee-configurations", response_model=List[FeeConfigurationOut])
async def list_fee_configurations(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(FeeConfiguration).order_by(FeeConfiguration.key))
    return result.scalars().all()


@router.post("/admin/fee-configurations", response_model=FeeConfigurationOut, status_code=status.HTTP_201_CREATED)
async def create_fee_configuration(
    data: FeeConfigurationCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = await db.execute(
        select(FeeConfiguration).where(FeeConfiguration.key == data.key)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Fee configuration '{data.key}' already exists")
    config = FeeConfiguration(**data.model_dump())
    db.add(config)
    await db.flush()
    await log_audit(db, admin, "CREATE", "fee_configuration", resource_id=str(config.id), new_values=data.model_dump())
    await db.commit()
    await db.refresh(config)
    return config


@router.put("/admin/fee-configurations/{config_id}", response_model=FeeConfigurationOut)
async def update_fee_configuration(
    config_id: int,
    data: FeeConfigurationUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    config = await db.get(FeeConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Fee configuration not found")

    old = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(config, field, value)

    await db.flush()
    new = {c.name: getattr(config, c.name) for c in config.__table__.columns}
    await log_audit(db, admin, "UPDATE", "fee_configuration", resource_id=str(config.id), old_values=old, new_values=new)
    await db.commit()
    await db.refresh(config)
    return config


# ---------------------------------------------------------------------------
# Settlement Configuration (singleton)
# ---------------------------------------------------------------------------

@router.get("/admin/settlement-config")
async def get_settlement_config(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    config = await get_settlement_configuration(db)
    return {
        "return_window_days": config.return_window_days,
        "settlement_version": config.settlement_version,
        "max_orders_per_settlement": config.max_orders_per_settlement,
        "is_daily_auto_enabled": config.is_daily_auto_enabled,
    }


@router.put("/admin/settlement-config")
async def update_settlement_config(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    allowed = {
        "return_window_days", "settlement_version",
        "max_orders_per_settlement", "is_daily_auto_enabled",
    }
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {sorted(unknown)}")

    config = await get_settlement_configuration(db)
    old = {c.name: getattr(config, c.name) for c in config.__table__.columns if c.name != "id"}
    for key, value in payload.items():
        setattr(config, key, value)

    await db.flush()
    await log_audit(db, admin, "UPDATE", "settlement_configuration", resource_id="1", old_values=old, new_values=payload)
    await db.commit()

    return {
        "return_window_days": config.return_window_days,
        "settlement_version": config.settlement_version,
        "max_orders_per_settlement": config.max_orders_per_settlement,
        "is_daily_auto_enabled": config.is_daily_auto_enabled,
    }


# ---------------------------------------------------------------------------
# Startup seeding endpoint (admin may re-run to seed defaults)
# ---------------------------------------------------------------------------

@router.post("/admin/configurations/seed")
async def seed_configurations(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    await ensure_default_configurations(db)
    await db.commit()
    return {"status": "ok", "message": "Default configurations ensured"}
