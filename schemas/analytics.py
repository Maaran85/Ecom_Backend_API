from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime

# Overview Dashboard
class AnalyticsOverview(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    total_products: int
    revenue_growth: str
    order_growth: str
    average_order_value: float
    top_selling_products: List[Dict]
    recent_orders: List[Dict]

class DealerAnalyticsOverview(BaseModel):
    total_revenue: float
    total_orders: int
    total_products: int
    pending_orders: int
    out_of_stock_count: int
    revenue_growth: str
    order_growth: str
    top_selling_products: List[Dict]
    recent_orders: List[Dict]
    return_exchange_stats: Dict[str, int]
    support_stats: Dict[str, int]

# Sales Analytics
class SalesByPeriod(BaseModel):
    date: str
    sales: float
    orders: int
    average: float

class SalesAnalytics(BaseModel):
    period: str
    total_sales: float
    total_orders: int
    average_order_value: float
    sales_by_period: List[SalesByPeriod]
    sales_by_category: Dict[str, float]
    sales_by_payment_method: Dict[str, float]

# Revenue Tracking
class PeriodRevenue(BaseModel):
    revenue: float
    orders: int
    refunds: float
    net_revenue: float

class RevenueGrowth(BaseModel):
    revenue_growth: str
    order_growth: str
    net_revenue_growth: str

class RevenueBreakdown(BaseModel):
    product_sales: float
    shipping: float
    discounts_applied: float
    refunds: float

class RevenueAnalytics(BaseModel):
    current_period: PeriodRevenue
    previous_period: PeriodRevenue
    growth: RevenueGrowth
    revenue_breakdown: RevenueBreakdown

# Product Performance
class ProductPerformance(BaseModel):
    product_id: int
    product_name: str
    total_sold: int
    revenue: float
    average_rating: Optional[float]
    stock_remaining: int
    conversion_rate: Optional[str]

class ProductAnalytics(BaseModel):
    top_products: List[ProductPerformance]
    low_performers: List[ProductPerformance]
    out_of_stock: List[Dict]

# Customer Insights
class TopCustomer(BaseModel):
    user_id: int
    name: str
    email: str
    total_orders: int
    total_spent: float
    average_order: float
    last_order: Optional[datetime]

class CustomerAnalytics(BaseModel):
    total_customers: int
    new_customers_this_month: int
    active_customers: int
    customer_lifetime_value: float
    top_customers: List[TopCustomer]
    customer_segments: Dict[str, int]

# Order Analytics
class OrderAnalytics(BaseModel):
    total_orders: int
    order_status_breakdown: Dict[str, int]
    average_processing_time: str
    average_delivery_time: str
    cancellation_rate: str
    return_rate: str
