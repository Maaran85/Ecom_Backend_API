from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class AddressType(str, enum.Enum):
    HOME = "home"
    WORK = "work"
    OTHER = "other"

class Address(Base):
    __tablename__ = "addresses"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=False)
    
    # Contact information
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    
    # Address details
    address_line1 = Column(String, nullable=False)
    address_line2 = Column(String, nullable=True)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    pincode = Column(String, nullable=False)
    country = Column(String, default="India", nullable=False)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    
    # Address metadata
    address_type = Column(SQLEnum(AddressType), default=AddressType.HOME, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    customer = relationship("CustomerUser", backref="addresses")
