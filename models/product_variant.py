from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String, unique=True, nullable=False, index=True)  # Stock Keeping Unit
    
    # Variant attributes
    size = Column(String, nullable=True)  # S, M, L, XL, XXL, 28, 30, 32, etc.
    color = Column(String, nullable=True)  # Red, Blue, Black, etc.
    material = Column(String, nullable=True)  # Cotton, Polyester, etc.
    
    # Pricing and inventory
    price_adjustment = Column(Float, default=0.0)  # +/- from base product price
    stock = Column(Integer, default=0, nullable=False)
    
    # Variant-specific images
    images = Column(JSON, nullable=True)  # Array of image URLs for this variant
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product")
    
    # Ensure unique combination of product + size + color
    __table_args__ = (
        UniqueConstraint('product_id', 'size', 'color', name='uq_product_size_color'),
    )
