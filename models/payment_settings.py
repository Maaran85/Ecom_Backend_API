from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.sql import func
from core.database import Base


class PlatformPaymentSettings(Base):
    """Platform-level payment gateway configuration."""
    __tablename__ = "platform_payment_settings"

    id = Column(Integer, primary_key=True, index=True)

    # Display / label
    provider_name = Column(String, nullable=False)          # e.g. "Razorpay", "PhonePe UPI"
    provider_type = Column(String, nullable=False)          # "upi" | "razorpay" | "stripe" | "paytm" | "other"

    # Credentials / config
    api_key = Column(String, nullable=True)
    api_secret = Column(String, nullable=True)
    merchant_id = Column(String, nullable=True)
    upi_vpa = Column(String, nullable=True)                 # e.g. merchant@okaxis
    webhook_secret = Column(String, nullable=True)

    # Mode
    is_live = Column(Boolean, default=False, nullable=False)  # False = sandbox/test
    is_active = Column(Boolean, default=True, nullable=False)

    # Platform fee
    platform_fee_percent = Column(Float, default=0.0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
