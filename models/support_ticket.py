from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Enum as SAEnum, JSON
from sqlalchemy.orm import relationship
import enum
from datetime import datetime, timezone
from core.database import Base

class TicketType(str, enum.Enum):
    ORDER_MANAGEMENT = "order_management"
    PAYMENT_REFUNDS = "payment_refunds"
    RETURNS_EXCHANGES = "returns_exchanges"
    PRODUCT_INQUIRIES = "product_inquiries"
    ACCOUNT_PROFILE = "account_profile"
    TECHNICAL_ISSUES = "technical_issues"
    OTHERS = "others"

class TicketSource(str, enum.Enum):
    WEBSITE = "website"
    EMAIL = "email"
    LIVE_CHAT = "live_chat"
    PHONE = "phone"
    SOCIAL_MEDIA = "social_media"
    WHATSAPP = "whatsapp"

class TicketSLAStatus(str, enum.Enum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BREACHED = "breached"

class TicketStage(str, enum.Enum):
    HELPDESK = "helpdesk"
    BACKOFFICE = "backoffice"

class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String(50), unique=True, index=True, nullable=True) # E.g., TKT-123456
    
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    dealer_id = Column(Integer, ForeignKey("dealers.id"), nullable=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    
    ticket_type = Column(SAEnum(TicketType), nullable=False, default=TicketType.OTHERS)
    status = Column(SAEnum(TicketStatus), default=TicketStatus.OPEN)
    priority = Column(SAEnum(TicketPriority), default=TicketPriority.MEDIUM)
    source = Column(SAEnum(TicketSource), default=TicketSource.WEBSITE)
    ticket_stage = Column(SAEnum(TicketStage, native_enum=False), default=TicketStage.HELPDESK)
    
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    attachments = Column(JSON, nullable=True, default=list)
    
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # SLA & Feedback Fields
    escalation_deadline = Column(DateTime, nullable=True)
    sla_status = Column(SAEnum(TicketSLAStatus, native_enum=False), default=TicketSLAStatus.ON_TRACK)
    customer_feedback_rating = Column(Integer, nullable=True) # 1 to 5
    customer_feedback_comments = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    customer = relationship("CustomerUser", backref="tickets")
    dealer = relationship("Dealer", backref="tickets")
    partner = relationship("Partner", backref="tickets")
    order = relationship("Order", backref="tickets")
    product = relationship("Product", backref="tickets")
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Can be customer, dealer, partner, or superadmin user id
    
    message = Column(Text, nullable=False)
    is_internal_note = Column(Boolean, default=False)
    attachment_url = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("SupportTicket", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
