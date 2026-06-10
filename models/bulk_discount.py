from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.sql import func
from core.database import Base

class BulkDiscount(Base):
    __tablename__ = "bulk_discounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # "Buy 3 Get 10% Off"
    description = Column(String, nullable=True)
    
    # Quantity-based discount
    min_quantity = Column(Integer, nullable=False)  # Minimum items to qualify
    discount_percentage = Column(Float, nullable=False)  # Discount to apply
    
    # Applicability (one of these should be set)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
