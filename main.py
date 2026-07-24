from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import settings
from core.rate_limiter import limiter
from routers import (
    auth_router, products_router, cart_router,
    dealers_router, admin_router,
    wishlist_router, addresses_router, reviews_router,
    coupons_router, flash_sales_router, bulk_discounts_router,
    payments_router, order_management_router,
    inventory_router, notifications_router,
    analytics_router, upload_router, social_router, support_tickets_router,
    riders_router, rider_reviews_router, locations_router,
    showroom_router, dealer_docs_router, payment_settings_router,
    finance_router, logistics_router, recharge_router, rewards_router,
    partners_router, referrals_router
)
from auction.routers import auction_router
from b2b_auction.routers import router as b2b_auction_router, product_router as b2b_products_router, order_router as b2b_orders_router

app = FastAPI(title=settings.PROJECT_NAME)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        body_str = body.decode()
    except Exception:
        body_str = "Could not read body (possibly already consumed by form-parser)"
        
    print(f"DEBUG: Validation Error for {request.method} {request.url}")
    print(f"DEBUG: Body: {body_str}")
    print(f"DEBUG: Errors: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "body": body_str},
    )

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:8081",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000",
        "http://10.0.2.2:8081",  # Android emulator
        "*",                      # Allow all others (mobile apps don't send Origin)
    ],
    allow_credentials=False,      # Token is in Authorization header, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(products_router, prefix="/api/v1")
app.include_router(cart_router, prefix="/api/v1")
app.include_router(dealers_router, prefix="/api/v1/dealers", tags=["dealers"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(wishlist_router, prefix="/api/v1/wishlist", tags=["wishlist"])
app.include_router(addresses_router, prefix="/api/v1/addresses", tags=["addresses"])
app.include_router(reviews_router, prefix="/api/v1/reviews", tags=["reviews"])
app.include_router(coupons_router, prefix="/api/v1/coupons", tags=["coupons"])
app.include_router(flash_sales_router, prefix="/api/v1/flash-sales", tags=["flash-sales"])
app.include_router(bulk_discounts_router, prefix="/api/v1/bulk-discounts", tags=["bulk-discounts"])
app.include_router(payments_router, prefix="/api/v1/payments", tags=["payments"])
app.include_router(order_management_router, prefix="/api/v1", tags=["order-management"])
app.include_router(inventory_router, prefix="/api/v1", tags=["inventory"])
app.include_router(notifications_router, prefix="/api/v1", tags=["notifications"])
app.include_router(analytics_router, prefix="/api/v1", tags=["analytics"])
app.include_router(upload_router, prefix="/api/v1", tags=["upload"])
app.include_router(social_router, prefix="/api/v1/social", tags=["social"])
app.include_router(support_tickets_router, prefix="/api/v1/support-tickets", tags=["support"])
app.include_router(riders_router, prefix="/api/v1/riders", tags=["riders"])
app.include_router(rider_reviews_router, prefix="/api/v1/rider-reviews", tags=["rider-reviews"])
app.include_router(locations_router, prefix="/api/v1/locations", tags=["locations"])
app.include_router(showroom_router, prefix="/api/v1/showrooms", tags=["showrooms"])
app.include_router(dealer_docs_router, prefix="/api/v1/admin/dealers", tags=["admin-dealer-docs"])
app.include_router(payment_settings_router, prefix="/api/v1", tags=["payment-settings"])
app.include_router(finance_router, prefix="/api/v1", tags=["finance"])
app.include_router(logistics_router, prefix="/api/v1/logistics", tags=["logistics"])
app.include_router(recharge_router, prefix="/api/v1/recharge", tags=["recharge"])
app.include_router(rewards_router, prefix="/api/v1/rewards", tags=["rewards"])
app.include_router(partners_router, prefix="/api/v1/superadmin/partners", tags=["superadmin-partners"])
app.include_router(auction_router, prefix="/api/v1", tags=["auction"])
app.include_router(referrals_router, prefix="/api/v1")
app.include_router(b2b_products_router, prefix="/api/v1", tags=["B2B Products"])
app.include_router(b2b_auction_router, prefix="/api/v1", tags=["B2B Auctions"])
app.include_router(b2b_orders_router, prefix="/api/v1", tags=["B2B Orders"])

@app.get("/")
def read_root():
    return {"message": "Welcome to OnlineshopApp API - Myntra Clone"}

@app.get("/api/v1/health")
@limiter.limit("100/minute")
def health_check(request: Request):
    return {"status": "ok", "app": settings.PROJECT_NAME}

import asyncio
from core.support_escalation import start_support_escalation_loop

@app.on_event("startup")
async def startup_event():
    # Automatically sync schema and create missing tables / columns
    try:
        from core.database import engine, Base
        from sqlalchemy import text
        import models.referral  # ensure referral models are registered with Base.metadata
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE categories ADD COLUMN IF NOT EXISTS referral_commission_rate DOUBLE PRECISION;"))
            await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS wallet_amount_used DOUBLE PRECISION DEFAULT 0.0;"))
            await conn.run_sync(Base.metadata.create_all)
        print("INFO: Successfully verified/created referral tables, wallet_transactions, and orders.wallet_amount_used column.")
    except Exception as e:
        print(f"WARNING: Schema auto-migration on startup encountered: {e}")

    # Start the support escalation background loop
    asyncio.create_task(start_support_escalation_loop())
