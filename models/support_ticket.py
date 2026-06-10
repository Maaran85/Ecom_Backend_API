from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum
from datetime import datetime, timezone
from core.database import Base

class TicketType(enum.Enum):
    QUERY = "query"
    COMPLAINT = "complaint"
    OTHER = "other"

class TicketStatus(enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    dealer_id = Column(Integer, ForeignKey("dealers.id"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    
    ticket_type = Column(SAEnum(TicketType), nullable=False)
    status = Column(SAEnum(TicketStatus), default=TicketStatus.OPEN)
    
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    customer = relationship("CustomerUser", backref="tickets")
    dealer = relationship("Dealer", backref="tickets")
    order = relationship("Order", backref="tickets")
    product = relationship("Product", backref="tickets")
