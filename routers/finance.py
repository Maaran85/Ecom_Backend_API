from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_, update
from datetime import datetime, timedelta
from typing import List, Optional

from core.database import get_db
from core.permissions import require_admin, get_current_active_user
from models import User, Order, OrderItem, OrderStatus, Dealer, Product, TaxCategory, TaxRule, TaxLedger, DealerRemittance
from schemas.finance import (
    TaxCategoryCreate, TaxCategoryUpdate, TaxCategoryOut,
    TaxRuleCreate, TaxRuleUpdate, TaxRuleOut,
    PLReportOut, GST1SummaryOut, GST1SummaryRow, 
    TDSReportOut, DealerPayoutRow, TaxCalculatorRequest,
    DealerRemittanceCreate, 
    DealerRemittanceOut, 
    DealerRemittanceStatusUpdate,
    DealerRemittanceSubmit
)
from services.tax_service import TaxService
from fastapi.responses import StreamingResponse
import io
import csv

router = APIRouter()

# ==========================================
# TAX CATEGORY MANAGEMENT
# ==========================================

@router.get("/admin/finance/tax-categories", response_model=List[TaxCategoryOut])
async def list_tax_categories(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    result = await db.execute(select(TaxCategory).order_by(TaxCategory.name))
    return result.scalars().all()

@router.post("/admin/finance/tax-categories", response_model=TaxCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_tax_category(
    data: TaxCategoryCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    existing = await db.execute(select(TaxCategory).where(TaxCategory.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tax category with this name already exists")
        
    category = TaxCategory(**data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

@router.put("/admin/finance/tax-categories/{category_id}", response_model=TaxCategoryOut)
async def update_tax_category(
    category_id: int,
    data: TaxCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    category = await db.get(TaxCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Tax Category not found")
        
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(category, key, value)
        
    await db.commit()
    await db.refresh(category)
    return category

# ==========================================
# TAX RULE MANAGEMENT
# ==========================================

@router.get("/admin/finance/tax-rules", response_model=List[TaxRuleOut])
async def list_tax_rules(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    # Eager load the tax category
    result = await db.execute(
        select(TaxRule).order_by(TaxRule.priority.desc())
    )
    rules = result.scalars().all()
    # Manual load of relationships for the response
    for rule in rules:
        if rule.tax_category_id:
            rule.tax_category = await db.get(TaxCategory, rule.tax_category_id)
    return rules

@router.post("/admin/finance/tax-rules", response_model=TaxRuleOut, status_code=status.HTTP_201_CREATED)
async def create_tax_rule(
    data: TaxRuleCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    # Verify tax category exists
    tax_cat = await db.get(TaxCategory, data.tax_category_id)
    if not tax_cat:
        raise HTTPException(status_code=400, detail="Invalid tax_category_id")
        
    rule = TaxRule(**data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    rule.tax_category = tax_cat
    return rule

@router.put("/admin/finance/tax-rules/{rule_id}", response_model=TaxRuleOut)
async def update_tax_rule(
    rule_id: int,
    data: TaxRuleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    rule = await db.get(TaxRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Tax Rule not found")
        
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
        
    await db.commit()
    await db.refresh(rule)
    
    if rule.tax_category_id:
        rule.tax_category = await db.get(TaxCategory, rule.tax_category_id)
    return rule

@router.delete("/admin/finance/tax-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tax_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    rule = await db.get(TaxRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Tax Rule not found")
        
    await db.delete(rule)
    await db.commit()

# Public/Dealer accessible tax rules
@router.get("/finance/tax-rules", response_model=List[TaxRuleOut])
async def get_tax_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all active tax rules for selection during product creation"""
    result = await db.execute(
        select(TaxRule).where(TaxRule.is_active == True).order_by(TaxRule.priority.desc())
    )
    rules = result.scalars().all()
    for rule in rules:
        if rule.tax_category_id:
            rule.tax_category = await db.get(TaxCategory, rule.tax_category_id)
    return rules

# ==========================================
# DEALER FINANCE SETTINGS
# ==========================================

@router.get("/finance/dealer/settings")
async def get_dealer_finance_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Returns financial settings for the logged-in dealer (including effective platform fee)"""
    from .dealers import get_current_dealer
    from models.payment_settings import PlatformPaymentSettings

    dealer = await get_current_dealer(current_user, db)
    if not dealer:
         raise HTTPException(status_code=404, detail="Dealer profile not found")
    
    # Try to fetch global platform fee from active payment settings if dealer fee is default
    # Or just return both and let the frontend decide, but usually we want one "effective" fee.
    effective_fee = dealer.platform_fee_percent
    
    # If dealer fee is the initial default (5.0), check if there's an admin-configured global fee
    if effective_fee == 5.0:
        result = await db.execute(
            select(PlatformPaymentSettings.platform_fee_percent)
            .where(PlatformPaymentSettings.is_active == True)
            .limit(1)
        )
        global_fee = result.scalar()
        if global_fee is not None:
            effective_fee = global_fee

    return {
        "platform_fee_percent": effective_fee,
        "dealer_custom_fee": dealer.platform_fee_percent
    }


@router.get("/finance/dealer/remittance-balance")
async def get_dealer_remittance_balance(
    remittance_type: Optional[str] = Query(None, pattern="^(payout|collection)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Returns the dealer's remittance balance:
    - How much admin owes them (pending unremitted items)
    - How much has already been settled
    - Recent pending items and settlement history
    """
    from .dealers import get_current_dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    # ── 1. Unremitted (pending) items for this dealer ──────────────────────────
    pending_query = (
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer.id,
                func.lower(OrderItem.status) == "delivered",
                OrderItem.dealer_remittance_id.is_(None),
                # 1. Platform owes Dealer: COD orders handled by logistics partner
                and_(
                    func.lower(func.coalesce(Order.payment_method, "cod")).in_(["cod", "cash"]),
                    OrderItem.logistics_partner_id.isnot(None)
                )
            )
        )
    )
    pending_items = []
    if remittance_type in [None, "payout"]:
        pending_result = await db.execute(pending_query)
        pending_items = pending_result.scalars().all()

    # ── 1b. Items where Dealer owes Platform (Fees for own-rider COD) ───────────
    collection_query = (
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer.id,
                func.lower(OrderItem.status) == "delivered",
                OrderItem.dealer_remittance_id.is_(None),
                # Dealer has cash: COD AND own_rider delivery (or implicitly handled by dealer with no logistics/hub)
                func.lower(func.coalesce(Order.payment_method, "cod")).in_(["cod", "cash"]),
                or_(
                    OrderItem.delivery_type == "own_rider",
                    and_(
                        OrderItem.logistics_partner_id.is_(None),
                        OrderItem.hub_id.is_(None)
                    )
                )
            )
        )
    )
    collection_items = []
    if remittance_type in [None, "collection"]:
        collection_result = await db.execute(collection_query)
        collection_items = collection_result.scalars().all()

    pending_amount = 0.0
    dealer_owes_amount = 0.0
    recent_pending = []

    for item in pending_items:
        prod = await db.get(Product, item.product_id)
        order = await db.get(Order, item.order_id)
        fee = float(item.platform_fee or 0.0)
        total_val = float(item.price or 0.0) * int(item.quantity or 1)
        total = round(float(total_val), 2)
        net = round(float(total - fee), 2)
        pending_amount += net
        payment_str = str(order.payment_method or "").lower() if order else ""
        is_cod_logistics = payment_str in ("cod", "cash") and bool(item.logistics_partner_id)
        recent_pending.append({
            "id": item.id,
            "order_number": (order.order_number if order else None) or f"ORD-{item.order_id}",
            "product_name": prod.name if prod else "Unknown",
            "quantity": int(item.quantity or 1),
            "net_amount": net,
            "payment_method": order.payment_method if order else None,
            "is_cod_logistics": is_cod_logistics,
            "remittance_type": "payout",
            "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
        })

    for item in collection_items:
        prod = await db.get(Product, item.product_id)
        order = await db.get(Order, item.order_id)
        fee = float(item.platform_fee or 0.0)
        dealer_owes_amount += fee
        recent_pending.append({
            "id": item.id,
            "order_number": (order.order_number if order else None) or f"ORD-{item.order_id}",
            "product_name": prod.name if prod else "Unknown",
            "quantity": int(item.quantity or 1),
            "net_amount": -fee, # Shown as negative since dealer owes it
            "payment_method": order.payment_method if order else None,
            "is_cod_logistics": False,
            "remittance_type": "collection",
            "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
        })

    # Sort recent pending by delivered_at descending, take last 10
    recent_pending.sort(key=lambda x: x["delivered_at"] or "", reverse=True)

    # ── 2. Settled remittances for this dealer ─────────────────────────────────
    history_query = select(DealerRemittance).where(DealerRemittance.dealer_id == dealer.id)
    if remittance_type:
        history_query = history_query.where(getattr(DealerRemittance, 'type', 'payout') == remittance_type)
    
    remittances_result = await db.execute(history_query.order_by(DealerRemittance.created_at.desc()))
    remittances = remittances_result.scalars().all()

    settled_amount = sum(float(r.amount or 0) for r in remittances if r.status == "completed")

    remittance_list = []
    for r in remittances:
        # Fetch linked order numbers
        linked_items = await db.execute(
            select(OrderItem).where(OrderItem.dealer_remittance_id == r.id)
        )
        linked = linked_items.scalars().all()
        order_numbers = []
        for li in linked:
            ord_ = await db.get(Order, li.order_id)
            if ord_ and ord_.order_number:
                order_numbers.append(ord_.order_number)

        remittance_list.append({
            "id": r.id,
            "amount": float(r.amount or 0),
            "status": r.status,
            "type": getattr(r, 'type', 'payout'),
            "reference_no": r.reference_no,
            "payment_method": r.payment_method,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "order_numbers": list(set(order_numbers)),
        })

    return {
        "dealer_name": dealer.business_name,
        "pending_amount": round(float(pending_amount), 2),
        "dealer_owes_amount": round(float(dealer_owes_amount), 2),
        "pending_items_count": len(pending_items) + len(collection_items),
        "settled_amount": round(float(settled_amount), 2),
        "recent_pending": recent_pending,
        "remittances": remittance_list,
    }


# ==========================================
# TAX CALCULATION PREVIEW 
# ==========================================

@router.post("/admin/finance/calculate-preview")
async def preview_tax_calculation(
    request: TaxCalculatorRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Utility endpoint to test how much tax is extracted from a price"""
    result = await TaxService.calculate_item_tax(
        db=db,
        inclusive_price=request.inclusive_price,
        qty=request.quantity,
        product_id=request.product_id,
        buyer_state=request.buyer_state,
        seller_state=request.seller_state
    )
    return result

# ==========================================
# FINANCIAL REPORTS
# ==========================================

@router.get("/admin/finance/reports/payouts", response_model=TDSReportOut)
async def get_tds_payout_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Calculates dealer payouts including Platform Commission, TCS, and TDS deductions.
    Formula: Gross Sales - Platform Fee - TCS(1%) - TDS(1%) = Net Payout
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # Find all delivered orders in this period
    query = (
        select(OrderItem, Order, Product, Dealer)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Dealer, Dealer.id == Product.dealer_id)
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at < end_date,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    dealer_stats = {}
    
    for item, order, product, dealer in rows:
        dealer_id = dealer.id
        if dealer_id not in dealer_stats:
            dealer_stats[dealer_id] = {
                "name": dealer.business_name,
                "gross_order_value": 0.0,
                "platform_commission": 0.0,
                "taxable_value": 0.0,
            }
            
        # The price saved on item is the inclusive price 
        gross_value = item.price * item.quantity
        
        # Calculate commission (EXTRACTED from the bundled price)
        fee_percent = dealer.platform_fee_percent if dealer else 5.0
        commission = gross_value * (fee_percent / (100.0 + fee_percent))
        
        # We need the net taxable value to calculate TCS under GST
        # Approximate taxable value extraction if not stored directly
        taxable_value = gross_value - (item.tax_amount or 0)
        
        dealer_stats[dealer_id]["gross_order_value"] += gross_value
        dealer_stats[dealer_id]["platform_commission"] += commission
        dealer_stats[dealer_id]["taxable_value"] += taxable_value

    payouts = []
    total_gross = 0.0
    total_comm = 0.0
    total_tcs = 0.0
    total_tds = 0.0
    total_net = 0.0

    for d_id, stats in dealer_stats.items():
        gov = stats["gross_order_value"]
        comm = stats["platform_commission"]
        taxable = stats["taxable_value"]
        
        # Amazon style deductions
        tcs = taxable * 0.01  # 1% under GST
        tds = gov * 0.01      # 1% under Sec 194-O (Gross value)
        
        net_payout = gov - comm - tcs - tds
        
        total_gross += gov
        total_comm += comm
        total_tcs += tcs
        total_tds += tds
        total_net += net_payout
        
        payouts.append(
            DealerPayoutRow(
                dealer_id=d_id,
                dealer_name=stats["name"],
                gross_order_value=round(gov, 2),
                refunds=0.0, # Simplification for now
                platform_commission=round(comm, 2),
                tcs_deduction=round(tcs, 2),
                tds_deduction=round(tds, 2),
                net_payout=round(net_payout, 2),
                status="Pending"
            )
        )

    return TDSReportOut(
        period=f"{datetime(year, month, 1).strftime('%B %Y')}",
        total_gross_value=round(total_gross, 2),
        total_platform_commission=round(total_comm, 2),
        total_tcs_withheld=round(total_tcs, 2),
        total_tds_withheld=round(total_tds, 2),
        total_net_payout=round(total_net, 2),
        payouts=payouts
    )

@router.get("/admin/finance/reports/gst", response_model=GST1SummaryOut)
async def get_gst_returns_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Calculates GST liability based on delivered orders. Note: this is a simplified MVP calculation.
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # Find all delivered orders in this period
    query = (
        select(OrderItem, Order, Product)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Order.created_at >= start_date,
                Order.created_at < end_date,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED])
            )
        )
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    total_b2c = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0

    hsn_stats = {}
    
    for item, order, product in rows:
        hsn = product.hsn_code or "Uncategorized"
        if hsn not in hsn_stats:
            hsn_stats[hsn] = {
                "desc": product.name,
                "qty": 0,
                "taxable": 0.0,
                "cgst": 0.0,
                "sgst": 0.0,
                "igst": 0.0,
            }
            
        gross_value = item.price * item.quantity
        item_tax = float(item.tax_amount or 0) * int(item.quantity or 1)
        if getattr(order, 'is_inter_state', False) or getattr(order, 'igst_amount', 0) > 0:
            igst = item_tax
            cgst = 0.0
            sgst = 0.0
        else:
            igst = 0.0
            cgst = item_tax / 2
            sgst = item_tax / 2
        total_tax = cgst + sgst + igst
        taxable_value = gross_value - total_tax
        
        total_b2c += gross_value
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst
        
        hsn_stats[hsn]["qty"] += item.quantity
        hsn_stats[hsn]["taxable"] += taxable_value
        hsn_stats[hsn]["cgst"] += cgst
        hsn_stats[hsn]["sgst"] += sgst
        hsn_stats[hsn]["igst"] += igst

    hsn_summary_out = []
    for hsn, stat in hsn_stats.items():
        hsn_summary_out.append(
            GST1SummaryRow(
                hsn_code=hsn,
                description=stat["desc"],
                total_quantity=stat["qty"],
                total_taxable_value=round(stat["taxable"], 2),
                total_cgst=round(stat["cgst"], 2),
                total_sgst=round(stat["sgst"], 2),
                total_igst=round(stat["igst"], 2),
                total_tax=round(stat["cgst"] + stat["sgst"] + stat["igst"], 2)
            )
        )
    return GST1SummaryOut(
        period=f"{month:02d}/{year}",
        total_b2c_sales=round(total_b2c, 2),
        total_b2b_sales=0.0, # Not currently tracking B2B
        total_cgst_collected=round(total_cgst, 2),
        total_sgst_collected=round(total_sgst, 2),
        total_igst_collected=round(total_igst, 2),
        hsn_summary=hsn_summary_out
    )


# ==========================================
# DEALER REMITTANCE MANAGEMENT (ORDER-WISE)
# ==========================================

@router.get("/admin/finance/debug-delivered-items")
async def debug_delivered_items(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Debug: Show all delivered order items with their payment methods (no filter)"""
    result = await db.execute(
        select(OrderItem, Order)
        .join(Order, Order.id == OrderItem.order_id)
        .where(func.lower(OrderItem.status) == "delivered")
        .limit(50)
    )
    rows = result.all()
    return [
        {
            "item_id": item.id,
            "order_id": order.id,
            "order_number": order.order_number,
            "item_status": item.status,
            "payment_method": order.payment_method,
            "logistics_partner_id": item.logistics_partner_id,
            "dealer_remittance_id": item.dealer_remittance_id,
        }
        for item, order in rows
    ]


@router.get("/admin/finance/unremitted-order-items")
async def list_unremitted_order_items(
    dealer_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    List delivered order items pending dealer remittance.
    Includes:
      1. Non-COD orders (UPI/card/online) — admin received money directly.
      2. COD orders assigned to a logistics partner — logistics partner
         collected the cash; admin now owes dealer.
    Excludes plain COD orders with no logistics partner (cash not received by admin yet).
    """
    # Base: delivered + not yet remitted to dealer
    base_conditions = and_(
        func.lower(OrderItem.status) == "delivered",
        OrderItem.dealer_remittance_id.is_(None),
    )

    # Payment filter: 
    # 1. Payout (Admin -> Dealer): COD and has logistics partner
    # 2. Collection (Dealer -> Admin): COD and own_rider
    payment_filter = and_(
        func.lower(func.coalesce(Order.payment_method, "cod")).in_(["cod", "cash"]),
    )

    query = (
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Dealer, Dealer.id == Product.dealer_id)
        .where(and_(base_conditions, payment_filter))
    )

    if dealer_id:
        query = query.where(Dealer.id == dealer_id)

    result = await db.execute(query)
    items = result.scalars().all()

    enriched = []
    for item in items:
        prod = await db.get(Product, item.product_id)
        order = await db.get(Order, item.order_id)
        dealer = await db.get(Dealer, prod.dealer_id) if prod else None

        payment_str = str(order.payment_method or "").lower() if order else ""
        is_cod_logistics = payment_str in ("cod", "cash") and bool(item.logistics_partner_id)
        is_own_rider_cod = payment_str in ("cod", "cash") and (
            item.delivery_type == "own_rider" or
            (item.logistics_partner_id is None and item.hub_id is None)
        )

        platform_fee = float(item.platform_fee or 0.0)
        total_value = round(float(item.price or 0.0) * int(item.quantity or 1), 2)
        
        if is_own_rider_cod:
            remittance_type = "collection"
            net_dealer_amount = -platform_fee # Dealer owes the fee
        else:
            remittance_type = "payout"
            net_dealer_amount = round(total_value - platform_fee, 2)

        enriched.append({
            "id": item.id,
            "order_number": (order.order_number if order else None) or f"ORD-{item.order_id}",
            "product_name": prod.name if prod else "Unknown",
            "quantity": int(item.quantity or 1),
            "price": float(item.price or 0.0),
            "total_value": total_value,
            "tax_amount": float(item.tax_amount or 0.0),
            "platform_fee": platform_fee,
            "net_dealer_amount": net_dealer_amount,
            "remittance_type": remittance_type,
            "delivered_at": item.delivered_at.isoformat() if item.delivered_at else None,
            "dealer_name": dealer.business_name if dealer else "N/A",
            "dealer_id": dealer.id if dealer else None,
            "payment_method": order.payment_method if order else None,
            "is_cod_logistics": is_cod_logistics,
            "logistics_partner_id": item.logistics_partner_id,
        })

    return enriched




@router.post("/admin/finance/dealer-remittances", response_model=DealerRemittanceOut, status_code=status.HTTP_201_CREATED)
async def create_dealer_remittance(
    data: DealerRemittanceCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """Record a new remittance to a dealer and link it to order items"""
    # 1. Create the remittance record
    remittance = DealerRemittance(
        dealer_id=data.dealer_id,
        amount=data.amount,
        reference_no=data.reference_no,
        payment_method=data.payment_method,
        payment_date=data.payment_date,
        notes=data.notes,
        type=data.type,
        status="completed", # Admin making the record usually means money is sent
        confirmed_by_admin_id=admin.id,
        confirmed_at=datetime.now()
    )
    db.add(remittance)
    await db.flush() # Get ID
    
    # 2. Link order items
    if data.order_item_ids:
        stmt = (
            update(OrderItem)
            .where(
                and_(
                    OrderItem.id.in_(data.order_item_ids),
                    OrderItem.dealer_remittance_id.is_(None)
                )
            )
            .values(dealer_remittance_id=remittance.id)
        )
        await db.execute(stmt)
        
    await db.commit()
    await db.refresh(remittance)
    
    # Enrich with order numbers for response
    items_res = await db.execute(
        select(Order.order_number)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(OrderItem.dealer_remittance_id == remittance.id)
        .distinct()
    )
    remittance.order_numbers = items_res.scalars().all()
    
    return remittance

@router.get("/admin/finance/dealer-remittances", response_model=List[DealerRemittanceOut])
async def list_all_remittances(
    dealer_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """List all remittances recorded by the platform"""
    query = select(DealerRemittance).order_by(DealerRemittance.created_at.desc())
    if dealer_id:
        query = query.where(DealerRemittance.dealer_id == dealer_id)
        
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    remittances = result.scalars().all()
    
    for r in remittances:
        items_res = await db.execute(
            select(Order.order_number)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.dealer_remittance_id == r.id)
            .distinct()
        )
        r.order_numbers = items_res.scalars().all()
        
    return remittances

@router.get("/finance/dealer/remittances", response_model=List[DealerRemittanceOut])
async def get_dealer_remittance_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Returns remittance history for the logged-in dealer"""
    # Get dealer profile
    from .dealers import get_current_dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
         raise HTTPException(status_code=404, detail="Dealer profile not found")
         
    query = (
        select(DealerRemittance)
        .where(DealerRemittance.dealer_id == dealer.id)
        .order_by(DealerRemittance.created_at.desc())
    )
    result = await db.execute(query)
    remittances = result.scalars().all()
    
    for r in remittances:
        items_res = await db.execute(
            select(Order.order_number)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(OrderItem.dealer_remittance_id == r.id)
            .distinct()
        )
        r.order_numbers = items_res.scalars().all()
        
    return remittances

@router.post("/finance/dealer/remittances", response_model=DealerRemittanceOut, status_code=status.HTTP_201_CREATED)
async def submit_dealer_remittance(
    data: DealerRemittanceSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Allows a dealer to submit a remittance (payment to admin) for verification"""
    from .dealers import get_current_dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
         raise HTTPException(status_code=404, detail="Dealer profile not found")

    # 1. Create the remittance record with 'pending' status
    remittance = DealerRemittance(
        dealer_id=dealer.id,
        amount=data.amount,
        reference_no=data.reference_no,
        payment_method=data.payment_method,
        payment_date=data.payment_date,
        notes=data.notes,
        type=data.type,
        status="pending", # Dealer marks as pending; Admin will confirm
    )
    db.add(remittance)
    await db.flush() # Get ID
    
    # 2. Link order items
    if data.order_item_ids:
        # Verify these items belong to the dealer and are not already remitted
        stmt = (
            update(OrderItem)
            .where(
                and_(
                    OrderItem.id.in_(data.order_item_ids),
                    OrderItem.dealer_remittance_id.is_(None)
                )
            )
            .values(dealer_remittance_id=remittance.id)
        )
        await db.execute(stmt)
        
    await db.commit()
    await db.refresh(remittance)
    
    # Enrich with order numbers
    items_res = await db.execute(
        select(Order.order_number)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(OrderItem.dealer_remittance_id == remittance.id)
        .distinct()
    )
    remittance.order_numbers = items_res.scalars().all()
    
    return remittance

@router.get("/finance/dealer/tax-reports")
async def get_dealer_tax_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Returns actual GST liability and TDS data for the logged-in dealer, grouped by periods.
    """
    from .dealers import get_current_dealer
    dealer = await get_current_dealer(current_user, db)
    if not dealer:
        raise HTTPException(status_code=404, detail="Dealer profile not found")

    # Fetch all delivered order items for this dealer
    query = (
        select(OrderItem, Order, Product)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer.id,
                func.lower(OrderItem.status).in_(["processing", "shipped", "delivered", "completed"])
            )
        )
    )
    result = await db.execute(query)
    rows = result.all()

    gst_dict = {}
    tds_dict = {}

    import math
    from datetime import datetime
    
    for item, order, product in rows:
        dt = order.created_at
        if not dt: continue
        
        # GST grouping (Monthly)
        month_key = dt.strftime("%B %Y")
        
        # TDS grouping (Quarterly - Financial Year starts April)
        fy_year = dt.year if dt.month > 3 else dt.year - 1
        q_map = {4:1, 5:1, 6:1, 7:2, 8:2, 9:2, 10:3, 11:3, 12:3, 1:4, 2:4, 3:4}
        quarter_num = q_map[dt.month]
        quarter = f"Q{quarter_num} {fy_year}-{str(fy_year+1)[2:]}"

        gross_value = float(item.price or 0) * int(item.quantity or 1)
        tax_amount = float(item.tax_amount or 0) * int(item.quantity or 1)
        
        # GST calculation
        if month_key not in gst_dict:
            gst_dict[month_key] = {
                "total_gross": 0.0, 
                "total_tax": 0.0, 
                "total_cgst": 0.0,
                "total_sgst": 0.0,
                "total_igst": 0.0,
                "date": dt, 
                "orders": []
            }
        
        if getattr(order, 'is_inter_state', False) or getattr(order, 'igst_amount', 0) > 0:
            igst_amount = tax_amount
            cgst_amount = 0.0
            sgst_amount = 0.0
        else:
            igst_amount = 0.0
            cgst_amount = tax_amount / 2
            sgst_amount = tax_amount / 2

        gst_dict[month_key]["total_gross"] += gross_value
        gst_dict[month_key]["total_tax"] += tax_amount
        gst_dict[month_key]["total_cgst"] += cgst_amount
        gst_dict[month_key]["total_sgst"] += sgst_amount
        gst_dict[month_key]["total_igst"] += igst_amount
        gst_dict[month_key]["orders"].append({
            "order_number": order.order_number or f"ORD-{order.id}",
            "product_name": product.name,
            "quantity": int(item.quantity or 1),
            "hsn_code": str(product.hsn_code or ""),
            "gst_rate": float(getattr(item, 'igst_rate', 0) or 0.0),
            "gross_value": round(gross_value, 2),
            "tax_amount": round(tax_amount, 2),
            "cgst_amount": round(cgst_amount, 2),
            "sgst_amount": round(sgst_amount, 2),
            "igst_amount": round(igst_amount, 2),
            "date": dt.isoformat()
        })

        # TDS/TCS calculation (1% TDS on gross, 1% TCS on taxable)
        taxable_value = gross_value - tax_amount
        tds_amount = gross_value * 0.01
        tcs_amount = taxable_value * 0.01
        
        if quarter not in tds_dict:
            tds_dict[quarter] = {
                "tds": 0.0,
                "tcs": 0.0,
                "date": dt,
                "orders": [],
                "gross_sales": 0.0,
                "taxable_value": 0.0
            }
            
        tds_dict[quarter]["tds"] += tds_amount
        tds_dict[quarter]["tcs"] += tcs_amount
        tds_dict[quarter]["gross_sales"] += gross_value
        tds_dict[quarter]["taxable_value"] += taxable_value
        
        tds_dict[quarter]["orders"].append({
            "order_number": order.order_number or f"ORD-{order.id}",
            "product_name": product.name,
            "quantity": int(item.quantity or 1),
            "gross_value": round(gross_value, 2),
            "taxable_value": round(taxable_value, 2),
            "tds_amount": round(tds_amount, 2),
            "tcs_amount": round(tcs_amount, 2),
            "date": dt.isoformat()
        })

    # Format output
    gst_reports = []
    
    for k, v in sorted(gst_dict.items(), key=lambda x: x[1]['date'], reverse=True):
        gst_reports.append({
            "id": f"gst-{k.replace(' ', '-')}",
            "month": k,
            "type": "GSTR-1 (Sales)",
            "status": "Generated",
            "amount": round(float(v["total_tax"]), 2),
            "total_cgst": round(float(v["total_cgst"]), 2),
            "total_sgst": round(float(v["total_sgst"]), 2),
            "total_igst": round(float(v["total_igst"]), 2),
            "date": str(v["date"]),
            "gross_sales": round(float(v["total_gross"]), 2),
            "orders": v["orders"]
        })

    tds_reports = []
    for k, v in sorted(tds_dict.items(), key=lambda x: x[1]['date'], reverse=True):
        tds_reports.append({
            "id": f"tds-{k.replace(' ', '-')}",
            "period": k,
            "type": "TDS Certificate (Form 16A)",
            "status": "Ready to Download",
            "amount": round(float(v["tds"]), 2),
            "tcs_amount": round(float(v["tcs"]), 2),
            "gross_sales": round(float(v["gross_sales"]), 2),
            "taxable_value": round(float(v["taxable_value"]), 2),
            "orders": v["orders"]
        })
        tds_reports.append({
            "id": f"tcs-{k.replace(' ', '-')}",
            "period": k,
            "type": "TCS Certificate (Form 27D)",
            "status": "Ready to Download",
            "amount": round(float(v["tcs"]), 2),
            "tds_amount": round(float(v["tds"]), 2),
            "gross_sales": round(float(v["gross_sales"]), 2),
            "taxable_value": round(float(v["taxable_value"]), 2),
            "orders": v["orders"]
        })

    return {
        "gst_reports": gst_reports,
        "tds_reports": tds_reports,
        "total_gst_lifetime": round(float(sum(v["total_tax"] for v in gst_dict.values())), 2),
        "total_tds_lifetime": round(float(sum(v["tds"] for v in tds_dict.values())), 2),
        "total_tcs_lifetime": round(float(sum(v["tcs"] for v in tds_dict.values())), 2)
    }

@router.get("/admin/finance/reports/remittances/export")
async def export_remittances(
    format: str = Query("csv"),
    dealer_id: Optional[int] = None,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export remittance history with token-in-query support for direct downloads"""
    # Manual token validation if no admin dependency passed
    from jose import jwt
    from core.config import settings
    from models.user import UserRole
    from datetime import datetime
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        if not email: raise HTTPException(status_code=401)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")

    is_admin = user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    
    if not is_admin:
        from .dealers import get_current_dealer
        dealer = await get_current_dealer(user, db)
        if not dealer:
            raise HTTPException(status_code=403, detail="Dealer profile required for export")
        # Securely lock export to this dealer only
        dealer_id = dealer.id

    query = (
        select(DealerRemittance, Dealer)
        .join(Dealer, Dealer.id == DealerRemittance.dealer_id)
        .order_by(DealerRemittance.created_at.desc())
    )
    if dealer_id:
        query = query.where(DealerRemittance.dealer_id == dealer_id)
        
    if date_from:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        query = query.where(DealerRemittance.created_at >= start_date)
    if date_to:
        end_date = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        query = query.where(DealerRemittance.created_at <= end_date)
    
    result = await db.execute(query)
    rows = result.all()

    filename_base = f"remittance_report_{datetime.now().strftime('%Y%m%d_%H%M')}"
    headers_row = ["ID", "Date", "Dealer", "Amount", "Method", "Reference", "Status", "Notes"]
    
    data_rows = []
    for r, dealer in rows:
        data_rows.append([
            str(r.id),
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
            str(dealer.business_name if dealer else r.dealer_id),
            str(r.amount),
            str(r.payment_method),
            str(r.reference_no or ""),
            str(r.status),
            str(r.notes or "")
        ])

    if format == "xlsx":
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Remittances"
            ws.append(headers_row)
            for row in data_rows:
                ws.append(row)
            
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
            )
        except ImportError:
            # Fallback to CSV if openpyxl not installed
            format = "csv"

    if format == "pdf":
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
            
            output = io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=landscape(letter))
            elements = []
            
            styles = getSampleStyleSheet()
            elements.append(Paragraph("Dealer Remittance Report", styles['Title']))
            
            table_data = [headers_row] + data_rows
            t = Table(table_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            elements.append(t)
            doc.build(elements)
            
            output.seek(0)
            return StreamingResponse(
                output,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
            )
        except ImportError:
            # Fallback to CSV if reportlab not installed
            format = "csv"

    # Default/Fallback: CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers_row)
    for row in data_rows:
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
    )

@router.get("/finance/dealer/tax-reports/export")
async def export_dealer_tax_reports(
    format: str = Query("csv"),
    month_key: Optional[str] = Query(None),
    quarter_key: Optional[str] = Query(None),
    year_key: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Export dealer GST sales report with token-in-query support for direct downloads"""
    from jose import jwt
    from core.config import settings
    from datetime import datetime
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        email: str = payload.get("sub")
        if not email: raise HTTPException(status_code=401)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")

    from .dealers import get_current_dealer
    dealer = await get_current_dealer(user, db)
    if not dealer:
        raise HTTPException(status_code=403, detail="Dealer profile required for export")

    query = (
        select(OrderItem, Order, Product)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(
            and_(
                Product.dealer_id == dealer.id,
                func.lower(OrderItem.status).in_(["processing", "shipped", "delivered", "completed"])
            )
        )
    )
    result = await db.execute(query)
    rows = result.all()

    filename_base = f"gst_export_{dealer.business_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"
    headers_row = ["Date", "Order Number", "Product", "Qty", "Gross Value", "Taxable Value", "CGST", "SGST", "IGST", "Total GST"]
    
    data_rows = []
    total_gross = 0
    total_taxable = 0
    total_cgst = 0
    total_sgst = 0
    total_igst = 0
    total_tax = 0

    for item, order, product in rows:
        dt = order.created_at
        if not dt: continue
        
        # Evaluate matching period logic
        m_key = dt.strftime("%B %Y")
        fy_year = dt.year if dt.month > 3 else dt.year - 1
        q_map = {4:1, 5:1, 6:1, 7:2, 8:2, 9:2, 10:3, 11:3, 12:3, 1:4, 2:4, 3:4}
        q_key = f"Q{q_map[dt.month]} {fy_year}-{str(fy_year+1)[2:]}"
        y_key = f"FY {fy_year}-{str(fy_year+1)[2:]}"
        
        if month_key and m_key != month_key:
            continue
        if quarter_key and q_key != quarter_key:
            continue
        if year_key and y_key != year_key:
            continue
            
        gross_value = float(item.price or 0) * int(item.quantity or 1)
        tax_amount = float(item.tax_amount or 0) * int(item.quantity or 1)
        taxable_value = gross_value - tax_amount
        if getattr(order, 'is_inter_state', False) or getattr(order, 'igst_amount', 0) > 0:
            igst_amount = tax_amount
            cgst_amount = 0.0
            sgst_amount = 0.0
        else:
            igst_amount = 0.0
            cgst_amount = tax_amount / 2
            sgst_amount = tax_amount / 2

        total_gross += gross_value
        total_taxable += taxable_value
        total_cgst += cgst_amount
        total_sgst += sgst_amount
        total_igst += igst_amount
        total_tax += tax_amount

        data_rows.append([
            dt.strftime("%Y-%m-%d"),
            str(order.order_number or f"ORD-{order.id}"),
            str(product.name),
            str(int(item.quantity or 1)),
            f"{round(gross_value, 2)}",
            f"{round(taxable_value, 2)}",
            f"{round(cgst_amount, 2)}",
            f"{round(sgst_amount, 2)}",
            f"{round(igst_amount, 2)}",
            f"{round(tax_amount, 2)}"
        ])

    data_rows.append([])
    data_rows.append([
        "TOTAL", "", "", "", 
        f"{round(total_gross, 2)}", 
        f"{round(total_taxable, 2)}", 
        f"{round(total_cgst, 2)}", 
        f"{round(total_sgst, 2)}", 
        f"{round(total_igst, 2)}", 
        f"{round(total_tax, 2)}"
    ])

    if format == "xlsx":
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "GST Export"
            ws.append(headers_row)
            for row in data_rows:
                ws.append(row)
            
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)
            
            return StreamingResponse(
                output,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
            )
        except ImportError:
            format = "csv"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers_row)
    for row in data_rows:
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
    )
