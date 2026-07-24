from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from core.database import Base


class CommissionStatus(str, enum.Enum):
    PENDING = "pending"
    CREDITED = "credited"
    CANCELLED = "cancelled"


class CustomerReferralProfile(Base):
    """Stores unique referral code and referrer linkage per customer."""
    __tablename__ = "customer_referral_profiles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), unique=True, nullable=False, index=True)
    referral_code = Column(String(30), unique=True, index=True, nullable=False)
    referred_by_id = Column(Integer, ForeignKey("customer_users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("CustomerUser", foreign_keys=[customer_id])
    referrer = relationship("CustomerUser", foreign_keys=[referred_by_id])


class ReferralOrderCommission(Base):
    """Header record for total referral commission earned on an order."""
    __tablename__ = "referral_order_commissions"

    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    referee_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    total_commission_amount = Column(Float, default=0.0, nullable=False)
    status = Column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)

    items = relationship("ReferralItemCommission", back_populates="order_commission", cascade="all, delete-orphan")
    referrer = relationship("CustomerUser", foreign_keys=[referrer_id])
    referee = relationship("CustomerUser", foreign_keys=[referee_id])


class ReferralItemCommission(Base):
    """Line-item breakdown capturing category rate applied to each OrderItem."""
    __tablename__ = "referral_item_commissions"

    id = Column(Integer, primary_key=True, index=True)
    order_commission_id = Column(Integer, ForeignKey("referral_order_commissions.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    item_price = Column(Float, nullable=False)
    applied_rate_percent = Column(Float, nullable=False)  # e.g., 5.0
    commission_amount = Column(Float, nullable=False)     # item_price * (applied_rate_percent / 100)
    status = Column(SQLEnum(CommissionStatus), default=CommissionStatus.PENDING)

    order_commission = relationship("ReferralOrderCommission", back_populates="items")


class CustomerWallet(Base):
    """Customer wallet tracking available rewards & referral cash."""
    __tablename__ = "customer_wallets"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), unique=True, nullable=False, index=True)
    available_balance = Column(Float, default=0.0, nullable=False)
    lifetime_earned = Column(Float, default=0.0, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("CustomerUser")


class WalletTransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class WalletTransaction(Base):
    """Ledger table tracking all wallet credit and debit history."""
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    transaction_type = Column(SQLEnum(WalletTransactionType), nullable=False)
    description = Column(String(255), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("CustomerUser")

