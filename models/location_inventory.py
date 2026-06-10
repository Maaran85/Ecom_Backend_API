from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class LocationInventory(Base):
    """Track stock levels at specific locations (Hubs/Showrooms)"""
    __tablename__ = "location_inventory"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    quantity = Column(Integer, default=0, nullable=False)
    
    # Audit timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Relationships
    product = relationship("Product", backref="location_inventories")
    hub = relationship("DeliveryHub", backref="location_inventories")
