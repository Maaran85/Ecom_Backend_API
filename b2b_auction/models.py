from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
import enum

from core.database import Base

class B2BAuctionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class B2BRegistrationType(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"

class B2BOrderStatus(str, enum.Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    DISPATCHED = "DISPATCHED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

class B2BAuctionItem(Base):
    __tablename__ = "b2b_auction_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    b2b_product_id = Column(UUID(as_uuid=True), ForeignKey("b2b_products.id"), nullable=False)
    
    # Creator of the auction (partner)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    
    qty = Column(Integer, default=1, nullable=False)
    
    base_price = Column(Float, nullable=False)
    current_highest_bid = Column(Float, default=0.0)
    min_bid_qty = Column(Integer, default=1, nullable=False)
    min_bid_amount = Column(Float, default=0.0)
    
    registration_type = Column(Enum(B2BRegistrationType), default=B2BRegistrationType.FREE, nullable=False)
    deposit_amount = Column(Float, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    status = Column(Enum(B2BAuctionStatus), default=B2BAuctionStatus.PENDING)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    bids = relationship("B2BAuctionBid", back_populates="auction", cascade="all, delete-orphan")
    registrations = relationship("B2BAuctionRegistration", back_populates="auction", cascade="all, delete-orphan")
    partner = relationship("Partner")
    b2b_product = relationship("B2BProduct")

    @property
    def product(self):
        return self.b2b_product

class B2BAuctionBid(Base):
    __tablename__ = "b2b_auction_bids"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    auction_id = Column(UUID(as_uuid=True), ForeignKey("b2b_auction_items.id"), nullable=False)
    # Dealer is bidding
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False)
    
    bid_amount = Column(Float, nullable=False)
    bid_qty = Column(Integer, nullable=False)
    allocated_qty = Column(Integer, default=0)
    is_winning = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    auction = relationship("B2BAuctionItem", back_populates="bids")
    dealer = relationship("Dealer")

    @property
    def dealer_name(self):
        if self.dealer:
            return getattr(self.dealer, "business_name", None) or f"Dealer #{getattr(self.dealer, 'user_id', '')}"
        return None

class B2BAuctionRegistration(Base):
    __tablename__ = "b2b_auction_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    auction_id = Column(UUID(as_uuid=True), ForeignKey("b2b_auction_items.id"), nullable=False)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False)
    
    registered_qty = Column(Integer, default=1, nullable=False)
    deposit_paid = Column(Float, default=0.0, nullable=False)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    auction = relationship("B2BAuctionItem", back_populates="registrations")
    dealer = relationship("Dealer")

    __table_args__ = (
        UniqueConstraint("auction_id", "dealer_id", name="uq_b2b_auction_dealer_registration"),
    )

class B2BProduct(Base):
    __tablename__ = "b2b_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    images = Column(Text, nullable=True)
    
    brand = Column(String(100), nullable=True)
    specification = Column(Text, nullable=True)
    warranty = Column(String(100), nullable=True)
    support = Column(String(100), nullable=True)
    is_returnable = Column(Boolean, default=False, nullable=False)
    is_exchangeable = Column(Boolean, default=False, nullable=False)
    
    base_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    partner = relationship("Partner")

class B2BOrder(Base):
    __tablename__ = "b2b_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    
    auction_id = Column(UUID(as_uuid=True), ForeignKey("b2b_auction_items.id"), nullable=False)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False)
    b2b_product_id = Column(UUID(as_uuid=True), ForeignKey("b2b_products.id"), nullable=False)
    
    total_qty = Column(Integer, nullable=False, default=0)
    total_amount = Column(Float, nullable=False, default=0.0)
    deposit_applied = Column(Float, nullable=False, default=0.0)
    balance_due = Column(Float, nullable=False, default=0.0)
    
    payment_status = Column(String(50), default="PENDING_PAYMENT") # PENDING_PAYMENT, PAID, PARTIALLY_PAID
    order_status = Column(Enum(B2BOrderStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=B2BOrderStatus.PENDING_CONFIRMATION)
    
    shipping_address = Column(Text, nullable=True)
    courier_company = Column(String(255), nullable=True)
    tracking_number = Column(String(255), nullable=True)
    
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    auction = relationship("B2BAuctionItem")
    partner = relationship("Partner")
    dealer = relationship("Dealer")
    b2b_product = relationship("B2BProduct")
    items = relationship("B2BOrderItem", back_populates="order", cascade="all, delete-orphan")

class B2BOrderItem(Base):
    __tablename__ = "b2b_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("b2b_orders.id"), nullable=False, index=True)
    bid_id = Column(UUID(as_uuid=True), ForeignKey("b2b_auction_bids.id"), nullable=False)
    
    qty = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    order = relationship("B2BOrder", back_populates="items")
    bid = relationship("B2BAuctionBid")

