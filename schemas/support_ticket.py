from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.support_ticket import TicketType, TicketStatus

class SupportTicketBase(BaseModel):
    ticket_type: TicketType
    subject: str
    description: str
    dealer_id: Optional[int] = None
    order_id: Optional[int] = None
    product_id: Optional[int] = None

class SupportTicketCreate(SupportTicketBase):
    pass

class SupportTicketUpdate(BaseModel):
    status: Optional[TicketStatus] = None

class SupportTicketResponse(SupportTicketBase):
    id: int
    user_id: int
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
