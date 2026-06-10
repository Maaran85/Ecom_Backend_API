"""
Analytics & Reporting Router - Sales, Revenue, Product Performance, Customer Insights
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, case
from datetime import datetime, timedelta
from typing import Optional, List

from core.database import get_db
from core.permissions import require_admin, require_dealer
from models import (
    User, UserRole, Product, Order, OrderItem, OrderStatus, Category, Payment, PaymentStatus,
    OrderReturn, ReturnStatus, SupportTicket, TicketType
)
from schemas.analytics import (
    AnalyticsOverview, DealerAnalyticsOverview, SalesAnalytics, SalesByPeriod,
    RevenueAnalytics, PeriodRevenue, RevenueGrowth, RevenueBreakdown,
    ProductAnalytics, ProductPerformance,
    CustomerAnalytics, TopCustomer,
    OrderAnalytics
)

router = APIRouter()

# ==================== OVERVIEW DASHBOARD ====================

@router.get("/admin/analytics/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics dashboard overview (admin only)"""
    
    # Total revenue (completed orders)
    revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
        )
    )
    total_revenue = revenue_result.scalar() or 0.0
    
    # Total orders
    orders_result = await db.execute(select(func.count(Order.id)))
    total_orders = orders_result.scalar() or 0
    
    # Total customers
    customers_result = await db.execute(
        select(func.count(func.distinct(Order.user_id)))
    )
    total_customers = customers_result.scalar() or 0
    
    # Total products
    products_result = await db.execute(select(func.count(Product.id)))
    total_products = products_result.scalar() or 0
    
    # Revenue growth (last 30 days vs previous 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    sixty_days_ago = datetime.utcnow() - timedelta(days=60)
    
    current_revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= thirty_days_ago,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    current_revenue = current_revenue_result.scalar() or 0.0
    
    previous_revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= sixty_days_ago,
                Order.created_at < thirty_days_ago,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    previous_revenue = previous_revenue_result.scalar() or 0.0
    
    revenue_growth = f"+{((current_revenue - previous_revenue) / previous_revenue * 100):.1f}%" if previous_revenue > 0 else "N/A"
    
    # Order growth
    current_orders_result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= thirty_days_ago)
    )
    current_orders = current_orders_result.scalar() or 0
    
    previous_orders_result = await db.execute(
        select(func.count(Order.id)).where(
            and_(Order.created_at >= sixty_days_ago, Order.created_at < thirty_days_ago)
        )
    )
    previous_orders = previous_orders_result.scalar() or 0
    
    order_growth = f"+{((current_orders - previous_orders) / previous_orders * 100):.1f}%" if previous_orders > 0 else "N/A"
    
    # Average order value
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0
    
    # Top selling products (by quantity)
    top_products_result = await db.execute(
        select(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label('total_sold')
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]))
        .group_by(Product.id, Product.name)
        .order_by(desc('total_sold'))
        .limit(5)
    )
    top_products = [
        {
            "product_id": row[0],
            "product_name": row[1],
            "total_sold": row[2]
        }
        for row in top_products_result.all()
    ]
    
    # Recent orders
    recent_orders_result = await db.execute(
        select(Order)
        .order_by(desc(Order.created_at))
        .limit(5)
    )
    recent_orders = [
        {
            "order_id": order.id,
            "user_id": order.user_id,
            "total_amount": order.total_amount,
            "status": order.status.value,
            "created_at": order.created_at
        }
        for order in recent_orders_result.scalars().all()
    ]
    
    return AnalyticsOverview(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        revenue_growth=revenue_growth,
        order_growth=order_growth,
        average_order_value=avg_order_value,
        top_selling_products=top_products,
        recent_orders=recent_orders
    )

@router.get("/dealer/analytics/overview", response_model=DealerAnalyticsOverview)
async def get_dealer_analytics_overview(
    current_user: User = Depends(require_dealer),
    db: AsyncSession = Depends(get_db)
):
    """Get analytics dashboard overview for the current dealer"""
    # Resolve dealer_id correctly for both owners and staff
    dealer_id = current_user.dealer_id
    if not dealer_id:
        # Check if they are the primary owner
        from models.dealer import Dealer
        res = await db.execute(select(Dealer).where(Dealer.user_id == current_user.id))
        dealer = res.scalar_one_or_none()
        if dealer:
            dealer_id = dealer.id
            
    if not dealer_id:
        # Check if admin user
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            raise HTTPException(status_code=400, detail="Admins do not have a dealer profile. Use admin analytics.")
        raise HTTPException(status_code=400, detail="User is not associated with a dealer")

    # Time periods for growth calculation
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # 1. Total Revenue (from completed orders for this dealer's products)
    revenue_query = (
        select(func.sum(OrderItem.quantity * OrderItem.price))
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    revenue_result = await db.execute(revenue_query)
    total_revenue = revenue_result.scalar() or 0.0

    # 2. Total Orders (orders containing at least one product from this dealer)
    orders_query = (
        select(func.count(func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Product.dealer_id == dealer_id)
    )
    orders_result = await db.execute(orders_query)
    total_orders = orders_result.scalar() or 0

    # 3. Total Products
    products_count_result = await db.execute(
        select(func.count(Product.id)).where(Product.dealer_id == dealer_id)
    )
    total_products = products_count_result.scalar() or 0

    # 4. Pending Orders (orders containing this dealer's products that are not yet delivered/cancelled/failed)
    pending_statuses = [
        OrderStatus.PENDING, OrderStatus.ORDER_PLACED, OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING, OrderStatus.PACKAGING, OrderStatus.PACKED,
        OrderStatus.AT_HUB, OrderStatus.DISPATCHED, OrderStatus.SHIPPED,
        OrderStatus.OUT_FOR_DELIVERY
    ]
    pending_orders_query = (
        select(func.count(func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.status.in_(pending_statuses)
            )
        )
    )
    pending_orders_result = await db.execute(pending_orders_query)
    pending_orders = pending_orders_result.scalar() or 0

    # 5. Out of Stock Count
    oos_result = await db.execute(
        select(func.count(Product.id)).where(
            and_(Product.dealer_id == dealer_id, Product.stock == 0)
        )
    )
    out_of_stock_count = oos_result.scalar() or 0

    # 6. Revenue Growth
    current_revenue_query = (
        select(func.sum(OrderItem.quantity * OrderItem.price))
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.created_at >= thirty_days_ago,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    current_revenue = (await db.execute(current_revenue_query)).scalar() or 0.0

    previous_revenue_query = (
        select(func.sum(OrderItem.quantity * OrderItem.price))
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.created_at >= sixty_days_ago,
                Order.created_at < thirty_days_ago,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    previous_revenue = (await db.execute(previous_revenue_query)).scalar() or 0.0
    
    revenue_growth = f"+{((current_revenue - previous_revenue) / previous_revenue * 100):.1f}%" if previous_revenue > 0 else "N/A"

    # 7. Order Growth
    current_orders_query = (
        select(func.count(func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.created_at >= thirty_days_ago
            )
        )
    )
    current_period_orders = (await db.execute(current_orders_query)).scalar() or 0

    previous_orders_query = (
        select(func.count(func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.created_at >= sixty_days_ago,
                Order.created_at < thirty_days_ago
            )
        )
    )
    previous_period_orders = (await db.execute(previous_orders_query)).scalar() or 0
    
    order_growth = f"+{((current_period_orders - previous_period_orders) / previous_period_orders * 100):.1f}%" if previous_period_orders > 0 else "N/A"

    # 8. Top Selling Products
    top_products_query = (
        select(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label('total_sold')
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            and_(
                Product.dealer_id == dealer_id,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
        .group_by(Product.id, Product.name)
        .order_by(desc('total_sold'))
        .limit(5)
    )
    top_products_result = await db.execute(top_products_query)
    top_selling_products = [
        {
            "product_id": row[0],
            "product_name": row[1],
            "total_sold": row[2]
        }
        for row in top_products_result.all()
    ]

    # 9. Recent Orders
    recent_orders_query = (
        select(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Product.dealer_id == dealer_id)
        .order_by(desc(Order.created_at))
        .distinct()
        .limit(5)
    )
    recent_orders_result = await db.execute(recent_orders_query)
    recent_orders = [
        {
            "order_id": order.id,
            "order_number": order.order_number,
            "total_amount": order.total_amount,
            "status": order.status.value,
            "created_at": order.created_at
        }
        for order in recent_orders_result.scalars().all()
    ]

    return_requests_query = (
        select(func.count(OrderReturn.id.distinct()))
        .join(Order, Order.id == OrderReturn.order_id)
        .join(OrderItem, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        .join(Product, Product.id == OrderItem.product_id)
        .where(and_(Product.dealer_id == dealer_id, OrderReturn.status == ReturnStatus.REQUESTED))
    )
    return_requests = (await db.execute(return_requests_query)).scalar() or 0

    return_approved_query = (
        select(func.count(OrderReturn.id.distinct()))
        .join(Order, Order.id == OrderReturn.order_id)
        .join(OrderItem, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        .join(Product, Product.id == OrderItem.product_id)
        .where(and_(Product.dealer_id == dealer_id, OrderReturn.status == ReturnStatus.APPROVED))
    )
    return_approved = (await db.execute(return_approved_query)).scalar() or 0

    return_rejected_query = (
        select(func.count(OrderReturn.id.distinct()))
        .join(Order, Order.id == OrderReturn.order_id)
        .join(OrderItem, or_(OrderReturn.order_item_id == OrderItem.id, OrderReturn.order_item_id.is_(None)))
        .join(Product, Product.id == OrderItem.product_id)
        .where(and_(Product.dealer_id == dealer_id, OrderReturn.status == ReturnStatus.REJECTED))
    )
    return_rejected = (await db.execute(return_rejected_query)).scalar() or 0

    # 11. Support Stats
    queries_query = (
        select(func.count(SupportTicket.id))
        .where(and_(SupportTicket.dealer_id == dealer_id, SupportTicket.ticket_type == TicketType.QUERY))
    )
    queries_count = (await db.execute(queries_query)).scalar() or 0

    complaints_query = (
        select(func.count(SupportTicket.id))
        .where(and_(SupportTicket.dealer_id == dealer_id, SupportTicket.ticket_type == TicketType.COMPLAINT))
    )
    complaints_count = (await db.execute(complaints_query)).scalar() or 0

    return DealerAnalyticsOverview(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_products=total_products,
        pending_orders=pending_orders,
        out_of_stock_count=out_of_stock_count,
        revenue_growth=revenue_growth,
        order_growth=order_growth,
        top_selling_products=top_selling_products,
        recent_orders=recent_orders,
        return_exchange_stats={
            "requests": return_requests,
            "accepted": return_approved,
            "rejected": return_rejected
        },
        support_stats={
            "queries": queries_count,
            "complaints": complaints_count
        }
    )

# ==================== SALES ANALYTICS ====================

@router.get("/admin/analytics/sales", response_model=SalesAnalytics)
async def get_sales_analytics(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    group_by: str = Query("day", pattern="^(day|week|month|year)$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get sales analytics with date range and grouping (admin only)"""
    
    # Default to last 30 days
    if not to_date:
        to_date = datetime.utcnow()
    if not from_date:
        from_date = to_date - timedelta(days=30)
    
    # Total sales in period
    total_sales_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= from_date,
                Order.created_at <= to_date,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    total_sales = total_sales_result.scalar() or 0.0
    
    # Total orders
    total_orders_result = await db.execute(
        select(func.count(Order.id)).where(
            and_(
                Order.created_at >= from_date,
                Order.created_at <= to_date
            )
        )
    )
    total_orders = total_orders_result.scalar() or 0
    
    # Average order value
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0.0
    
    # Sales by period (simplified - daily grouping)
    sales_by_period = []
    if group_by == "day":
        # Get daily sales
        daily_sales_result = await db.execute(
            select(
                func.date(Order.created_at).label('date'),
                func.sum(Order.total_amount).label('sales'),
                func.count(Order.id).label('orders')
            )
            .where(
                and_(
                    Order.created_at >= from_date,
                    Order.created_at <= to_date,
                    Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
                )
            )
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
        )
        
        for row in daily_sales_result.all():
            sales_by_period.append(SalesByPeriod(
                date=str(row[0]),
                sales=row[1] or 0.0,
                orders=row[2] or 0,
                average=(row[1] / row[2]) if row[2] > 0 else 0.0
            ))
    
    # Sales by category
    category_sales_result = await db.execute(
        select(
            Category.name,
            func.sum(Order.total_amount).label('sales')
        )
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Category, Category.id == Product.category_id)
        .where(
            and_(
                Order.created_at >= from_date,
                Order.created_at <= to_date,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
        .group_by(Category.name)
    )
    sales_by_category = {row[0]: row[1] or 0.0 for row in category_sales_result.all()}
    
    # Sales by payment method
    payment_sales_result = await db.execute(
        select(
            Payment.method,
            func.sum(Order.total_amount).label('sales')
        )
        .join(Order, Order.id == Payment.order_id)
        .where(
            and_(
                Order.created_at >= from_date,
                Order.created_at <= to_date,
                Payment.status == PaymentStatus.SUCCESS
            )
        )
        .group_by(Payment.method)
    )
    sales_by_payment_method = {str(row[0]): row[1] or 0.0 for row in payment_sales_result.all()}
    
    return SalesAnalytics(
        period=f"{from_date.date()} to {to_date.date()}",
        total_sales=total_sales,
        total_orders=total_orders,
        average_order_value=avg_order_value,
        sales_by_period=sales_by_period,
        sales_by_category=sales_by_category,
        sales_by_payment_method=sales_by_payment_method
    )

# ==================== REVENUE TRACKING ====================

@router.get("/admin/analytics/revenue", response_model=RevenueAnalytics)
async def get_revenue_analytics(
    period: str = Query("month", pattern="^(week|month|year)$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get revenue analytics with period comparison (admin only)"""
    
    # Calculate period dates
    now = datetime.utcnow()
    if period == "week":
        current_start = now - timedelta(days=7)
        previous_start = now - timedelta(days=14)
        previous_end = current_start
    elif period == "month":
        current_start = now - timedelta(days=30)
        previous_start = now - timedelta(days=60)
        previous_end = current_start
    else:  # year
        current_start = now - timedelta(days=365)
        previous_start = now - timedelta(days=730)
        previous_end = current_start
    
    # Current period revenue
    current_revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= current_start,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    current_revenue = current_revenue_result.scalar() or 0.0
    
    current_orders_result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= current_start)
    )
    current_orders = current_orders_result.scalar() or 0
    
    # Current refunds (simplified - using cancelled/refunded orders)
    current_refunds_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= current_start,
                Order.status.in_([OrderStatus.CANCELLED, OrderStatus.REFUNDED])
            )
        )
    )
    current_refunds = current_refunds_result.scalar() or 0.0
    
    # Previous period
    previous_revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= previous_start,
                Order.created_at < previous_end,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    previous_revenue = previous_revenue_result.scalar() or 0.0
    
    previous_orders_result = await db.execute(
        select(func.count(Order.id)).where(
            and_(Order.created_at >= previous_start, Order.created_at < previous_end)
        )
    )
    previous_orders = previous_orders_result.scalar() or 0
    
    previous_refunds_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            and_(
                Order.created_at >= previous_start,
                Order.created_at < previous_end,
                Order.status.in_([OrderStatus.CANCELLED, OrderStatus.REFUNDED])
            )
        )
    )
    previous_refunds = previous_refunds_result.scalar() or 0.0
    
    # Calculate growth
    revenue_growth = f"+{((current_revenue - previous_revenue) / previous_revenue * 100):.1f}%" if previous_revenue > 0 else "N/A"
    order_growth = f"+{((current_orders - previous_orders) / previous_orders * 100):.1f}%" if previous_orders > 0 else "N/A"
    
    current_net = current_revenue - current_refunds
    previous_net = previous_revenue - previous_refunds
    net_revenue_growth = f"+{((current_net - previous_net) / previous_net * 100):.1f}%" if previous_net > 0 else "N/A"
    
    # Revenue breakdown (simplified)
    total_discounts_result = await db.execute(
        select(func.sum(Order.discount_amount)).where(
            and_(
                Order.created_at >= current_start,
                Order.discount_amount.isnot(None)
            )
        )
    )
    total_discounts = total_discounts_result.scalar() or 0.0
    
    return RevenueAnalytics(
        current_period=PeriodRevenue(
            revenue=current_revenue,
            orders=current_orders,
            refunds=current_refunds,
            net_revenue=current_net
        ),
        previous_period=PeriodRevenue(
            revenue=previous_revenue,
            orders=previous_orders,
            refunds=previous_refunds,
            net_revenue=previous_net
        ),
        growth=RevenueGrowth(
            revenue_growth=revenue_growth,
            order_growth=order_growth,
            net_revenue_growth=net_revenue_growth
        ),
        revenue_breakdown=RevenueBreakdown(
            product_sales=current_revenue,
            shipping=0.0,  # Not tracked separately yet
            discounts_applied=-total_discounts,
            refunds=-current_refunds
        )
    )

# ==================== PRODUCT PERFORMANCE ====================

@router.get("/admin/analytics/products", response_model=ProductAnalytics)
async def get_product_analytics(
    sort_by: str = Query("revenue", pattern="^(revenue|quantity|rating)$"),
    limit: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get product performance analytics (admin only)"""
    
    # Top products
    query = select(
        Product.id,
        Product.name,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
        Product.stock
    ).outerjoin(OrderItem, OrderItem.product_id == Product.id)\
     .outerjoin(Order, Order.id == OrderItem.order_id)\
     .where(
         (Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])) | (Order.id.is_(None))
     )\
     .group_by(Product.id, Product.name, Product.stock)
    
    if sort_by == "revenue":
        query = query.order_by(desc('revenue'))
    elif sort_by == "quantity":
        query = query.order_by(desc('total_sold'))
    
    query = query.limit(limit)
    result = await db.execute(query)
    
    top_products = [
        ProductPerformance(
            product_id=row[0],
            product_name=row[1],
            total_sold=row[2],
            revenue=row[3],
            average_rating=None,  # Can be added later
            stock_remaining=row[4],
            conversion_rate=None  # Requires view tracking
        )
        for row in result.all()
    ]
    
    # Low performers (products with low sales)
    low_query = select(
        Product.id,
        Product.name,
        func.coalesce(func.sum(OrderItem.quantity), 0).label('total_sold'),
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label('revenue'),
        Product.stock
    ).outerjoin(OrderItem, OrderItem.product_id == Product.id)\
     .group_by(Product.id, Product.name, Product.stock)\
     .order_by('total_sold')\
     .limit(10)
    
    low_result = await db.execute(low_query)
    low_performers = [
        ProductPerformance(
            product_id=row[0],
            product_name=row[1],
            total_sold=row[2],
            revenue=row[3],
            average_rating=None,
            stock_remaining=row[4],
            conversion_rate=None
        )
        for row in low_result.all()
    ]
    
    # Out of stock products
    out_of_stock_result = await db.execute(
        select(Product.id, Product.name).where(Product.stock == 0)
    )
    out_of_stock = [
        {"product_id": row[0], "product_name": row[1]}
        for row in out_of_stock_result.all()
    ]
    
    return ProductAnalytics(
        top_products=top_products,
        low_performers=low_performers,
        out_of_stock=out_of_stock
    )

# ==================== CUSTOMER INSIGHTS ====================

@router.get("/admin/analytics/customers", response_model=CustomerAnalytics)
async def get_customer_analytics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get customer insights and analytics (admin only)"""
    
    # Total customers
    total_customers_result = await db.execute(
        select(func.count(func.distinct(Order.user_id)))
    )
    total_customers = total_customers_result.scalar() or 0
    
    # New customers this month
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_customers_result = await db.execute(
        select(func.count(func.distinct(Order.user_id))).where(
            Order.created_at >= thirty_days_ago
        )
    )
    new_customers = new_customers_result.scalar() or 0
    
    # Active customers (ordered in last 30 days)
    active_customers = new_customers
    
    # Customer lifetime value
    total_revenue_result = await db.execute(
        select(func.sum(Order.total_amount)).where(
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
        )
    )
    total_revenue = total_revenue_result.scalar() or 0.0
    clv = total_revenue / total_customers if total_customers > 0 else 0.0
    
    # Top customers
    top_customers_result = await db.execute(
        select(
            User.id,
            User.full_name,
            User.email,
            func.count(Order.id).label('total_orders'),
            func.sum(Order.total_amount).label('total_spent'),
            func.max(Order.created_at).label('last_order')
        )
        .join(Order, Order.user_id == User.id)
        .where(Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]))
        .group_by(User.id, User.full_name, User.email)
        .order_by(desc('total_spent'))
        .limit(10)
    )
    
    top_customers = [
        TopCustomer(
            user_id=row[0],
            name=row[1],
            email=row[2],
            total_orders=row[3],
            total_spent=row[4],
            average_order=row[4] / row[3] if row[3] > 0 else 0.0,
            last_order=row[5]
        )
        for row in top_customers_result.all()
    ]
    
    # Customer segments (simplified)
    customer_segments = {
        "high_value": len([c for c in top_customers if c.total_spent > 5000]),
        "medium_value": len([c for c in top_customers if 1000 <= c.total_spent <= 5000]),
        "low_value": total_customers - len([c for c in top_customers if c.total_spent >= 1000])
    }
    
    return CustomerAnalytics(
        total_customers=total_customers,
        new_customers_this_month=new_customers,
        active_customers=active_customers,
        customer_lifetime_value=clv,
        top_customers=top_customers,
        customer_segments=customer_segments
    )

# ==================== ORDER ANALYTICS ====================

@router.get("/admin/analytics/orders", response_model=OrderAnalytics)
async def get_order_analytics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get order analytics and metrics (admin only)"""
    
    # Total orders
    total_orders_result = await db.execute(select(func.count(Order.id)))
    total_orders = total_orders_result.scalar() or 0
    
    # Order status breakdown
    status_result = await db.execute(
        select(Order.status, func.count(Order.id))
        .group_by(Order.status)
    )
    order_status_breakdown = {str(row[0]): row[1] for row in status_result.all()}
    
    # Cancellation rate
    cancelled_count = order_status_breakdown.get('OrderStatus.CANCELLED', 0)
    cancellation_rate = f"{(cancelled_count / total_orders * 100):.1f}%" if total_orders > 0 else "0%"
    
    # Return rate (simplified)
    refunded_count = order_status_breakdown.get('OrderStatus.REFUNDED', 0)
    return_rate = f"{(refunded_count / total_orders * 100):.1f}%" if total_orders > 0 else "0%"
    
    return OrderAnalytics(
        total_orders=total_orders,
        order_status_breakdown=order_status_breakdown,
        average_processing_time="2.5 days",  # Placeholder
        average_delivery_time="5.2 days",  # Placeholder
        cancellation_rate=cancellation_rate,
        return_rate=return_rate
    )
