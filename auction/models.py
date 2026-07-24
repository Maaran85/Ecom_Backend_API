from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone
import enum

from core.database import Base

class AuctionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class RegistrationType(str, enum.Enum):
    FREE = "FREE"
    PAID = "PAID"

class AuctionItem(Base):
    __tablename__ = "auction_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Mandatory link to existing catalog product
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    
    # Creator of the auction (dealer or admin)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=True)
    
    # Hub that the stock is physically reserved from
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id"), nullable=True)
    
    qty = Column(Integer, default=1, nullable=False)
    
    base_price = Column(Float, nullable=False)
    current_highest_bid = Column(Float, default=0.0)
    min_bid_qty = Column(Integer, default=1, nullable=False)
    min_bid_amount = Column(Float, default=0.0)
    max_bidders = Column(Integer, default=100, nullable=False)
    
    # Registration type: FREE (anyone can bid) or PAID (must pay deposit first)
    registration_type = Column(Enum(RegistrationType), default=RegistrationType.FREE, nullable=False)
    deposit_amount = Column(Float, nullable=True)  # Required when registration_type = PAID
    
    start_time = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    status = Column(Enum(AuctionStatus), default=AuctionStatus.PENDING)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    bids = relationship("AuctionBid", back_populates="auction", cascade="all, delete-orphan")
    registrations = relationship("AuctionRegistration", back_populates="auction", cascade="all, delete-orphan")
    dealer = relationship("Dealer")
    product = relationship("Product")

class AuctionBid(Base):
    __tablename__ = "auction_bids"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    auction_id = Column(UUID(as_uuid=True), ForeignKey("auction_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False)
    
    bid_amount = Column(Float, nullable=False)
    bid_qty = Column(Integer, nullable=False)
    allocated_qty = Column(Integer, default=0)
    is_winning = Column(Boolean, default=False)
    
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    auction = relationship("AuctionItem", back_populates="bids")
    user = relationship("CustomerUser")

class AuctionRegistration(Base):
    """Tracks customers who have registered (and optionally paid deposit) to participate in an auction."""
    __tablename__ = "auction_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    auction_id = Column(UUID(as_uuid=True), ForeignKey("auction_items.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False)
    
    deposit_paid = Column(Float, default=0.0, nullable=False)  # 0.0 for FREE registrations
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    auction = relationship("AuctionItem", back_populates="registrations")
    user = relationship("CustomerUser")

    __table_args__ = (
        UniqueConstraint("auction_id", "user_id", name="uq_auction_user_registration"),
    )
