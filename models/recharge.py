from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from core.database import Base
from models.customer_user import CustomerUser
import enum

class RechargeStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    PROCESSING = "processing"

class RechargeTransaction(Base):
    __tablename__ = "recharge_transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    mobile_number = Column(String(15), nullable=False, index=True)
    operator = Column(String(50), nullable=False)
    circle = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(Enum(RechargeStatus), default=RechargeStatus.PENDING)

    # Provider references
    provider_reference_id = Column(String(100), nullable=True, unique=True, index=True)
    api_response_code = Column(String(20), nullable=True)
    api_response_message = Column(String(255), nullable=True)

    # Internal references
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("CustomerUser", backref="recharge_transactions")
    payment = relationship("Payment")
