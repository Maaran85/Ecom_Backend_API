from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class ReturnStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    OUT_FOR_PICKUP = "OUT_FOR_PICKUP"
    OUT_FOR_SWAP = "OUT_FOR_SWAP"
    PICKED_UP = "PICKED_UP"
    PICKUP_FAILED = "PICKUP_FAILED"
    IN_TRANSIT_TO_HUB = "IN_TRANSIT_TO_HUB"
    AT_HUB = "AT_HUB"
    IN_TRANSIT_TO_STORE = "IN_TRANSIT_TO_STORE"
    RETURN_PICKUP_PROCESSING = "RETURN_PICKUP_PROCESSING"
    RETURN_PICKUP_STARTED = "RETURN_PICKUP_STARTED"
    RETURN_PICKUP_COMPLETED = "RETURN_PICKUP_COMPLETED"
    SWAP_COMPLETED = "SWAP_COMPLETED"
    EXCHANGE_COMPLETED = "EXCHANGE_COMPLETED"
    COMPLETED = "COMPLETED"
    REFUNDED = "REFUNDED"

class OrderReturn(Base):
    __tablename__ = "order_returns"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True) # For partial returns
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=False)
    
    # Return details
    reason = Column(String, nullable=False)
    description = Column(String, nullable=True)
    images = Column(JSON, nullable=True)  # Photos of product issue
    
    # Exchange details
    is_exchange = Column(Boolean, default=False, nullable=False)
    exchange_variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    replacement_order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    
    # Status
    status = Column(SQLEnum(ReturnStatus, native_enum=True), default=ReturnStatus.REQUESTED, nullable=False)
    pickup_attempts = Column(Integer, default=0, nullable=False)
    
    # Admin response
    admin_notes = Column(String, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Refund
    refund_amount = Column(Float, nullable=True)
    refund_initiated = Column(Boolean, default=False, nullable=False)
    refund_mode = Column(String, nullable=True)      # upi, bank_transfer, original_method, wallet, none
    refund_reference = Column(String, nullable=True)  # UTR / transaction ID of actual refund
    extra_amount_to_collect = Column(Float, default=0.0, nullable=False)
    
    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    pickup_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Return pickup rider / partner
    rider_id = Column(Integer, ForeignKey("delivery_riders.id", ondelete="SET NULL"), nullable=True)
    logistics_partner_id = Column(Integer, ForeignKey("logistics_partners.id", ondelete="SET NULL"), nullable=True)
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id", ondelete="SET NULL"), nullable=True)
    
    # Relationships
    order = relationship("Order", back_populates="returns", foreign_keys=[order_id])
    order_item = relationship("OrderItem")
    customer = relationship("CustomerUser", foreign_keys=[customer_id], backref="order_returns")
    approver = relationship("User", foreign_keys=[approved_by])
    exchange_variant = relationship("ProductVariant", foreign_keys=[exchange_variant_id])
    replacement_order = relationship("Order", foreign_keys=[replacement_order_id])
    hub = relationship("DeliveryHub", backref="returns")
    logistics_partner = relationship("LogisticsPartner")
