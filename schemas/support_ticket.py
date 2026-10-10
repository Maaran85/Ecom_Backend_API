from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime
from models.support_ticket import TicketType, TicketPriority, TicketStatus, TicketSource, TicketSLAStatus, TicketStage

PRE_DELIVERY_REASONS = [
    "Payment made still order is showing pending for payment",
    "Order canceled - refund issue",
    "Others"
]

DELIVERED_REASONS = [
    "Return requested - item not picked up yet",
    "Return picked up but refund pending",
    "Others"
]

POST_POLICY_REASONS = [
    "Product damaged within warranty period",
    "Damaged product supplied unable to return",
    "Complained to dealer on product issue but no response",
    "Reward points issue",
    "Others"
]

PROFILE_REASONS = [
    "App issues",
    "Reward points",
    "Redeem points",
    "Others"
]

VALID_DEPARTMENTS = ["dealer", "logistics", "technology", "finance", "others", "helpdesk"]

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

class TicketResolverUser(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None

    class Config:
        from_attributes = True

from pydantic import BaseModel, field_validator, model_validator

class SupportTicketCreate(BaseModel):
    subject: str
    description: str
    ticket_type: Optional[TicketType] = None
    category: Optional[str] = None
    complaint_reason: Optional[str] = None
    source: Optional[TicketSource] = TicketSource.WEBSITE
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    device_info: Optional[Dict[str, Any]] = None
    attachments: Optional[List[str]] = []

    @model_validator(mode="before")
    @classmethod
    def resolve_ticket_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ttype = data.get("ticket_type")
            cat = data.get("category")
            if not ttype and cat:
                cat_lower = str(cat).strip().lower()
                if cat_lower in ["complaint", "order", "orders", "order_management"]:
                    if data.get("order_item_id") or data.get("order_id"):
                        data["ticket_type"] = TicketType.ORDER_MANAGEMENT
                    else:
                        data["ticket_type"] = TicketType.ACCOUNT_PROFILE
                elif cat_lower in ["payment", "payments", "refund", "refunds", "payment_refunds"]:
                    data["ticket_type"] = TicketType.PAYMENT_REFUNDS
                elif cat_lower in ["return", "returns", "exchange", "exchanges", "returns_exchanges"]:
                    data["ticket_type"] = TicketType.RETURNS_EXCHANGES
                elif cat_lower in ["product", "products", "inquiry", "product_inquiries"]:
                    data["ticket_type"] = TicketType.PRODUCT_INQUIRIES
                elif cat_lower in ["account", "profile", "account_profile"]:
                    data["ticket_type"] = TicketType.ACCOUNT_PROFILE
                elif cat_lower in ["technical", "tech", "technical_issues"]:
                    data["ticket_type"] = TicketType.TECHNICAL_ISSUES
                else:
                    data["ticket_type"] = TicketType.OTHERS
            elif not ttype:
                if data.get("order_item_id") or data.get("order_id"):
                    data["ticket_type"] = TicketType.ORDER_MANAGEMENT
                elif data.get("complaint_reason"):
                    data["ticket_type"] = TicketType.ACCOUNT_PROFILE
                else:
                    data["ticket_type"] = TicketType.OTHERS
        return data

class OperatorTicketCreate(BaseModel):
    customer_id: Optional[int] = None
    customer_identifier: Optional[str] = None
    subject: str
    description: str
    ticket_type: Optional[TicketType] = None
    category: Optional[str] = None
    complaint_reason: Optional[str] = None
    source: Optional[TicketSource] = TicketSource.PHONE
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    priority: Optional[TicketPriority] = TicketPriority.MEDIUM
    attachments: Optional[List[str]] = []

    @model_validator(mode="before")
    @classmethod
    def resolve_operator_ticket_type(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ttype = data.get("ticket_type")
            cat = data.get("category")
            if not ttype and cat:
                cat_lower = str(cat).strip().lower()
                if cat_lower in ["complaint", "order", "orders", "order_management"]:
                    if data.get("order_item_id") or data.get("order_id"):
                        data["ticket_type"] = TicketType.ORDER_MANAGEMENT
                    else:
                        data["ticket_type"] = TicketType.ACCOUNT_PROFILE
                else:
                    data["ticket_type"] = TicketType.OTHERS
            elif not ttype:
                if data.get("order_item_id") or data.get("order_id"):
                    data["ticket_type"] = TicketType.ORDER_MANAGEMENT
                elif data.get("complaint_reason"):
                    data["ticket_type"] = TicketType.ACCOUNT_PROFILE
                else:
                    data["ticket_type"] = TicketType.OTHERS
        return data

class DepartmentActionUpdate(BaseModel):
    assigned_department: Optional[str] = None
    root_cause_analysis: Optional[str] = None
    action_taken: Optional[str] = None
    exceptional_refund_approved: Optional[bool] = None
    offline_refund_reference: Optional[str] = None
    offline_refund_amount: Optional[float] = None

    @field_validator("assigned_department")
    @classmethod
    def validate_dept(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.lower() not in VALID_DEPARTMENTS:
            raise ValueError(f"Invalid department '{v}'. Must be one of: {', '.join(VALID_DEPARTMENTS)}")
        return v.lower() if v is not None else None


class CustomerSupportTicketResponse(BaseModel):
    id: int
    ticket_number: str
    customer_id: int
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    product_id: Optional[UUID] = None
    
    subject: str
    description: str
    ticket_type: Optional[TicketType] = TicketType.OTHERS
    complaint_reason: Optional[str] = None
    
    priority: Optional[TicketPriority] = TicketPriority.MEDIUM
    status: Optional[TicketStatus] = TicketStatus.OPEN
    source: Optional[TicketSource] = TicketSource.WEBSITE
    ticket_stage: Optional[TicketStage] = TicketStage.HELPDESK
    
    sla_status: Optional[TicketSLAStatus] = TicketSLAStatus.ON_TRACK
    customer_feedback_rating: Optional[int] = None
    customer_feedback_comments: Optional[str] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: Optional[int] = None
    attachments: Optional[List[str]] = []
    
    messages: List[TicketMessageResponse] = []
    
    class Config:
        from_attributes = True

class SupportTicketResponse(BaseModel):
    id: int
    ticket_number: str
    customer_id: int
    dealer_id: Optional[UUID] = None
    partner_id: Optional[int] = None
    order_id: Optional[int] = None
    order_item_id: Optional[int] = None
    product_id: Optional[UUID] = None
    
    subject: str
    description: str
    ticket_type: TicketType
    complaint_reason: Optional[str] = None
    escalation_reason: Optional[str] = None
    investigation_request: Optional[str] = None
    assigned_department: Optional[str] = None
    root_cause_analysis: Optional[str] = None
    action_taken: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    exceptional_refund_approved: Optional[bool] = False
    
    priority: TicketPriority
    status: TicketStatus
    source: TicketSource
    ticket_stage: TicketStage
    assigned_user_id: Optional[int] = None
    assigned_user: Optional[TicketAssignedUser] = None
    resolved_by_user_id: Optional[int] = None
    resolved_by_user: Optional[TicketResolverUser] = None
    
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
    reason: Optional[str] = "General"
    target_department: Optional[str] = None
    department: Optional[str] = None
    investigation_request: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_department(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("target_department") and data.get("department"):
                data["target_department"] = data.get("department")
        return data

class TicketReturnCreate(BaseModel):
    resolution_summary: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_summary(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("resolution_summary") and data.get("reason"):
                data["resolution_summary"] = data.get("reason")
            elif not data.get("resolution_summary"):
                data["resolution_summary"] = "Backoffice investigation completed"
        return data

class OrderItemContext(BaseModel):
    id: int
    product_id: Optional[UUID] = None
    product_name: str
    product_image: Optional[str] = None
    quantity: int
    price: float
    status: Optional[str] = None
    delivered_at: Optional[datetime] = None
    return_window_matures_at: Optional[datetime] = None
    dealer_name: Optional[str] = None
    dealer_id: Optional[UUID] = None

class OrderContextResponse(BaseModel):
    ticket_id: int
    order_id: Optional[int] = None
    order_number: Optional[str] = None
    order_status: Optional[str] = None
    order_created_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    payment_amount: Optional[float] = None
    refund_status: Optional[str] = None
    refund_amount: Optional[float] = None
    shipping_address: Optional[Dict[str, Any]] = None
    logistics_partner_name: Optional[str] = None
    delivery_rider_name: Optional[str] = None
    delivery_rider_phone: Optional[str] = None
    delivery_status: Optional[str] = None
    return_status: Optional[str] = None
    return_reason: Optional[str] = None
    settlement_status: Optional[str] = None
    order_items: List[OrderItemContext] = []
    selected_order_item: Optional[OrderItemContext] = None
