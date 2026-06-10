from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class FlashSale(Base):
    __tablename__ = "flash_sales"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # "Weekend Sale", "Diwali Mega Sale"
    description = Column(String, nullable=True)
    
    # Discount
    discount_percentage = Column(Float, nullable=False)  # 30 for 30% off
    
    # Time period
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    # Applicability
    product_ids = Column(JSON, nullable=True)  # List of specific product IDs
    category_ids = Column(JSON, nullable=True)  # Or entire categories
    dealer_id = Column(Integer, ForeignKey("dealers.id", ondelete="CASCADE"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
