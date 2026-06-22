from .user import User, UserRole
from .customer_user import CustomerUser
from .product import Category, Product, CategoryAttribute
from .cart import CartItem, Order, OrderItem, OrderStatus
from .dealer import Dealer
from .product_variant import ProductVariant
from .address import Address, AddressType
from .review import Review, ReviewVote
from .wishlist import WishlistItem
from .consent import ConsentLog
from .coupon import Coupon, CouponUsage, DiscountType
from .flash_sale import FlashSale
from .bulk_discount import BulkDiscount
from .payment import Payment, PaymentWebhook, PaymentMethod, PaymentStatus
from .order_return import OrderReturn, ReturnStatus
from .inventory import StockMovement, StockReservation, StockAlert, MovementType, ProductInventory
from .notification import Notification, NotificationPreference, CustomerNotificationPreference, NotificationType, NotificationChannel
from .social import DealerFollow
from .search_history import SearchHistory
from .support_ticket import SupportTicket, TicketType, TicketStatus
from .delivery_rider import DeliveryRider
from .logistics_partner import LogisticsPartner
from .rider_review import RiderReview
from .rider_earning import RiderEarning
from .hub import DeliveryHub
from .location import Country, State, PincodeMaster
from .dealer_logistics import dealer_logistics_mapping
from .audit import AuditLog
from .payment_settings import PlatformPaymentSettings
from .tax import TaxCategory, TaxRule, TaxLedger
from .logistics_remittance import LogisticsRemittance
from .dealer_remittance import DealerRemittance
from .recharge import RechargeTransaction, RechargeStatus
from .reward import SpinConfig, SpinToken, SpinResult, RewardPrize, MonthlyLeaderboard, SpinSource, RewardSession, RewardSessionStatus
from .partner import Partner

__all__ = [
    "User", "UserRole", "CustomerUser",
    "Category", "Product", "CategoryAttribute",
    "CartItem", "Order", "OrderItem", "OrderStatus",
    "Dealer",
    "ProductVariant",
    "Address", "AddressType",
    "Review", "ReviewVote",
    "WishlistItem", "ConsentLog",
    "Coupon", "CouponUsage", "DiscountType",
    "FlashSale",
    "BulkDiscount",
    "Payment", "PaymentWebhook", "PaymentMethod", "PaymentStatus",
    "OrderReturn", "ReturnStatus",
    "StockMovement", "StockReservation", "StockAlert", "MovementType", "ProductInventory",
    "Notification", "NotificationPreference", "CustomerNotificationPreference", "NotificationType", "NotificationChannel",
    "DealerFollow",
    "SearchHistory",
    "SupportTicket", "TicketType", "TicketStatus",
    "DeliveryRider", "RiderReview", "RiderEarning",
    "LogisticsPartner",
    "DeliveryHub",
    "Country", "State", "PincodeMaster",
    "AuditLog",
    "PlatformPaymentSettings",
    "dealer_logistics_mapping",
    "TaxCategory", "TaxRule", "TaxLedger",
    "LogisticsRemittance",
    "DealerRemittance",
    "RechargeTransaction", "RechargeStatus",
    "SpinConfig", "SpinToken", "SpinResult", "RewardPrize", "MonthlyLeaderboard", "SpinSource", "RewardSession", "RewardSessionStatus",
    "Partner"
]

# Dynamically calculate stock from ProductInventory to avoid circular imports and premature mapper initialization
from sqlalchemy.orm import aliased, column_property
from sqlalchemy import select, func

ChildProduct = aliased(Product)
Product.stock = column_property(
    select(func.coalesce(func.sum(ProductInventory.stock), 0)).where(
        (ProductInventory.product_id == Product.id) | 
        ProductInventory.product_id.in_(
            select(ChildProduct.id).where(ChildProduct.parent_product_id == Product.id).correlate(Product)
        )
    ).correlate(Product).scalar_subquery()
)
