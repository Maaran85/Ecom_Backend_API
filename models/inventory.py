from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from core.database import Base
import enum

class MovementType(str, enum.Enum):
    PURCHASE = "purchase"           # Order placed
    RETURN = "return"               # Product returned
    RESTOCK = "restock"             # Admin restocked
    ADJUSTMENT = "adjustment"       # Manual adjustment
    RESERVATION = "reservation"     # Stock reserved
    RELEASE = "release"             # Reservation released
    CANCELLATION = "cancellation"   # Order cancelled
    SALE = "sale"                   # Showroom sale

class StockMovement(Base):
    """Track all stock changes for audit trail"""
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    
    movement_type = Column(SQLEnum(MovementType), nullable=False)
    quantity = Column(Integer, nullable=False)  # +ve for increase, -ve for decrease
    
    # Before/After stock levels
    stock_before = Column(Integer, nullable=False)
    stock_after = Column(Integer, nullable=False)
    
    # Reference
    reference_id = Column(Integer, nullable=True)  # Order ID, Return ID, etc.
    reference_type = Column(String, nullable=True)  # "order", "return", etc.
    
    # Location
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id", ondelete="SET NULL"), nullable=True)
    
    # Who made the change
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    product = relationship("Product", backref="stock_movements")
    user = relationship("User", backref="stock_movements")
    hub = relationship("DeliveryHub", backref="stock_movements")

class ProductInventory(Base):
    __tablename__ = "product_inventories"
    
    id = Column(Integer, primary_key=True, index=True)
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    
    # Relationships
    hub = relationship("DeliveryHub", backref="inventory")
    product = relationship("Product", backref="product_inventory")

class StockReservation(Base):
    """Reserve stock when items are added to cart"""
    __tablename__ = "stock_reservations"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    
    # Reservation expiry (e.g., 15 minutes)
    reserved_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    product = relationship("Product", backref="reservations")
    user = relationship("User", backref="stock_reservations")

class StockAlert(Base):
    """Low stock alert configuration"""
    __tablename__ = "stock_alerts"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True)
    threshold = Column(Integer, default=10, nullable=False)  # Alert when stock < threshold
    
    # Alert status
    is_active = Column(Boolean, default=True, nullable=False)
    last_alerted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notification preferences
    notify_admin = Column(Boolean, default=True, nullable=False)
    notify_dealer = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product", backref="stock_alert", uselist=False)
