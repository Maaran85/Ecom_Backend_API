from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from pydantic import BaseModel
from datetime import datetime
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
