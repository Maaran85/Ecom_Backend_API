from .auth import router as auth_router
from .products import router as products_router
from .cart import router as cart_router
from .dealers import router as dealers_router
from .admin import router as admin_router
from .wishlist import router as wishlist_router
from .addresses import router as addresses_router
from .reviews import router as reviews_router
from .variants import router as variants_router
from .coupons import router as coupons_router
from .flash_sales import router as flash_sales_router
from .bulk_discounts import router as bulk_discounts_router
from .payments import router as payments_router
from .order_management import router as order_management_router
from .inventory import router as inventory_router
from .notifications import router as notifications_router
from .analytics import router as analytics_router
from .upload import router as upload_router
from .social import router as social_router
from .support_tickets import router as support_tickets_router
from .riders import router as riders_router
from .rider_reviews import router as rider_reviews_router
from .locations import router as locations_router
from .showroom import router as showroom_router
from .dealer_docs import router as dealer_docs_router
from .payment_settings import router as payment_settings_router
from .finance import router as finance_router
from .logistics import router as logistics_router
from .recharge import router as recharge_router
from .rewards import router as rewards_router
from .partners import router as partners_router

__all__ = [
    "auth_router", "products_router", "cart_router",
    "dealers_router", "admin_router",
    "wishlist_router", "addresses_router", "reviews_router", "variants_router",
    "coupons_router", "flash_sales_router", "bulk_discounts_router",
    "payments_router", "order_management_router",
    "inventory_router", "notifications_router",
    "analytics_router", "upload_router", "social_router", "support_tickets_router",
    "riders_router", "rider_reviews_router", "locations_router",
    "showroom_router", "dealer_docs_router", "payment_settings_router",
    "finance_router", "logistics_router",
    "rewards_router", "partners_router"
]
