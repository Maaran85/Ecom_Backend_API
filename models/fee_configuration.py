import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from core.database import Base
from core.enums import FeeType


class FeeConfiguration(Base):
    """
    Configurable settlement fees (marketplace/marketing/shipping etc).

    The settlement engine ALWAYS reads fees from this table and snapshots the
    applied value into each settlement for historical accuracy. No hardcoded
    values in the engine.
    """
    __tablename__ = "fee_configurations"

    id = Column(Integer, primary_key=True, index=True)

    key = Column(String, nullable=False, unique=True, index=True)  # e.g. marketplace_fee, marketing_fee
    name = Column(String, nullable=True)
    description = Column(String, nullable=True)

    # percentage (of gross sale) or flat (fixed amount per order item)
    fee_type = Column(SQLEnum(FeeType), default=FeeType.FLAT, nullable=False)
    value = Column(Float, default=0.0, nullable=False)  # 25.0 = flat ₹25/item; 0.05 = 5% of gross

    # Whether GST applies on top of this fee (billing sheet: 18% on fees)
    is_gst_applicable = Column(Boolean, default=False, nullable=False)
    gst_rate = Column(Float, default=0.0, nullable=False)  # snapshot of GST rate applied

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FeeConfiguration {self.key} type={self.fee_type.value} value={self.value}>"
