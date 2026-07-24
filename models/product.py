from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from core.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    is_spec_group = Column(Boolean, default=False, nullable=False)
    referral_commission_rate = Column(Float, nullable=True)  # e.g. 5.0 for 5%; None = inherit from parent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    products = relationship("Product", back_populates="category", foreign_keys="[Product.category_id]")
    attributes = relationship("CategoryAttribute", back_populates="category", cascade="all, delete-orphan")

class CategoryAttribute(Base):
    __tablename__ = "category_attributes"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g., "RAM", "Fabric"
    is_mandatory = Column(Boolean, default=True, nullable=False)
    is_variant_key = Column(Boolean, default=False, nullable=False) # True if used to define variants (e.g. Size, Color)
    datatype = Column(String, default="string", nullable=False) # string, number, array
    allowed_values = Column(JSON, nullable=True) 
    unit = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_filter = Column(Boolean, default=False, nullable=False)
    
    category = relationship("Category", back_populates="attributes")

class Brand(Base):
    __tablename__ = "brands"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    logo_url = Column(String, nullable=True)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    products = relationship("Product", back_populates="brand")

class SubcategoryBrand(Base):
    __tablename__ = "subcategory_brands"
    
    subcategory_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True)

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    dealer_price = Column(Float, nullable=False) # Previously 'MRP (Excl Tax)'
    selling_price = Column(Float, nullable=True) # Previously 'discount_price'
    mrp = Column(Float, nullable=True) # 'MRP (Incl Tax)'
    discount_price = Column(Float, nullable=True) # Raw discount amount
    tax_perc = Column(Float, nullable=True)
    tax_price = Column(Float, nullable=True)
    discount_percentage = Column(Integer, nullable=True)  # For filter: 10%, 20%, 30%, etc.
    # stock column removed, replaced by dynamic column_property at the bottom
    average_rating = Column(Float, nullable=True, default=0.0)  # Calculated from reviews
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    subcategory_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False, index=True)  # All products must belong to a dealer
    is_approved = Column(Boolean, default=False, nullable=False)
    reject_reasons = Column(JSON, nullable=True, default=[])
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    # Variant Support (Parent-Child)
    parent_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)
    images = Column(JSON, nullable=False, default=[])  # Store as JSON array of image URLs
    
    # Filter fields
    sku = Column(String, nullable=True, unique=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True, index=True)  # Temporarily nullable for migration
    attributes = Column(JSON, nullable=True) # Dynamic properties specific to category. e.g. {"RAM": "8GB"}
    
    # Return & Exchange Policy
    is_returnable = Column(Boolean, default=True, nullable=False)
    return_window_days = Column(Integer, default=14, nullable=False)  # e.g. 7, 14, 30
    is_exchangeable = Column(Boolean, default=True, nullable=False)
    return_policy_note = Column(String, nullable=True)  # Custom dealer note e.g. "Innerwear non-returnable"
    estimated_delivery_days = Column(Integer, nullable=True) # Override dealer value if set

    # Tax & Compliance
    hsn_code = Column(String, nullable=False)   # for GST invoice compliance
    tax_rule_id = Column(Integer, ForeignKey("tax_rules.id"), nullable=False)
    referral_commission_rate = Column(Float, nullable=True)  # Product-level referral override rate

    @property
    def dealer_delivery_days(self):
        if self.dealer:
            return self.dealer.estimated_delivery_days
        return None
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    category = relationship("Category", back_populates="products", foreign_keys=[category_id])
    brand = relationship("Brand", back_populates="products", lazy="selectin")
    subcategory = relationship("Category", foreign_keys=[subcategory_id])
    dealer = relationship("Dealer", back_populates="products")
    children = relationship("Product", backref=backref('parent', remote_side=[id]))
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")


