from sqlalchemy import Column, Integer, Float, ForeignKey, String, DateTime, Enum as SQLEnum, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import enum
from core.database import Base

class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    quantity = Column(Integer, default=1)
    size = Column(String, nullable=True)
    variant_attributes = Column(JSON, nullable=True) # Selected dynamic attributes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    product = relationship("Product", foreign_keys=[product_id])
    variant = relationship("Product", foreign_keys=[variant_id])
    customer = relationship("CustomerUser", backref="cart_items")

class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    ORDER_PLACED = "order_placed"
    FAILED = "failed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    PACKAGING = "packaging"
    PACKED = "packed"
    AT_HUB = "at_hub"
    DISPATCHED = "dispatched"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    UNDELIVERED = "undelivered"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    RETURNED = "returned"

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(20), unique=True, index=True, nullable=True)
    customer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=False, index=True)
    
    # Pricing
    subtotal = Column(Float, nullable=False)          # Before any discounts (Inclusive of tax)
    discount_amount = Column(Float, default=0.0)      # Coupon discount
    wallet_amount_used = Column(Float, default=0.0)   # Wallet balance applied to this order
    delivery_charge = Column(Float, default=0.0)      # Total delivery fee
    total_amount = Column(Float, nullable=False)      # Final amount paid by customer
    
    # Tax summary (Calculated backwards from inclusive price)
    tax_amount       = Column(Float, default=0.0)
    cgst_amount      = Column(Float, default=0.0)
    sgst_amount      = Column(Float, default=0.0)
    igst_amount      = Column(Float, default=0.0)
    supply_state     = Column(String, nullable=True) # buyer's state code for IGST calc
    is_inter_state   = Column(Boolean, default=False)
    # tax_invoice_no moved to OrderInvoice

    # Platform Revenue
    platform_fee_amount = Column(Float, default=0.0) # Our cut of this order
    
    # Discount information
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=True)
    coupon_code = Column(String, nullable=True)
    
    # Order status
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    payment_method = Column(String, default="COD")
    is_auction_order = Column(Boolean, default=False)
    
    # (Overall payment status removed from order level, now moved to item level)
    
    # Shipping information
    shipping_address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    billing_address_id = Column(Integer, ForeignKey("addresses.id"), nullable=True)
    tracking_number = Column(String, nullable=True)
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String, nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Invoice
    tax_invoice_no = Column(String, nullable=True, unique=True)
    
    # Referral & Reward Snapshots
    referrer_id = Column(Integer, ForeignKey("customer_users.id"), nullable=True, index=True)
    referral_reward_points = Column(Float, default=0.0, nullable=False)
    referral_reward_amount = Column(Float, default=0.0, nullable=False)
    referral_reward_status = Column(String(20), default="na", nullable=False)  # pending, credited, cancelled, refunded, na
    spin_reward_points = Column(Float, default=0.0, nullable=False)
    spin_reward_amount = Column(Float, default=0.0, nullable=False)
    spin_reward_status = Column(String(20), default="na", nullable=False)      # on_hold, credited, cancelled, na

    # POS specific fields
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    
    # Relationships
    items = relationship("OrderItem", back_populates="order")
    shipping_address = relationship("Address", backref="orders_shipping", foreign_keys=[shipping_address_id])
    billing_address = relationship("Address", backref="orders_billing", foreign_keys=[billing_address_id])
    coupon = relationship("Coupon", backref="orders")
    customer = relationship("CustomerUser", backref="orders", foreign_keys=[customer_id])
    referrer = relationship("CustomerUser", foreign_keys=[referrer_id])
    payment = relationship("Payment", back_populates="order", uselist=False)
    returns = relationship("OrderReturn", back_populates="order", cascade="all, delete-orphan", foreign_keys="OrderReturn.order_id")

    @property
    def refund_amount(self) -> float:
        if hasattr(self, 'payment') and self.payment:
            return getattr(self.payment, 'refund_amount', 0.0) or 0.0
        return 0.0

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)  # Store inclusive price at time of order
    size = Column(String, nullable=True)
    variant_attributes = Column(JSON, nullable=True)
    
    # Financial breakdown (Calculated at checkout)
    tax_amount       = Column(Float, default=0.0)
    cgst_rate        = Column(Float, default=0.0)
    sgst_rate        = Column(Float, default=0.0)
    igst_rate        = Column(Float, default=0.0)
    cgst_amount      = Column(Float, default=0.0)
    sgst_amount      = Column(Float, default=0.0)
    igst_amount      = Column(Float, default=0.0)
    hsn_code         = Column(String, nullable=True)
    platform_fee     = Column(Float, default=0.0)

    # Billing Slab fee snapshots (calculated at checkout for historical immutability)
    marketplace_customer_charge = Column(Float, default=0.0)
    marketplace_dealer_fee      = Column(Float, default=0.0)
    marketing_fee_amount         = Column(Float, default=0.0)
    marketing_customer_charge   = Column(Float, default=0.0)
    logistics_charge_amount      = Column(Float, default=0.0)
    logistics_customer_charge   = Column(Float, default=0.0)
    
    # Item-specific tracking
    status = Column(String, default="pending")  # PENDING, PACKAGING, DISPATCHED, DELIVERED, REJECTED, UNDELIVERED
    reject_reason = Column(String, nullable=True)
    courier_company = Column(String, nullable=True)
    tracking_number = Column(String, nullable=True)
    tracking_url = Column(String, nullable=True)
    dispatch_date = Column(DateTime(timezone=True), nullable=True)
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Delivery tracking
    delivery_attempts = Column(Integer, default=0)
    
    # Item-specific payment status
    payment_status = Column(String, default="pending")  # pending, paid, failed
    
    # Hub assignment
    hub_id = Column(Integer, ForeignKey("delivery_hubs.id"), nullable=True)
    hub_arrived_at = Column(DateTime(timezone=True), nullable=True)  # When item arrived at hub

    # Rider assignment
    rider_id = Column(Integer, ForeignKey("delivery_riders.id", ondelete="SET NULL"), nullable=True)
    
    # Logistics partner assignment
    logistics_partner_id = Column(Integer, ForeignKey("logistics_partners.id", ondelete="SET NULL"), nullable=True)
    
    # Delivery Type
    delivery_type = Column(String, nullable=True) # courier, own_rider, logistics
    
    # Rider-collected payment method at delivery (set when rider marks as delivered)
    rider_payment_method = Column(String, nullable=True)  # online, cash, upi
    
    # Settlement tracking
    logistics_remittance_id = Column(Integer, ForeignKey("logistics_remittances.id", ondelete="SET NULL"), nullable=True)
    dealer_remittance_id = Column(Integer, ForeignKey("dealer_remittances.id", ondelete="SET NULL"), nullable=True)

    # Return & Exchange Policy Snapshot at Checkout
    return_window_days = Column(Integer, nullable=True)
    is_returnable      = Column(Boolean, nullable=True)
    is_exchangeable    = Column(Boolean, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", foreign_keys=[product_id])
    variant = relationship("Product", foreign_keys=[variant_id])
    rider = relationship("DeliveryRider", backref="assigned_items")
    hub = relationship("DeliveryHub", backref="order_items")
    logistics_partner = relationship("LogisticsPartner", back_populates="order_items")
    logistics_remittance = relationship("LogisticsRemittance", backref="settled_items")
    dealer_remittance = relationship("DealerRemittance", backref="settled_items")

    @property
    def item_order_id(self) -> str:
        if hasattr(self, 'order') and self.order and self.order.order_number:
            return f"{self.order.order_number}"
        return f"ORD-{self.order_id}-{self.id}"
