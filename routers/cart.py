from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload, joinedload
from typing import List

from core.database import get_db
from core.permissions import get_current_active_user
from schemas.cart import CartItem, CartItemCreate, CartItemUpdate, Order
from models.cart import CartItem as CartItemModel, Order as OrderModel, OrderItem as OrderItemModel, OrderStatus
from models.product import Product as ProductModel, Category as CategoryModel
from models.product_variant import ProductVariant as ProductVariantModel
from models.dealer import Dealer as DealerModel
from models.user import User
from models.customer_user import CustomerUser
from models.coupon import Coupon as CouponModel, CouponUsage as CouponUsageModel
from models.order_return import OrderReturn as OrderReturnModel
from services.notification import EmailService
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional
import secrets
import string
from services.tax_service import TaxService
from models.tax import TaxLedger

def generate_order_number():
    """Generate a unique 10-digit numeric string."""
    return ''.join(secrets.choice(string.digits) for _ in range(10))

class OrderRequest(BaseModel):
    coupon_code: Optional[str] = None
    payment_method: str = "COD"
    address_id: Optional[int] = None

router = APIRouter()

# Cart endpoints
@router.post("/cart", response_model=CartItem, tags=["cart"])
async def add_to_cart(
    item_in: CartItemCreate, 
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Add item to cart or update quantity if already exists"""
    from sqlalchemy import insert as sql_insert
    customer_id = int(current_user.id)
    product_id = int(item_in.product_id)
    variant_id = item_in.variant_id
    quantity = int(item_in.quantity)

    # Check if item with SAME product AND same size AND same variant already in cart
    result = await db.execute(
        select(CartItemModel.id, CartItemModel.quantity)
        .where(
            CartItemModel.customer_id == customer_id, 
            CartItemModel.product_id == product_id,
            CartItemModel.variant_id == variant_id,
            CartItemModel.size == item_in.size
        )
    )
    existing = result.first()

    if existing:
        # Update quantity
        await db.execute(
            update(CartItemModel)
            .where(CartItemModel.id == existing.id)
            .values(quantity=existing.quantity + quantity)
            .execution_options(synchronize_session=False)
        )
    else:
        await db.execute(
            sql_insert(CartItemModel).values(
                customer_id=customer_id,
                product_id=product_id,
                variant_id=variant_id,
                quantity=quantity,
                size=item_in.size
            )
        )

    await db.commit()

    # Re-fetch with eager loading — MUST match size as well to stay unique
    res = await db.execute(
        select(CartItemModel)
        .where(
            CartItemModel.customer_id == customer_id, 
            CartItemModel.product_id == product_id,
            CartItemModel.variant_id == variant_id,
            CartItemModel.size == item_in.size
        )
        .options(
            joinedload(CartItemModel.product).options(
                joinedload(ProductModel.dealer),
                joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.variants)
            )
        )


    )
    # Use first() instead of scalar_one() to be safer during high-concurrency duplicates
    cart_item = res.scalar_one_or_none()
    if not cart_item:
        # Fallback if somehow missing
        res = await db.execute(
            select(CartItemModel)
            .where(CartItemModel.customer_id == customer_id, CartItemModel.product_id == product_id)
            .options(
                joinedload(CartItemModel.product).options(
                    joinedload(ProductModel.dealer),
                    joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
                    selectinload(ProductModel.variants)
                )
            )

            .limit(1)
        )
        cart_item = res.scalar_one()

    return cart_item

@router.get("/cart", response_model=List[CartItem], tags=["cart"])
async def get_cart(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all items in the cart"""
    result = await db.execute(
        select(CartItemModel)
        .where(CartItemModel.customer_id == current_user.id)
        .options(
            joinedload(CartItemModel.product).options(
                joinedload(ProductModel.dealer),
                joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.variants)
            )
        )


    )
    items = result.scalars().all()
    return items

@router.patch("/cart/{item_id}", response_model=CartItem, tags=["cart"])
async def update_cart_item(
    item_id: int,
    update_in: CartItemUpdate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update cart item quantity"""
    # Verify ownership with a lightweight query
    result = await db.execute(
        select(CartItemModel.id)
        .where(CartItemModel.id == item_id, CartItemModel.customer_id == current_user.id)
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Cart item not found")
    if update_in.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

    # Update using SQL — no ORM attribute access after commit
    await db.execute(
        update(CartItemModel)
        .where(CartItemModel.id == item_id)
        .values(quantity=update_in.quantity)
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    res = await db.execute(
        select(CartItemModel)
        .where(CartItemModel.id == item_id)
        .options(
            joinedload(CartItemModel.product).options(
                joinedload(ProductModel.dealer),
                joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.variants)
            )
        )


    )
    return res.scalar_one()

@router.delete("/cart/{item_id}", tags=["cart"])
async def remove_from_cart(
    item_id: int, 
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove item from cart"""
    result = await db.execute(
        delete(CartItemModel).where(
            CartItemModel.id == item_id,
            CartItemModel.customer_id == current_user.id
        )
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    return {"message": "Item removed from cart"}

# Order endpoints
@router.post("/orders", response_model=List[Order], tags=["orders"])
async def create_order(
    background_tasks: BackgroundTasks,
    order_request: OrderRequest = None,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create order from cart items (checkout)"""
    # Capture user attrs NOW before any db writes expire the ORM object
    customer_id = int(current_user.id)
    user_email = str(current_user.email)

    result = await db.execute(
        select(CartItemModel)
        .join(ProductModel, CartItemModel.product_id == ProductModel.id)
        .join(DealerModel, ProductModel.dealer_id == DealerModel.id)
        .where(
            CartItemModel.customer_id == customer_id,
            DealerModel.access_status == 'active',
            DealerModel.is_active == True,
            ProductModel.is_approved == True
        )
        .options(
            joinedload(CartItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.variants)
            )
        )



    )
    cart_items = result.scalars().all()
    
    # Check if some items were filtered out due to dealer status
    from sqlalchemy import func
    all_cart_res = await db.execute(select(func.count(CartItemModel.id)).where(CartItemModel.customer_id == customer_id))
    if cart_items and len(cart_items) < all_cart_res.scalar():
         raise HTTPException(
             status_code=400, 
             detail="Some items in your cart are no longer available as the seller is currently inactive. Please update your cart."
         )
    
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    total_amount = 0.0
    total_delivery_charge = 0.0
    order_items_data = []
    stock_updates = []  # (product_id, deduct_qty)
    dealer_subtotals: dict[int, float] = {}  # dealer_id -> subtotal of their items

    for cart_item in cart_items:
        product = cart_item.product

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {cart_item.product_id} not found")

        # Check stock - if variant is selected, check variant stock
        if cart_item.variant_id:
            variant = next((v for v in (product.variants or []) if v.id == cart_item.variant_id), None)
            if not variant:
                # If variant not loaded, fetch it
                res = await db.execute(select(ProductVariantModel).where(ProductVariantModel.id == cart_item.variant_id))
                variant = res.scalar_one_or_none()
            
            if not variant:
                 raise HTTPException(status_code=404, detail=f"Variant {cart_item.variant_id} not found")
            
            if variant.stock < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name} (Size: {variant.size})")
        else:
            # Check main stock for simple product
            if product.stock < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name}")

        price = float(product.discount_price if product.discount_price else product.price)
        line_total = price * cart_item.quantity
        total_amount += line_total

        # Track per-dealer subtotal for delivery fee calc
        d_id = int(product.dealer_id) if product.dealer_id else 0
        dealer_subtotals[d_id] = dealer_subtotals.get(d_id, 0.0) + line_total

        # --- FINANCIAL SPLITS (Tax & Platform Commission) ---
        # 1. Tax Calculation (from inclusive price)
        buyer_state = "UNKNOWN" # To be derived from address if provided, ignoring for MVP
        seller_state = product.dealer.state if product.dealer else "UNKNOWN"
        
        tax_res = await TaxService.calculate_item_tax(
            db=db,
            inclusive_price=price,
            qty=cart_item.quantity,
            product_id=product.id,
            buyer_state=buyer_state,
            seller_state=seller_state
        )
        
        # 2. Platform Commission Calculation (EXTRACTED from the bundled price)
        # Using Hidden Markup Strategy: Platform Fee is added on top of (Base + Tax).
        # To extract: Fee = Total * (Fee% / (100 + Fee%))
        fee_percent = product.dealer.platform_fee_percent if product.dealer else 5.0
        # If the platform collects the fee from the customer (hidden as markup),
        # we extract it from the inclusive price.
        platform_fee = line_total * (fee_percent / (100.0 + fee_percent))

        order_items_data.append({
            "product_id": int(cart_item.product_id),
            "variant_id": cart_item.variant_id,
            "quantity": int(cart_item.quantity),
            "price": price,
            "size": cart_item.size,
            "dealer_id": d_id,
            # Tax and fee data
            "tax_data": tax_res,
            "platform_fee": platform_fee
        })
        # For stock updates, we'll handle variant stock deduction too
        stock_updates.append({
            "product_id": int(product.id),
            "variant_id": cart_item.variant_id,
            "quantity": int(cart_item.quantity)
        })

    # ── Delivery Charge Breakdown ──────────────────────────────────────────────
    # Map dealer_id -> (fee, threshold, dealer_items_total)
    dealer_fees_map: dict[int, dict] = {}
    if dealer_subtotals:
        dealers_res = await db.execute(
            select(
                DealerModel.id,
                DealerModel.delivery_charge,
                DealerModel.free_delivery_above
            ).where(DealerModel.id.in_(list(dealer_subtotals.keys())))
        )
        for row in dealers_res.fetchall():
            dealer_items_total = dealer_subtotals.get(row.id, 0.0)
            fee = float(row.delivery_charge or 0.0)
            threshold = float(row.free_delivery_above or 0.0)
            is_waived = (fee == 0 or (threshold > 0 and dealer_items_total >= threshold))
            
            dealer_fees_map[row.id] = {
                "fee": 0.0 if is_waived else fee,
                "total_dealer_subtotal": dealer_items_total
            }
            if not is_waived:
                total_delivery_charge += fee
    
    # Deduct stock
    for update_data in stock_updates:
        p_id = update_data["product_id"]
        v_id = update_data["variant_id"]
        qty = update_data["quantity"]
        
        # Deduct from main product
        await db.execute(
            update(ProductModel)
            .where(ProductModel.id == p_id)
            .values(stock=ProductModel.stock - qty)
            .execution_options(synchronize_session=False)
        )
        
        # If variant, deduct from variant too
        if v_id:
            await db.execute(
                update(ProductVariantModel)
                .where(ProductVariantModel.id == v_id)
                .values(stock=ProductVariantModel.stock - qty)
                .execution_options(synchronize_session=False)
            )
    
    # ── Coupon Validation (Global) ─────────────────────────────────────────────
    coupon_code_str = order_request.coupon_code.strip().upper() if (order_request and order_request.coupon_code) else None
    applied_coupon = None
    total_discount_amount = 0.0

    if coupon_code_str:
        coupon_res = await db.execute(
            select(CouponModel).where(CouponModel.code == coupon_code_str)
        )
        coupon_obj = coupon_res.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if not coupon_obj or not coupon_obj.is_active:
            raise HTTPException(status_code=400, detail="Invalid or inactive coupon code")
        if now < coupon_obj.valid_from or now > coupon_obj.valid_until:
            raise HTTPException(status_code=400, detail="Coupon is expired or not yet valid")
        if coupon_obj.usage_limit and coupon_obj.current_usage >= coupon_obj.usage_limit:
            raise HTTPException(status_code=400, detail="Coupon usage limit reached")
        if total_amount < coupon_obj.min_order_value:
            raise HTTPException(status_code=400, detail=f"Minimum order value ₹{coupon_obj.min_order_value} required for this coupon")

        if coupon_obj.dealer_id:
            cart_product_ids = [item_data["product_id"] for item_data in order_items_data]
            dealer_check = await db.execute(
                select(ProductModel.id).where(
                    ProductModel.id.in_(cart_product_ids),
                    ProductModel.dealer_id == coupon_obj.dealer_id
                )
            )
            if not dealer_check.first():
                raise HTTPException(status_code=400, detail="Coupon is not valid for items in your cart")

        from models.coupon import DiscountType
        if coupon_obj.discount_type == DiscountType.PERCENTAGE:
            total_discount_amount = total_amount * (coupon_obj.discount_value / 100)
            if coupon_obj.max_discount_amount:
                total_discount_amount = min(total_discount_amount, coupon_obj.max_discount_amount)
        elif coupon_obj.discount_type == DiscountType.FIXED:
            total_discount_amount = min(coupon_obj.discount_value, total_amount)

        applied_coupon = coupon_obj

    # If coupon applied: increment usage
    if applied_coupon:
        await db.execute(
            update(CouponModel)
            .where(CouponModel.id == applied_coupon.id)
            .values(current_usage=CouponModel.current_usage + 1)
            .execution_options(synchronize_session=False)
        )

    # ── Create Separate Orders Per Item ────────────────────────────────────────
    from sqlalchemy import insert as sql_insert
    created_order_ids = []
    
    for item_data in order_items_data:
        item_subtotal = item_data["price"] * item_data["quantity"]
        
        # Pro-rata discount
        item_discount = 0.0
        if total_amount > 0:
            item_discount = (item_subtotal / total_amount) * total_discount_amount
            
        # Pro-rata delivery charge (for same dealer grouping)
        item_delivery = 0.0
        dealer_info = dealer_fees_map.get(item_data["dealer_id"], {"fee": 0.0, "total_dealer_subtotal": 0.0})
        if dealer_info["total_dealer_subtotal"] > 0:
            item_delivery = (item_subtotal / dealer_info["total_dealer_subtotal"]) * dealer_info["fee"]
            
        final_item_total = max(0.0, item_subtotal - item_discount) + item_delivery
        
        tax_data = item_data["tax_data"]
        
        order_result = await db.execute(
            sql_insert(OrderModel).values(
                customer_id=customer_id,
                subtotal=item_subtotal,
                order_number=generate_order_number(),
                discount_amount=item_discount,
                delivery_charge=item_delivery,
                total_amount=final_item_total,
                status=OrderStatus.ORDER_PLACED.value,
                coupon_id=applied_coupon.id if applied_coupon else None,
                coupon_code=applied_coupon.code if applied_coupon else None,
                payment_method=order_request.payment_method if order_request else "COD",
                shipping_address_id=order_request.address_id if order_request else None,
                # Tax Fields
                tax_amount=tax_data["total_tax"],
                cgst_amount=tax_data["cgst_amount"],
                sgst_amount=tax_data["sgst_amount"],
                igst_amount=tax_data["igst_amount"],
                is_inter_state=tax_data["is_inter_state"],
                tax_invoice_no=await TaxService.generate_tax_invoice_number(db),
                # Platform Revenue
                platform_fee_amount=item_data["platform_fee"]
            ).returning(OrderModel.id)
        )
        new_order_id = order_result.scalar_one()
        created_order_ids.append(new_order_id)
        
        # Insert matching OrderItem
        item_result = await db.execute(
            sql_insert(OrderItemModel).values(
                order_id=new_order_id,
                product_id=item_data["product_id"],
                variant_id=item_data.get("variant_id"),
                quantity=item_data["quantity"],
                price=item_data["price"],
                size=item_data.get("size"),
                status="order_placed",
                # Tax Fields
                tax_amount=tax_data["total_tax"],
                cgst_rate=tax_data["cgst_rate"],
                sgst_rate=tax_data["sgst_rate"],
                igst_rate=tax_data["igst_rate"],
                platform_fee=item_data["platform_fee"]
            ).returning(OrderItemModel.id)
        )
        new_item_id = item_result.scalar_one()
        
        # Insert into Tax Ledger for audit trail
        if tax_data["tax_category_id"]:
            await db.execute(
                sql_insert(TaxLedger).values(
                    order_id=new_order_id,
                    order_item_id=new_item_id,
                    tax_category_id=tax_data["tax_category_id"],
                    taxable_amount=tax_data["taxable_amount"],
                    cgst_amount=tax_data["cgst_amount"],
                    sgst_amount=tax_data["sgst_amount"],
                    igst_amount=tax_data["igst_amount"],
                    total_tax=tax_data["total_tax"]
                )
            )

    # Clear cart
    await db.execute(
        delete(CartItemModel).where(CartItemModel.customer_id == customer_id)
    )
    
    await db.commit()
    
    # Send confirmation for each (or just once)
    background_tasks.add_task(
        EmailService.send_order_confirmation,
        to_email=user_email,
        order_data={"ids": created_order_ids, "total": total_amount}
    )

    # SEND IN-APP NOTIFICATION
    try:
        from services.notification import AppNotificationService
        from models import NotificationType
        for order_id in created_order_ids:
             await AppNotificationService.create_notification(
                 db,
                 customer_id=customer_id,
                 type=NotificationType.ORDER_PLACED,
                 title="Order Placed!",
                 message=f"Your order ID {order_id} has been placed successfully. Thank you for shopping!"
             )
        await db.commit()
    except Exception as e:
        print(f"Error sending in-app notification: {e}")
    
    # Re-fetch all created orders with eager loading
    res = await db.execute(
        select(OrderModel)
        .where(OrderModel.id.in_(created_order_ids))
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.variants)
            ),

            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns)
        )
        .order_by(OrderModel.created_at.desc())
    )
    return res.scalars().all()

@router.get("/orders", response_model=list, tags=["orders"])
async def get_orders(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders for the current user, newest first"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.customer_id == current_user.id)
        .options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.variants),
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.dealer),
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
            selectinload(OrderModel.items).selectinload(OrderItemModel.hub),
            selectinload(OrderModel.returns).selectinload(OrderReturnModel.exchange_variant),
            selectinload(OrderModel.shipping_address),
            selectinload(OrderModel.payment)
        )
        .order_by(OrderModel.created_at.desc())
    )
    orders = result.scalars().all()
    
    from schemas.cart import Order as OrderSchema
    
    response_list = []
    for o in orders:
        if hasattr(OrderSchema, 'model_validate'):
            o_dict = OrderSchema.model_validate(o).model_dump()
        else:
            o_dict = OrderSchema.from_orm(o).dict()
            
        addr_str = "Home Address"
        if o.shipping_address:
            addr = o.shipping_address
            street = getattr(addr, 'address_line1', getattr(addr, 'street_address', ''))
            city = getattr(addr, 'city', '')
            state = getattr(addr, 'state', '')
            zip_code = getattr(addr, 'pincode', getattr(addr, 'postal_code', ''))
            parts = [p for p in [street, city, state, zip_code] if p]
            if parts:
                addr_str = ", ".join(parts[:3]) + (f" - {zip_code}" if zip_code else "")
        
        o_dict["shipping_address"] = addr_str
        response_list.append(o_dict)
    
    return response_list
