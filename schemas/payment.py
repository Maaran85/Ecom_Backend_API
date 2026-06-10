from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
from models.payment import PaymentMethod, PaymentStatus

# Payment Initiation
class PaymentInitiateRequest(BaseModel):
    order_id: int
    payment_method: PaymentMethod
    
    # Card details (if card payment)
    card_number: Optional[str] = None
    card_expiry: Optional[str] = None  # MM/YY
    card_cvv: Optional[str] = None
    card_holder_name: Optional[str] = None
    
    # UPI details
    upi_id: Optional[str] = None
    
    # Wallet details
    wallet_provider: Optional[str] = None  # Paytm, PhonePe, GooglePay
    
    @validator('card_number')
    def validate_card_number(cls, v, values):
        if values.get('payment_method') == PaymentMethod.CARD and not v:
            raise ValueError('Card number is required for card payments')
        return v
    
    @validator('upi_id')
    def validate_upi_id(cls, v, values):
        if values.get('payment_method') == PaymentMethod.UPI and not v:
            raise ValueError('UPI ID is required for UPI payments')
        return v

class PaymentResponse(BaseModel):
    id: int
    order_id: int
    amount: float
    payment_method: PaymentMethod
    status: PaymentStatus
    transaction_id: str
    payment_gateway: str
    payment_url: Optional[str] = None  # Mock payment page URL
    initiated_at: datetime
    
    class Config:
        from_attributes = True

class PaymentStatusResponse(BaseModel):
    payment_id: int
    order_id: int
    status: PaymentStatus
    transaction_id: str
    amount: float
    message: str
    completed_at: Optional[datetime] = None

class PaymentConfirmRequest(BaseModel):
    """Mock payment confirmation (simulates user completing payment)"""
    simulate_success: bool = True  # False to simulate failure

class PaymentRefundRequest(BaseModel):
    amount: Optional[float] = None  # Partial refund amount, None for full refund
    reason: str

class PaymentRefundResponse(BaseModel):
    payment_id: int
    refund_amount: float
    status: PaymentStatus
    message: str

class Payment(BaseModel):
    id: int
    order_id: int
    amount: float
    payment_method: PaymentMethod
    status: PaymentStatus
    transaction_id: str
    payment_gateway: str
    card_last4: Optional[str] = None
    card_brand: Optional[str] = None
    upi_id: Optional[str] = None
    wallet_provider: Optional[str] = None
    failure_reason: Optional[str] = None
    refund_amount: float
    refund_reason: Optional[str] = None
    refunded_at: Optional[datetime] = None
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class PaymentStats(BaseModel):
    total_payments: int
    successful_payments: int
    failed_payments: int
    total_amount: float
    total_refunded: float
    payment_method_breakdown: dict

# Razorpay Schemas
class RazorpayOrderResponse(BaseModel):
    id: str
    currency: str
    amount: int
    receipt: str
    status: str
    order_id: int # Internal order ID

class RazorpayVerifyRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    order_id: int # Internal order ID sent back from client
