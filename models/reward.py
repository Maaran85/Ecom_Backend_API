from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from core.database import Base
import enum


class SpinSource(str, enum.Enum):
    ORDER = "order"
    RECHARGE = "recharge"
    BILL = "bill"


class SpinConfig(Base):
    """Admin-controlled settings for the spin game."""
    __tablename__ = "spin_configs"

    id = Column(Integer, primary_key=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    top_x_winners = Column(Integer, default=10, nullable=False)       # e.g. top 10 winners
    spins_per_order = Column(Integer, default=1, nullable=False)
    spins_per_recharge = Column(Integer, default=1, nullable=False)
    spins_per_bill = Column(Integer, default=1, nullable=False)
    min_rank = Column(Integer, default=1, nullable=False)              # lowest rank number on wheel
    max_rank = Column(Integer, default=100, nullable=False)            # highest rank number on wheel
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class SpinToken(Base):
    """Unplayed spin tokens granted to customers."""
    __tablename__ = "spin_tokens"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    source = Column(Enum(SpinSource), nullable=False)
    source_ref_id = Column(Integer, nullable=True)          # order_id / recharge_id / bill_id
    is_played = Column(Boolean, default=False, nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)
    played_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("CustomerUser", backref="spin_tokens")


class SpinResult(Base):
    """Record of each spin played by a customer."""
    __tablename__ = "spin_results"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("spin_tokens.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    rank_earned = Column(Integer, nullable=False)                      # random number from wheel
    source = Column(Enum(SpinSource), nullable=False)
    month_year = Column(String(7), nullable=False, index=True)        # e.g. "2026-03"
    spun_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    customer = relationship("CustomerUser", backref="spin_results")
    token = relationship("SpinToken", backref="result")


class RewardPrize(Base):
    """Prize catalog per rank position for a month."""
    __tablename__ = "reward_prizes"

    id = Column(Integer, primary_key=True, index=True)
    month_year = Column(String(7), nullable=False, index=True)        # e.g. "2026-03"
    rank_position = Column(Integer, nullable=False)                    # 1 = 1st place, 2 = 2nd, …
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    prize_value = Column(Float, nullable=True)                         # monetary value in ₹
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class MonthlyLeaderboard(Base):
    """Announced winner records at month end."""
    __tablename__ = "monthly_leaderboard"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    month_year = Column(String(7), nullable=False, index=True)
    final_rank = Column(Integer, nullable=False)                       # leaderboard position (1, 2, 3…)
    total_score = Column(Integer, nullable=False)                      # sum of rank_earned values
    total_spins = Column(Integer, nullable=False, default=0)
    prize_id = Column(Integer, ForeignKey("reward_prizes.id"), nullable=True)
    announced_at = Column(DateTime, nullable=True)
    is_announced = Column(Boolean, default=False)

    # Relationships
    customer = relationship("CustomerUser", backref="leaderboard_entries")
    prize = relationship("RewardPrize")

class RewardSessionStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ANNOUNCED = "announced"

class RewardSession(Base):
    """Monthly record linking profit, pool and status."""
    __tablename__ = "reward_sessions"

    id = Column(Integer, primary_key=True, index=True)
    month_year = Column(String(7), nullable=False, unique=True, index=True) # e.g. "2026-03"
    net_profit = Column(Float, default=0.0)
    reward_pool = Column(Float, default=0.0)
    status = Column(Enum(RewardSessionStatus), default=RewardSessionStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class RewardConfiguration(Base):
    """Partner / Admin dynamic configuration for referral and reward rules."""
    __tablename__ = "reward_configurations"

    id = Column(Integer, primary_key=True, index=True)
    points_to_rupee_ratio = Column(Float, default=100.0, nullable=False)        # 100 pts = ₹1
    referral_amount_points = Column(Float, default=100.0, nullable=False)       # 100 pts (₹1) signup bonus (A)
    referral_qualifying_orders_count = Column(Integer, default=3, nullable=False) # 3 delivered orders to unlock bonus A
    
    # Slabs stored as JSON
    # Default purchase slabs: 1-500: 0.20%, 501-1000: 0.15%, >1001: 0.20%
    purchase_commission_slabs = Column(JSON, default=lambda: [
        {"min": 1, "max": 500, "rate_percent": 0.20},
        {"min": 501, "max": 1000, "rate_percent": 0.15},
        {"min": 1001, "max": None, "rate_percent": 0.20}
    ], nullable=False)

    # Default spin slabs: 1-500: 1 to 5, 501-1000: 6 to 10, >1001: 11 to 15
    spin_and_win_slabs = Column(JSON, default=lambda: [
        {"min": 1, "max": 500, "min_points": 1, "max_points": 5},
        {"min": 501, "max": 1000, "min_points": 6, "max_points": 10},
        {"min": 1001, "max": None, "min_points": 11, "max_points": 15}
    ], nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

