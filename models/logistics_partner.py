from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class LogisticsPartner(Base):
    __tablename__ = "logistics_partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    contact_person = Column(String, nullable=True)
    contact_number = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    
    is_internal = Column(Boolean, default=True) # True if platform's own fleet, False if 3rd party
    is_active = Column(Boolean, default=True)
    
    # Tracking configuration (for 3rd party)
    tracking_api_url = Column(String, nullable=True)
    api_key = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    riders = relationship("DeliveryRider", back_populates="partner")
    order_items = relationship("OrderItem", back_populates="logistics_partner")
    dealers = relationship("Dealer", secondary="dealer_logistics_mapping", back_populates="logistics_partners")
