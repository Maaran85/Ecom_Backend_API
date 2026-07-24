import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    FREE_SHIPPING = "free_shipping"

class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id", ondelete="CASCADE"), nullable=True) # Null = Admin/Global
    code = Column(String, unique=True, nullable=False, index=True)  # e.g., "SAVE20"
    description = Column(String, nullable=True)
    
    # Discount details
    discount_type = Column(SQLEnum(DiscountType), nullable=False)
    discount_value = Column(Float, nullable=False)  # 20 for 20% or ₹20
    
    # Restrictions
    min_order_value = Column(Float, default=0.0)
    max_discount_amount = Column(Float, nullable=True)  # Cap for percentage discounts
    
    # Usage limits
    usage_limit = Column(Integer, nullable=True)  # Total uses allowed (null = unlimited)
    usage_per_user = Column(Integer, default=1)  # Per user limit
    current_usage = Column(Integer, default=0)
    
    # Validity
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Applicability
    applicable_categories = Column(JSON, nullable=True)  # List of category IDs
    applicable_products = Column(JSON, nullable=True)  # List of product IDs
    first_order_only = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    usages = relationship("CouponUsage", back_populates="coupon", cascade="all, delete-orphan")

class CouponUsage(Base):
    __tablename__ = "coupon_usage"

    id = Column(Integer, primary_key=True, index=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    discount_amount = Column(Float, nullable=False)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    coupon = relationship("Coupon", back_populates="usages")
    user = relationship("User", backref="coupon_usages")
    order = relationship("Order", backref="coupon_usage")
