from sqlalchemy import Column, Integer, Text, ForeignKey, Float, DateTime, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class RiderReview(Base):
    __tablename__ = "rider_reviews"

    id = Column(Integer, primary_key=True, index=True)
    rider_id = Column(Integer, ForeignKey("delivery_riders.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True)
    
    # Review content
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    rider = relationship("DeliveryRider", backref="reviews")
    user = relationship("User", backref="rider_reviews")
    order_item = relationship("OrderItem", backref="rider_reviews")
    
    # Constraint: rating must be between 1 and 5
    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rider_rating_range'),
    )
