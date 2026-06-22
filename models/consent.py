from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class ConsentLog(Base):
    """
    Tracks user consent for data processing, marketing, and terms of service.
    Required for GDPR and DPDP Act compliance.
    """
    __tablename__ = "consent_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=True, index=True)
    
    consent_type = Column(String, nullable=False, index=True) # e.g., 'marketing', 'data_processing', 'tos_v1'
    status = Column(String, nullable=False) # 'granted', 'withdrawn'
    
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    customer = relationship("CustomerUser", foreign_keys=[customer_id])
