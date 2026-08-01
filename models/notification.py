from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import enum

class NotificationType(str, enum.Enum):
    ORDER_PLACED = "order_placed"
    ORDER_CONFIRMED = "order_confirmed"
    ORDER_SHIPPED = "order_shipped"
    ORDER_OUT_FOR_DELIVERY = "order_out_for_delivery"
    ORDER_DELIVERED = "order_delivered"
    ORDER_PACKED = "order_packed"
    ORDER_PACKING = "order_packing"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FAILED = "order_failed"
    RETURN_REQUESTED = "return_requested"
    RETURN_APPROVED = "return_approved"
    RETURN_REJECTED = "return_rejected"
    PAYMENT_SUCCESS = "payment_success"
    PAYMENT_FAILED = "payment_failed"
    LOW_STOCK_ALERT = "low_stock_alert"
    PROMOTIONAL = "promotional"
    RIDER_APPROVED = "rider_approved"
    RIDER_REJECTED = "rider_rejected"
    SETTLEMENT_GENERATED = "settlement_generated"
    SETTLEMENT_APPROVED = "settlement_approved"
    SETTLEMENT_PAID = "settlement_paid"

class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    PUSH = "push"

class Notification(Base):
    """User notifications"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), nullable=True)
    
    # Notification details
    type = Column(SQLEnum(NotificationType), nullable=False)
    channel = Column(SQLEnum(NotificationChannel), nullable=False)
    
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    data = Column(JSON, nullable=True)  # Additional data (order_id, product_id, etc.)
    
    # Status
    is_read = Column(Boolean, default=False, nullable=False)
    is_sent = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", backref="notifications")
    customer = relationship("CustomerUser", backref="notifications")

class CustomerNotificationPreference(Base):
    """Customer notification preferences"""
    __tablename__ = "customer_notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Email preferences
    email_order_updates = Column(Boolean, default=True, nullable=False)
    email_promotions = Column(Boolean, default=True, nullable=False)
    email_newsletters = Column(Boolean, default=False, nullable=False)
    
    # SMS preferences
    sms_order_updates = Column(Boolean, default=True, nullable=False)
    sms_promotions = Column(Boolean, default=False, nullable=False)
    
    # In-app preferences
    in_app_order_updates = Column(Boolean, default=True, nullable=False)
    in_app_promotions = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    customer = relationship("CustomerUser", backref="notification_preference", uselist=False)

class NotificationPreference(Base):
    """User notification preferences"""
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    # Email preferences
    email_order_updates = Column(Boolean, default=True, nullable=False)
    email_promotions = Column(Boolean, default=True, nullable=False)
    email_newsletters = Column(Boolean, default=False, nullable=False)
    
    # SMS preferences
    sms_order_updates = Column(Boolean, default=True, nullable=False)
    sms_promotions = Column(Boolean, default=False, nullable=False)
    
    # In-app preferences
    in_app_order_updates = Column(Boolean, default=True, nullable=False)
    in_app_promotions = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", backref="notification_preference", uselist=False)
