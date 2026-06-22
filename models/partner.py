from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from core.database import Base

class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    
    # Organization Details
    partner_name = Column(String(255), nullable=False)
    support_email = Column(String(255), nullable=True)
    support_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    pincode = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    tax_id = Column(String(100), nullable=True)
    logo_url = Column(String(500), nullable=True)
    
    # Platform Licensing
    license_key = Column(String(255), nullable=True, unique=True, index=True)
    plan_type = Column(String(50), default="Basic") # Basic, Professional, Enterprise
    valid_until = Column(DateTime(timezone=True), nullable=True)
    max_dealers = Column(Integer, default=10)
    
    # Technical / Defaults
    default_currency = Column(String(10), default="INR")
    timezone = Column(String(50), default="Asia/Kolkata")
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
