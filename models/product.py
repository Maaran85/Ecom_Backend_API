from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    products = relationship("Product", back_populates="category")
    attributes = relationship("CategoryAttribute", back_populates="category", cascade="all, delete-orphan")

class CategoryAttribute(Base):
    __tablename__ = "category_attributes"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g., "RAM", "Fabric"
    is_mandatory = Column(Boolean, default=True, nullable=False)
    datatype = Column(String, default="string", nullable=False) # string, number, array
    allowed_values = Column(JSON, nullable=True) 
    
    category = relationship("Category", back_populates="attributes")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    discount_price = Column(Float, nullable=True)
    discount_percentage = Column(Integer, nullable=True)  # For filter: 10%, 20%, 30%, etc.
    stock = Column(Integer, default=0, nullable=False)
    average_rating = Column(Float, nullable=True, default=0.0)  # Calculated from reviews
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    subcategory = Column(String, nullable=False, index=True)  # Topwear, Bottomwear, Footwear, etc.
    dealer_id = Column(Integer, ForeignKey("dealers.id"), nullable=False, index=True)  # All products must belong to a dealer
    is_approved = Column(Boolean, default=False, nullable=False)
    has_variants = Column(Boolean, default=False, nullable=False)
    images = Column(JSON, nullable=False, default=[])  # Store as JSON array of image URLs
    
    # Filter fields
    gender = Column(String, nullable=False, index=True)  # Men, Women, Kids, Unisex
    brand = Column(String, nullable=False, index=True)  # Nike, Adidas, Puma, etc.
    color = Column(String, nullable=True, index=True)  # Black, White, Blue, etc.
    sizes = Column(JSON, nullable=False)  # Available sizes: ["S", "M", "L", "XL"]
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

    @property
    def dealer_delivery_days(self):
        if self.dealer:
            return self.dealer.estimated_delivery_days
        return None
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    category = relationship("Category", back_populates="products")
    dealer = relationship("Dealer", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
