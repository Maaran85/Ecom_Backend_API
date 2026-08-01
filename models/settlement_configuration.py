from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from core.database import Base


class SettlementConfiguration(Base):
    """
    Singleton platform-level settlement settings (single row, id=1).

    Keeps the settlement engine config-driven: return window, engine version,
    auto-run flag. Used by BOTH settlement eligibility and return-window
    validation (replaces the hardcoded 7 days).
    """
    __tablename__ = "settlement_configurations"

    id = Column(Integer, primary_key=True)  # always 1

    return_window_days = Column(Integer, default=14, nullable=False)
    settlement_version = Column(String, default="1.0", nullable=False)
    max_orders_per_settlement = Column(Integer, default=1000, nullable=False)
    is_daily_auto_enabled = Column(Boolean, default=True, nullable=False)

    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SettlementConfiguration version={self.settlement_version} return_window={self.return_window_days} days>"
