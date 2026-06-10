from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Date, func, Text
from sqlalchemy.orm import relationship
from core.database import Base

class LogisticsRemittance(Base):
    __tablename__ = "logistics_remittances"

    id = Column(Integer, primary_key=True, index=True)
    logistics_partner_id = Column(Integer, ForeignKey("logistics_partners.id", ondelete="CASCADE"), nullable=False)
    
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending")  # pending, completed, rejected
    
    reference_no = Column(String, nullable=True)     # UTR or Transaction ID
    payment_method = Column(String, nullable=True)   # UPI, NEFT, Cash, etc.
    payment_date = Column(Date, nullable=True)        # Actual payment transfer date
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    logistics_partner = relationship("LogisticsPartner", backref="remittances")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_admin_id])
