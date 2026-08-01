import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class DealerFinancialYearSummary(Base):
    """
    Running FY totals per dealer used for TDS exemption threshold tracking.

    Updated on each settled period so the threshold check is O(1) and the
    history is auditable.
    """
    __tablename__ = "dealer_financial_year_summaries"

    id = Column(Integer, primary_key=True, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=False, index=True)

    financial_year = Column(String, nullable=False, index=True)  # e.g. "2026-2027"
    fy_start_date = Column(Date, nullable=False)
    fy_end_date = Column(Date, nullable=False)

    cumulative_gross_sale = Column(Float, default=0.0, nullable=False)   # cumulative TDS base (gross sale) for the FY
    cumulative_tds_exempt = Column(Float, default=0.0, nullable=False)   # portion shielded by the exemption limit
    cumulative_tds_applied = Column(Float, default=0.0, nullable=False)  # base on which TDS actually applied
    cumulative_tds_amount = Column(Float, default=0.0, nullable=False)   # total TDS deducted so far
    total_settlements = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("dealer_id", "financial_year", name="uq_dealer_fy"),
    )

    # Relationships
    dealer = relationship("Dealer", backref="fy_summaries")

    def __repr__(self) -> str:
        return f"<DealerFinancialYearSummary dealer={self.dealer_id} fy={self.financial_year} gross={self.cumulative_gross_sale}>"
