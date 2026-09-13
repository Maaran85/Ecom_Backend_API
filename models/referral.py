from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from core.database import Base


class CommissionStatus(str, enum.Enum):
    PENDING = "pending"
    ON_HOLD = "on_hold"
    CREDITED = "credited"
    CANCELLED = "cancelled"
    REFUND = "refund"
    REDEEMED = "redeemed"
    PAID = "paid"
    NA = "na"
    # Uppercase aliases to gracefully support legacy DB rows
    PENDING_UPPER = "PENDING"
    ON_HOLD_UPPER = "ON_HOLD"
    CREDITED_UPPER = "CREDITED"
    CANCELLED_UPPER = "CANCELLED"
    PAID_UPPER = "PAID"


class WalletTxnType(str, enum.Enum):
    REFERRAL = "referral"
    REFERRAL_PURCHASE = "referral_purchase"
    SPIN_AND_WIN = "spin_and_win"
    ORDER_REFUND = "order_refund"
    REDEEM = "redeem"
    CREDIT = "credit"
    DEBIT = "debit"
    # Uppercase aliases to gracefully support legacy DB rows
    REFERRAL_UPPER = "REFERRAL"
    SPIN_AND_WIN_UPPER = "SPIN_AND_WIN"
    CREDIT_UPPER = "CREDIT"
    DEBIT_UPPER = "DEBIT"


# Backward compatibility alias
WalletTransactionType = WalletTxnType


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
    total_commission_points = Column(Float, default=0.0, nullable=False)
    total_commission_amount = Column(Float, default=0.0, nullable=False)
    status = Column(SQLEnum(CommissionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False), default=CommissionStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)
    settled_at = Column(DateTime, nullable=True)

    items = relationship("ReferralItemCommission", back_populates="order_commission", cascade="all, delete-orphan")
    referrer = relationship("CustomerUser", foreign_keys=[referrer_id])
    referee = relationship("CustomerUser", foreign_keys=[referee_id])


class ReferralItemCommission(Base):
    """Line-item breakdown capturing rate applied to each OrderItem."""
    __tablename__ = "referral_item_commissions"

    id = Column(Integer, primary_key=True, index=True)
    order_commission_id = Column(Integer, ForeignKey("referral_order_commissions.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    item_price = Column(Float, nullable=False)
    applied_rate_percent = Column(Float, nullable=False)  # e.g., 0.20
    commission_amount = Column(Float, nullable=False)     # item_price * (applied_rate_percent / 100)
    commission_points = Column(Float, default=0.0, nullable=False)
    status = Column(SQLEnum(CommissionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False), default=CommissionStatus.PENDING)

    order_commission = relationship("ReferralOrderCommission", back_populates="items")


class CustomerWallet(Base):
    """Customer / User wallet tracking points and monetary balances (100 Points = ₹1.00)."""
    __tablename__ = "customer_wallets"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), unique=True, nullable=False, index=True)
    
    # Points and ₹ balances
    available_points = Column(Float, default=0.0, nullable=False)
    available_amount = Column(Float, default=0.0, nullable=False)
    on_hold_points = Column(Float, default=0.0, nullable=False)
    on_hold_amount = Column(Float, default=0.0, nullable=False)
    redeemed_points = Column(Float, default=0.0, nullable=False)
    redeemed_amount = Column(Float, default=0.0, nullable=False)
    lifetime_earned_points = Column(Float, default=0.0, nullable=False)
    lifetime_earned_amount = Column(Float, default=0.0, nullable=False)

    # Legacy balance fields kept for backwards-compatibility
    available_balance = Column(Float, default=0.0, nullable=False)
    lifetime_earned = Column(Float, default=0.0, nullable=False)

    # Order lifecycle counters
    order_placed_count = Column(Integer, default=0, nullable=False)
    order_delivered_count = Column(Integer, default=0, nullable=False)
    order_canceled_count = Column(Integer, default=0, nullable=False)
    order_returned_count = Column(Integer, default=0, nullable=False)

    # Referral commission (bonus A) status: "pending" until >= 3 delivered orders, then "paid"
    ref_com_status = Column(SQLEnum(CommissionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False), default=CommissionStatus.PENDING, nullable=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("CustomerUser")


class WalletTransaction(Base):
    """Ledger table tracking all wallet credit, debit, on-hold, and refund events."""
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    source_user_id = Column(Integer, ForeignKey("customer_users.id"), nullable=True, index=True)
    
    points = Column(Float, default=0.0, nullable=False)
    amount = Column(Float, default=0.0, nullable=False)
    
    transaction_type = Column(SQLEnum(WalletTxnType, values_callable=lambda x: [e.value for e in x], native_enum=False), nullable=False)
    status = Column(SQLEnum(CommissionStatus, values_callable=lambda x: [e.value for e in x], native_enum=False), default=CommissionStatus.CREDITED, nullable=False)
    
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("CustomerUser", foreign_keys=[customer_id])
    source_user = relationship("CustomerUser", foreign_keys=[source_user_id])


class WalletRedemption(Base):
    """Tracks wallet redemptions against orders."""
    __tablename__ = "wallet_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    transaction_id = Column(String(100), nullable=True, index=True)
    
    redeem_points = Column(Float, default=0.0, nullable=False)
    redeem_amount = Column(Float, default=0.0, nullable=False)
    status = Column(SQLEnum(CommissionStatus, native_enum=False), default=CommissionStatus.REDEEMED, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("CustomerUser", foreign_keys=[customer_id])
    order = relationship("Order", foreign_keys=[order_id])

