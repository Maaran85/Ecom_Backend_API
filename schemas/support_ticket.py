from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.support_ticket import TicketType, TicketPriority, TicketStatus, TicketSource, TicketSLAStatus, TicketStage

class TicketMessageCreate(BaseModel):
    message: str
    is_internal_note: Optional[bool] = False
    attachment_url: Optional[str] = None

class TicketMessageResponse(BaseModel):
    id: int
    ticket_id: int
    sender_id: int
    message: str
    is_internal_note: bool
    attachment_url: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class TicketAssignedUser(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: str

    class Config:
        from_attributes = True

class SupportTicketCreate(BaseModel):
    subject: str
    description: str
    ticket_type: TicketType
    source: Optional[TicketSource] = TicketSource.WEBSITE
    order_item_id: Optional[int] = None
    attachments: Optional[List[str]] = []

class SupportTicketResponse(BaseModel):
    id: int
    ticket_number: str
    customer_id: int
    dealer_id: Optional[int] = None
    partner_id: Optional[int] = None
    order_id: Optional[int] = None
    product_id: Optional[int] = None
    
    subject: str
    description: str
    ticket_type: TicketType
    priority: TicketPriority
    status: TicketStatus
    source: TicketSource
    ticket_stage: TicketStage
    assigned_user_id: Optional[int] = None
    assigned_user: Optional[TicketAssignedUser] = None
    
    escalation_deadline: Optional[datetime] = None
    sla_status: TicketSLAStatus
    customer_feedback_rating: Optional[int] = None
    customer_feedback_comments: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    attachments: Optional[List[str]] = []
    
    messages: List[TicketMessageResponse] = []
    
    class Config:
        from_attributes = True

class TicketStatusUpdate(BaseModel):
    status: TicketStatus

class TicketPriorityUpdate(BaseModel):
    priority: TicketPriority

class TicketAssignUpdate(BaseModel):
    assigned_user_id: int

class TicketFeedbackCreate(BaseModel):
    rating: int
    comments: Optional[str] = None

class TicketBulkAssign(BaseModel):
    ticket_ids: List[int]
    assigned_user_id: int

class TicketEscalateCreate(BaseModel):
    reason: str

class TicketReturnCreate(BaseModel):
    resolution_summary: str
