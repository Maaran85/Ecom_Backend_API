import enum
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from core.database import Base
from core.enums import TDSThresholdStrategy


class TDSConfiguration(Base):
    """
    TDS rate matrix per organization type (Sec 194-O), configurable by admins.

    One row per organization_type. Each row holds:
      - TDS rate with PAN
      - Exemption limit with PAN (NULL = no exemption, e.g. Company/LLP/Pvt Ltd)
      - TDS rate without PAN
      - Exemption limit without PAN (Excel: Nill -> NULL)
    """
    __tablename__ = "tds_configurations"

    id = Column(Integer, primary_key=True, index=True)

    section = Column(String, default="194-O", nullable=False)  # Income Tax Act section

    # Organization type this rule applies to (see core.enums.OrganizationType)
    organization_type = Column(String, nullable=False, index=True)

    # --- With PAN ---
    tds_rate_with_pan = Column(Float, default=0.001, nullable=False)          # 0.1%
    exemption_limit_with_pan = Column(Float, nullable=True)                    # 500000; NULL = no exemption

    # --- Without PAN ---
    tds_rate_without_pan = Column(Float, default=0.05, nullable=False)         # 5%
    exemption_limit_without_pan = Column(Float, nullable=True)                 # NULL = no exemption

    # Threshold crossing behaviour (configurable per rule)
    threshold_strategy = Column(
        SQLEnum(TDSThresholdStrategy),
        default=TDSThresholdStrategy.PROSPECTIVE,
        nullable=False,
    )

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<TDSConfiguration {self.organization_type} rate_with_pan={self.tds_rate_with_pan}>"
