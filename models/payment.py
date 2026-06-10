from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class PaymentMethod(str, enum.Enum):
    CARD = "card"
    UPI = "upi"
    WALLET = "wallet"
    NET_BANKING = "net_banking"
    COD = "cod"  # Cash on Delivery

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Payment details
    amount = Column(Float, nullable=False)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    
    # Transaction details
    transaction_id = Column(String, unique=True, nullable=False, index=True)
    payment_gateway = Column(String, default="MockPay")
    
    # Card details (for card payments)
    card_last4 = Column(String, nullable=True)
    card_brand = Column(String, nullable=True)  # Visa, Mastercard, Amex, etc.
    
    # UPI details
    upi_id = Column(String, nullable=True)
    
    # Wallet details
    wallet_provider = Column(String, nullable=True)  # Paytm, PhonePe, GooglePay, etc.
    
    # Failure details
    failure_reason = Column(String, nullable=True)
    
    # Refund details
    refund_amount = Column(Float, default=0.0)
    refund_reason = Column(String, nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    initiated_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    order = relationship("Order", back_populates="payment")

class PaymentWebhook(Base):
    """Log of payment webhook events for audit trail"""
    __tablename__ = "payment_webhooks"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String, nullable=False)  # payment.success, payment.failed, refund.processed
    payload = Column(JSON, nullable=True)
    processed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    payment = relationship("Payment", backref="webhooks")
