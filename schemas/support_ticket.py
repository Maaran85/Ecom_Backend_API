from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List, Any, Dict, Union
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
    category_name: Optional[str] = None
    quantity: int
    price: float
    mrp: Optional[float] = None
    discount_amount: Optional[float] = 0.0
    discount_percentage: Optional[int] = 0
    status: Optional[str] = None
    delivered_at: Optional[datetime] = None
    return_window_matures_at: Optional[datetime] = None
    dealer_name: Optional[str] = None
    dealer_id: Optional[UUID] = None
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivery_attempts: Optional[int] = 0
    delivery_type: Optional[str] = None
    reject_reason: Optional[str] = None
    logistics_partner_name: Optional[str] = None
    delivery_rider_name: Optional[str] = None
    delivery_rider_phone: Optional[str] = None


class CustomerOrderPricingBreakdown(BaseModel):
    total_mrp: float = 0.0
    discount_on_mrp: float = 0.0
    coupon_discount: float = 0.0
    total_savings: float = 0.0
    delivery_charge: float = 0.0
    platform_fee: float = 0.0
    wallet_applied: float = 0.0
    other_customer_charges: float = 0.0
    final_order_amount: float = 0.0
    persisted_total_amount: float = 0.0
    has_pricing_discrepancy: bool = False
    discrepancy_details: Optional[str] = None


class CODVerificationContext(BaseModel):
    is_cod: bool = False
    payment_method: str = "COD"
    payment_status: str = "pending"
    cod_collection_status: str = "UNCOLLECTED"  # COLLECTED, UNCOLLECTED, PENDING_DELIVERY
    amount_to_collect: float = 0.0
    amount_collected: Optional[float] = None
    collected_at: Optional[datetime] = None
    collected_by: Optional[str] = None
    collected_method: Optional[str] = None  # cash, upi, online
    is_verified_collected: bool = False
    reconciliation_discrepancy: Optional[str] = None



class OrderLifecycleEvent(BaseModel):
    event_key: str
    event_title: str
    timestamp: Optional[datetime] = None
    is_completed: bool = False
    is_current: bool = False
    description: Optional[str] = None
    source: str = "system"  # system, courier, rider, payment_gateway


class RiderDetailsContext(BaseModel):
    rider_id: Optional[int] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = None
    current_status: Optional[str] = None
    is_available: Optional[bool] = None
    average_rating: Optional[float] = 0.0
    total_reviews: Optional[int] = 0
    logistics_partner_name: Optional[str] = None
    business_name: Optional[str] = None


class DeliveryAttemptRecord(BaseModel):
    attempt_number: int
    attempt_timestamp: Optional[datetime] = None
    status: str
    reason: Optional[str] = None
    source: str = "rider"
    notes: Optional[str] = None


class ProofOfDeliveryContext(BaseModel):
    is_available: bool = False
    pod_type: Optional[str] = None  # otp, photo, signature, courier_pod
    recipient_name: Optional[str] = None
    handover_timestamp: Optional[datetime] = None
    evidence_url: Optional[str] = None
    status_notes: str = "Proof of Delivery evidence is not captured in current courier/rider workflow."


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

    # Customer information (buyer)
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    # Delivery & Tracking Information
    logistics_partner_name: Optional[str] = None
    courier_company: Optional[str] = None
    delivery_rider_name: Optional[str] = None
    delivery_rider_phone: Optional[str] = None
    delivery_status: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    delivery_attempts: Optional[int] = 0

    # Amazon-style investigation blocks
    lifecycle_timeline: List[OrderLifecycleEvent] = []
    rider_details: Optional[RiderDetailsContext] = None
    delivery_attempt_history: List[DeliveryAttemptRecord] = []
    proof_of_delivery: Optional[ProofOfDeliveryContext] = None

    # Customer Order View & Price Breakdown
    pricing_breakdown: Optional[CustomerOrderPricingBreakdown] = None
    cod_verification: Optional[CODVerificationContext] = None

    return_status: Optional[str] = None
    return_reason: Optional[str] = None
    settlement_status: Optional[str] = None
    settlement: Optional[Dict[str, Any]] = None
    tracking: Optional[Dict[str, Any]] = None
    order_items: List[OrderItemContext] = []
    selected_order_item: Optional[OrderItemContext] = None

    # Department-Specific Investigation Views (populated only for authorized department/roles)
    authorized_departments: List[str] = []
    active_department_view: Optional[str] = None
    logistics_investigation: Optional["LogisticsInvestigationContext"] = None
    finance_investigation: Optional["FinanceInvestigationContext"] = None
    dealer_investigation: Optional["DealerProductInvestigationContext"] = None
    technology_investigation: Optional["TechnologyInvestigationContext"] = None


class LogisticsInvestigationContext(BaseModel):
    is_accessible: bool = True
    courier_company: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_url: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    delivery_attempts: int = 0
    attempt_history: List[DeliveryAttemptRecord] = []
    rider_details: Optional[RiderDetailsContext] = None
    proof_of_delivery: Optional[ProofOfDeliveryContext] = None
    delivery_discrepancy: Optional[str] = None
    shipment_exceptions: List[str] = []


class FinanceInvestigationContext(BaseModel):
    is_accessible: bool = True
    payment_id: Optional[int] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    transaction_id: Optional[str] = None
    payment_gateway: Optional[str] = None
    amount: Optional[float] = None
    currency: str = "INR"
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    upi_id: Optional[str] = None
    wallet_provider: Optional[str] = None
    gateway_response_captured: bool = False
    gateway_event_logs: List[Dict[str, Any]] = []
    pricing_breakdown: Optional[CustomerOrderPricingBreakdown] = None
    cod_verification: Optional[CODVerificationContext] = None
    refund_details: Optional[Dict[str, Any]] = None
    settlement_details: Optional[Dict[str, Any]] = None
    financial_discrepancies: List[str] = []


class DealerProductInvestigationContext(BaseModel):
    is_accessible: bool = True
    dealer_id: Optional[str] = None
    dealer_name: Optional[str] = None
    dealer_gst: Optional[str] = None
    dealer_phone: Optional[str] = None
    dealer_city: Optional[str] = None
    dealer_is_approved: Optional[bool] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    category_name: Optional[str] = None
    hsn_code: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None
    is_returnable: Optional[bool] = None
    return_window_days: Optional[int] = None
    return_policy_note: Optional[str] = None
    item_ordered_price: Optional[float] = None
    item_ordered_quantity: Optional[int] = None
    fulfillment_return_evidence: Optional[Dict[str, Any]] = None
    product_images: List[str] = []
    listing_discrepancy: Optional[str] = None


class TechnologyInvestigationContext(BaseModel):
    is_accessible: bool = True
    ticket_id: int
    ticket_number: Optional[str] = None
    order_id: Optional[int] = None
    order_number: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    platform: Optional[str] = None
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    browser: Optional[str] = None
    client_ip: Optional[str] = None
    ticket_source: Optional[str] = None
    complaint_reason: Optional[str] = None
    error_context: Optional[str] = None
    transaction_reference: Optional[str] = None
    integration_failures: List[Dict[str, Any]] = []
    audit_trail: List[Dict[str, Any]] = []
    telemetry_status: str = "Captured via client device_info and system audit trail"


class DepartmentInvestigationResponse(BaseModel):
    ticket_id: int
    department: str
    is_accessible: bool = True
    data: Union[
        LogisticsInvestigationContext,
        FinanceInvestigationContext,
        DealerProductInvestigationContext,
        TechnologyInvestigationContext
    ]
