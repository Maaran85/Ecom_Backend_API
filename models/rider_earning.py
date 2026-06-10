from sqlalchemy import Column, Integer, Float, ForeignKey, String, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class RiderEarning(Base):
    __tablename__ = "rider_earnings"

    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("delivery_riders.id"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=True) # If linked to a specific delivery
    
    amount = Column(Float, nullable=False)
    type = Column(String, default="delivery") # delivery, bonus, deduction, payout
    status = Column(String, default="earned") # earned, paid_out, cancelled
    
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    rider = relationship("DeliveryRider", backref="earnings")
    order_item = relationship("OrderItem", backref="rider_earnings")
