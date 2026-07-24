from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base


class TaxCategory(Base):
    """Defines a tax slab (e.g. GST 5%, GST 12%, IGST 18%)"""
    __tablename__ = "tax_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    
    # "CGST_SGST", "IGST", "VAT", "CUSTOM"
    tax_type = Column(String, default="CGST_SGST", nullable=False)
    
    cgst_rate = Column(Float, default=0.0)
    sgst_rate = Column(Float, default=0.0)
    igst_rate = Column(Float, default=0.0)
    vat_rate = Column(Float, default=0.0)
    custom_rate = Column(Float, default=0.0)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    rules = relationship("TaxRule", back_populates="tax_category")
    ledger_entries = relationship("TaxLedger", back_populates="tax_category")


class TaxRule(Base):
    """Maps a TaxCategory to a Product Category or specific Product"""
    __tablename__ = "tax_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    
    # If set, applies to all products in this category
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    # If set, applies to this specific product (overrides category rule)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    
    tax_category_id = Column(Integer, ForeignKey("tax_categories.id"), nullable=False)
    
    # Higher priority wins if both match
    priority = Column(Integer, default=0)
    
    # Optional filtering by state (e.g., specific rules for UP vs MH)
    state_code = Column(String, nullable=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    tax_category = relationship("TaxCategory", back_populates="rules")
    product_category = relationship("Category")
    # For the product relationship, we'll define it on the Product model side to avoid circular imports


class TaxLedger(Base):
    """Audit trail of all taxes collected on each order item"""
    __tablename__ = "tax_ledger"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False)
    
    tax_category_id = Column(Integer, ForeignKey("tax_categories.id"), nullable=False)
    
    taxable_amount = Column(Float, nullable=False)
    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)
    vat_amount = Column(Float, default=0.0)
    total_tax = Column(Float, nullable=False)
    
    hsn_code = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    tax_category = relationship("TaxCategory", back_populates="ledger_entries")
    order = relationship("Order")
    order_item = relationship("OrderItem")
