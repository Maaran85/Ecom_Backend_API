from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base
import uuid

class OrderInvoice(Base):
    __tablename__ = "order_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    dealer_id = Column(UUID(as_uuid=True), ForeignKey("dealers.id"), nullable=False, index=True)
    
    invoice_number = Column(String, unique=True, index=True, nullable=False)
    invoice_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Financial totals for this specific dealer's portion
    total_amount = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, nullable=False, default=0.0)
    
    is_reverse_charge = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    order = relationship("Order", backref="invoices")
    dealer = relationship("Dealer")
