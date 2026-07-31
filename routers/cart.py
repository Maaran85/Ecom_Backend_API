import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from sqlalchemy.orm import selectinload, joinedload
from typing import List

from core.database import get_db

gst_logger = logging.getLogger("gst")
from core.permissions import get_current_active_user
from schemas.cart import CartItem, CartItemCreate, CartItemUpdate, Order
from models.cart import CartItem as CartItemModel, Order as OrderModel, OrderItem as OrderItemModel, OrderStatus
from models.product import Product as ProductModel, Category as CategoryModel
from models.dealer import Dealer as DealerModel
from models.user import User
from models.customer_user import CustomerUser
from models.coupon import Coupon as CouponModel, CouponUsage as CouponUsageModel
from models.order_return import OrderReturn as OrderReturnModel
from models.invoice import OrderInvoice as OrderInvoiceModel
from models.address import Address as AddressModel
from fastapi.responses import StreamingResponse


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
    billing_address_id: Optional[int] = None
    use_wallet: Optional[bool] = False
    wallet_amount: Optional[float] = None

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
    product_id = item_in.product_id
    variant_id = item_in.variant_id
    quantity = int(item_in.quantity)
    
    print(f"[DEBUG] ADD TO CART: product_id={product_id}, variant_id={variant_id}, quantity={quantity}")
    
    # Verify product exists
    prod_check = await db.execute(
        select(ProductModel.id).where(ProductModel.id == product_id)
    )
    product_exists = prod_check.scalar_one_or_none()
    print(f"[DEBUG] ADD TO CART: Product exists? {product_exists is not None}")
    if product_exists is None:
        print(f"[DEBUG] ADD TO CART: Product ID {product_id} NOT FOUND in products table!")
        from models.product import ProductModel as ProductModelCls
        print(f"[DEBUG] ADD TO CART: Available products (first 5):")
        available_prods = await db.execute(select(ProductModelCls.id, ProductModelCls.name).limit(5))
        for prod_id, prod_name in available_prods.fetchall():
            print(f"[DEBUG] ADD TO CART:   Product ID: {prod_id}, Name: {prod_name}")

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
                size=item_in.size,
                variant_attributes=item_in.variant_attributes
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
                selectinload(ProductModel.children).selectinload(ProductModel.children)
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
                    selectinload(ProductModel.children).selectinload(ProductModel.children)
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
                selectinload(ProductModel.children).selectinload(ProductModel.children)
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
                selectinload(ProductModel.children).selectinload(ProductModel.children)
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
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True
        )
        .options(
            joinedload(CartItemModel.product).options(
                joinedload(ProductModel.dealer).selectinload(DealerModel.state_rel),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
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

    # Fetch buyer state_id from shipping address
    shipping_address_state_id = None
    shipping_address = None
    if order_request and order_request.address_id:
        addr_res = await db.execute(
            select(AddressModel).options(selectinload(AddressModel.state_rel)).where(AddressModel.id == order_request.address_id)
        )
        shipping_addr = addr_res.scalar_one_or_none()
        if shipping_addr and shipping_addr.state_rel:
            shipping_address_state_id = shipping_addr.state_rel.id
            shipping_address = shipping_addr
            
            print(f"\n{'=' * 80}")
            print(f"[GST DEBUG] STAGE 1: GST Checkout Flow - Input Values")
            print(f"{'=' * 80}")
            print(f"[GST DEBUG] STAGE 1: buyer_state_id = {shipping_address_state_id}")
            print(f"[GST DEBUG] STAGE 1: seller_state_id = NULL (will be set from product/dealer)")
            print(f"[GST DEBUG] STAGE 1: dealer.state_id = NULL (will be set from product/dealer)")
            print(f"[GST DEBUG] STAGE 1: shipping_address.state_id = {shipping_address_state_id}")
            print(f"{'=' * 80}\n")
            print(f"[DEBUG] STAGE 1: BEFORE TAX SERVICE CALCULATION")
            print(f"[DEBUG] STAGE 1: buyer_state_id = {shipping_address_state_id}")
            print(f"[DEBUG] STAGE 1: seller_state_id = NULL (will be set per product)")
            print(f"[DEBUG] STAGE 1: shipping_address.state_id = {shipping_address_state_id}")
            print()

    for cart_item in cart_items:
        product = cart_item.product

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {cart_item.product_id} not found")

        # Check stock - if variant is selected, check variant stock
        if cart_item.variant_id:
            variant = next((v for v in (product.children or []) if v.id == cart_item.variant_id), None)
            if not variant:
                # If variant not loaded, fetch it
                res = await db.execute(select(ProductModel).where(ProductModel.id == cart_item.variant_id))
                variant = res.scalar_one_or_none()
            
            if not variant:
                 raise HTTPException(status_code=404, detail=f"Variant {cart_item.variant_id} not found")
            
            if variant.stock < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name} (Size: {variant.sizes[0] if variant.sizes else 'Unknown'})")
        else:
            # Check main stock for simple product
            if product.stock < cart_item.quantity:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name}")

        price = float(product.selling_price if product.selling_price else (product.mrp or product.dealer_price))
        line_total = price * cart_item.quantity
        total_amount += line_total

        # Track per-dealer subtotal for delivery fee calc
        d_id = product.dealer_id
        if d_id:
            dealer_subtotals[d_id] = dealer_subtotals.get(d_id, 0.0) + line_total

        # --- FINANCIAL SPLITS (Tax & Platform Commission) ---
        # 1. Tax Calculation (from inclusive price)
        # Resolve buyer/seller GST state codes (e.g. '33') from the address/dealer.
        buyer_state = shipping_address.state_rel.state_code if (shipping_address and shipping_address.state_rel) else None
        seller_state = product.dealer.state_code if product.dealer else None
        
        print(f"[DEBUG] STAGE 2: BEFORE TaxService.calculate_item_tax()")
        print(f"[DEBUG] STAGE 2: buyer_state = {buyer_state}")
        print(f"[DEBUG] STAGE 2: seller_state = {seller_state}")
        print(f"[DEBUG] STAGE 2: dealer.state_code = {seller_state}")
        print(f"[DEBUG] STAGE 2: shipping_address.state_code = {buyer_state}")
        print()
        
        tax_res = await TaxService.calculate_item_tax(
            db=db,
            base_price=price,
            qty=cart_item.quantity,
            product_id=product.id,
            buyer_state=buyer_state,
            seller_state=seller_state
        )
        
        print(f"[DEBUG] STAGE 2: AFTER TaxService.calculate_item_tax()")
        print(f"[DEBUG] STAGE 2: tax_data = {tax_res}")
        print(f"[DEBUG] STAGE 2: is_inter_state = {tax_res.get('is_inter_state')}")
        print(f"[DEBUG] STAGE 2: cgst_rate = {tax_res.get('cgst_rate')}")
        print(f"[DEBUG] STAGE 2: sgst_rate = {tax_res.get('sgst_rate')}")
        print(f"[DEBUG] STAGE 2: igst_rate = {tax_res.get('igst_rate')}")
        print(f"[DEBUG] STAGE 2: cgst_amount = {tax_res.get('cgst_amount')}")
        print(f"[DEBUG] STAGE 2: sgst_amount = {tax_res.get('sgst_amount')}")
        print(f"[DEBUG] STAGE 2: igst_amount = {tax_res.get('igst_amount')}")
        print()
        
        # 2. Platform Commission Calculation (EXTRACTED from the bundled price)
        # Using Hidden Markup Strategy: Platform Fee is added on top of (Base + Tax).
        # To extract: Fee = Total * (Fee% / (100 + Fee%))
        fee_amount = product.dealer.platform_fee_amount if product.dealer else 5.0
        # Platform fee is a flat amount per unit
        platform_fee = fee_amount * cart_item.quantity

        order_items_data.append({
            "product_id": cart_item.product_id,
            "product_name": product.name,
            "variant_id": cart_item.variant_id,
            "category_id": product.category_id,
            "quantity": int(cart_item.quantity),
            "price": price,
            "size": cart_item.size,
            "variant_attributes": cart_item.variant_attributes,
            "dealer_id": d_id,
            # Tax and fee data
            "tax_data": tax_res,
            "platform_fee": platform_fee,
            "referral_commission_rate": product.referral_commission_rate
        })
        # For stock updates, we'll handle variant stock deduction too
        stock_updates.append({
            "product_id": product.id,
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
        
        target_id = v_id if v_id else p_id
        
        # Deduct from ProductInventory
        from models.inventory import ProductInventory
        # Naive deduction from the hub with the most stock
        inv_result = await db.execute(select(ProductInventory).where(ProductInventory.product_id == target_id).order_by(ProductInventory.stock.desc()))
        inv = inv_result.scalars().first()
        if inv:
            await db.execute(
                update(ProductInventory)
                .where(ProductInventory.id == inv.id)
                .values(stock=ProductInventory.stock - qty)
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

    # ── Wallet Deduction ───────────────────────────────────────────────────────
    total_wallet_discount = 0.0
    if order_request and order_request.use_wallet:
        from models.referral import CustomerWallet
        w_res = await db.execute(select(CustomerWallet).where(CustomerWallet.customer_id == customer_id))
        wallet_obj = w_res.scalar_one_or_none()
        if wallet_obj and wallet_obj.available_balance > 0:
            max_payable = max(0.0, round(total_amount - total_discount_amount + total_delivery_charge, 2))
            total_wallet_discount = round(min(wallet_obj.available_balance, max_payable), 2)
            if order_request.wallet_amount and order_request.wallet_amount > 0:
                total_wallet_discount = round(min(total_wallet_discount, float(order_request.wallet_amount)), 2)
            if total_wallet_discount > 0:
                wallet_obj.available_balance = round(max(0.0, wallet_obj.available_balance - total_wallet_discount), 2)
                db.add(wallet_obj)

    # ── Create Separate Orders Per Item ────────────────────────────────────────
    from sqlalchemy import insert as sql_insert
    created_order_ids = []
    created_order_items_list = []
    
    for item_data in order_items_data:
        item_subtotal = round(item_data["price"] * item_data["quantity"], 2)
        
        # Pro-rata discount
        item_discount = 0.0
        if total_amount > 0:
            item_discount = round((item_subtotal / total_amount) * total_discount_amount, 2)
            
        # Pro-rata wallet discount
        item_wallet_discount = 0.0
        if total_amount > 0 and total_wallet_discount > 0:
            item_wallet_discount = round((item_subtotal / total_amount) * total_wallet_discount, 2)
            
        # Pro-rata delivery charge (for same dealer grouping)
        item_delivery = 0.0
        dealer_info = dealer_fees_map.get(item_data["dealer_id"], {"fee": 0.0, "total_dealer_subtotal": 0.0})
        if dealer_info["total_dealer_subtotal"] > 0:
            item_delivery = round((item_subtotal / dealer_info["total_dealer_subtotal"]) * dealer_info["fee"], 2)
            
        total_item_discount = round(item_discount + item_wallet_discount, 2)
        final_item_total = round(max(0.0, item_subtotal - total_item_discount) + item_delivery + item_data["platform_fee"], 2)
        
        tax_data = item_data["tax_data"]
        
        print(f"[DEBUG] STAGE 3: BEFORE creating Order model")
        print(f"[DEBUG] STAGE 3: Order.is_inter_state = {tax_data.get('is_inter_state')}")
        print(f"[DEBUG] STAGE 3: Order.cgst_amount = {tax_data.get('cgst_amount')}")
        print(f"[DEBUG] STAGE 3: Order.sgst_amount = {tax_data.get('sgst_amount')}")
        print(f"[DEBUG] STAGE 3: Order.igst_amount = {tax_data.get('igst_amount')}")
        print()
        
        order_result = await db.execute(
            sql_insert(OrderModel).values(
                customer_id=customer_id,
                subtotal=item_subtotal,
                order_number=generate_order_number(),
                discount_amount=total_item_discount,
                wallet_amount_used=item_wallet_discount,
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
                billing_address_id=order_request.billing_address_id if order_request else None,
                # Platform Revenue
                platform_fee_amount=item_data["platform_fee"]
            ).returning(OrderModel.id)
        )
        new_order_id = order_result.scalar_one()
        created_order_ids.append(new_order_id)
        
        if item_wallet_discount > 0:
            from models.referral import WalletTransaction, WalletTransactionType
            await db.execute(
                sql_insert(WalletTransaction).values(
                    customer_id=customer_id,
                    amount=item_wallet_discount,
                    transaction_type=WalletTransactionType.DEBIT,
                    description=f"Used wallet balance for Order #{new_order_id}",
                    order_id=new_order_id
                )
            )
        
        print(f"[DEBUG] STAGE 4: BEFORE creating OrderItem")
        print(f"[DEBUG] STAGE 4: OrderItem.cgst_rate = {tax_data.get('cgst_rate')}")
        print(f"[DEBUG] STAGE 4: OrderItem.sgst_rate = {tax_data.get('sgst_rate')}")
        print(f"[DEBUG] STAGE 4: OrderItem.igst_rate = {tax_data.get('igst_rate')}")
        print(f"[DEBUG] STAGE 4: OrderItem.cgst_amount = {tax_data.get('cgst_amount')}")
        print(f"[DEBUG] STAGE 4: OrderItem.sgst_amount = {tax_data.get('sgst_amount')}")
        print(f"[DEBUG] STAGE 4: OrderItem.igst_amount = {tax_data.get('igst_amount')}")
        print()
        
        # Insert matching OrderItem
        item_result = await db.execute(
            sql_insert(OrderItemModel).values(
                order_id=new_order_id,
                product_id=item_data["product_id"],
                variant_id=item_data.get("variant_id"),
                quantity=item_data["quantity"],
                price=item_data["price"],
                size=item_data.get("size"),
                variant_attributes=item_data.get("variant_attributes"),
                status="order_placed",
                tax_amount=tax_data["total_tax"],
                cgst_rate=tax_data["cgst_rate"],
                sgst_rate=tax_data["sgst_rate"],
                igst_rate=tax_data["igst_rate"],
                cgst_amount=tax_data["cgst_amount"],
                sgst_amount=tax_data["sgst_amount"],
                igst_amount=tax_data["igst_amount"],
                platform_fee=item_data["platform_fee"]
            ).returning(OrderItemModel.id)
        )
        new_item_id = item_result.scalar_one()
        created_order_items_list.append((new_order_id, new_item_id, item_data))

        # Checkout GST logging
        source = "tax_category_id" if tax_data.get("tax_category_id") else "Legacy tax_rule_id fallback"
        prod_name = item_data.get('product_name', '')
        gst_logger.info(
            "[Checkout][GST] Order: %s | Product ID: %s | Product Name: %s | GST Slab: %s%% | Source: %s | CGST: %s%% | SGST: %s%% | IGST: %s%% | Tax Amount: ₹%s",
            new_order_id,
            item_data['product_id'],
            prod_name,
            tax_data['cgst_rate'] + tax_data['sgst_rate'] if not tax_data['is_inter_state'] else tax_data['igst_rate'],
            source,
            tax_data['cgst_rate'],
            tax_data['sgst_rate'],
            tax_data['igst_rate'],
            tax_data['total_tax']
        )
        gst_logger.info(
            "[Order Snapshot] Order: %s | Order Item: %s | Product ID: %s | Product Name: %s | CGST: %s%% | SGST: %s%% | IGST: %s%% | Tax Amount: ₹%s | Source: %s",
            new_order_id, new_item_id,
            item_data['product_id'],
            prod_name,
            tax_data['cgst_rate'], tax_data['sgst_rate'], tax_data['igst_rate'],
            tax_data['total_tax'],
            source
        )
        
        # Insert OrderInvoice
        invoice_result = await db.execute(
            sql_insert(OrderInvoiceModel).values(
                order_id=new_order_id,
                dealer_id=item_data["dealer_id"],
                invoice_number=await TaxService.generate_tax_invoice_number(db),
                total_amount=final_item_total,
                tax_amount=tax_data["total_tax"],
                is_reverse_charge=False
            )
        )
        
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

    # Track Category-Specific Lifetime Referral Commission if customer was referred
    try:
        from models.referral import (
            CustomerReferralProfile,
            ReferralOrderCommission,
            ReferralItemCommission,
            CommissionStatus
        )
        res_ref = await db.execute(
            select(CustomerReferralProfile).where(CustomerReferralProfile.customer_id == customer_id)
        )
        ref_profile = res_ref.scalar_one_or_none()
        if ref_profile and ref_profile.referred_by_id:
            cats_res = await db.execute(select(CategoryModel))
            cats_map = {c.id: (c.referral_commission_rate if c.referral_commission_rate is not None else 2.0) for c in cats_res.scalars().all()}
            for ord_id, itm_id, itm_data in created_order_items_list:
                cat_id = itm_data.get("category_id")
                prod_rate = itm_data.get("referral_commission_rate")
                if prod_rate is not None:
                    rate_pct = float(prod_rate)
                else:
                    rate_pct = cats_map.get(cat_id, 2.0)
                item_total = itm_data["price"] * itm_data["quantity"]
                comm_amt = round(item_total * (rate_pct / 100.0), 2)
                if comm_amt > 0:
                    ord_comm = ReferralOrderCommission(
                        referrer_id=ref_profile.referred_by_id,
                        referee_id=customer_id,
                        order_id=ord_id,
                        total_commission_amount=comm_amt,
                        status=CommissionStatus.PENDING
                    )
                    db.add(ord_comm)
                    await db.flush()
                    item_comm = ReferralItemCommission(
                        order_commission_id=ord_comm.id,
                        order_item_id=itm_id,
                        category_id=cat_id,
                        item_price=item_total,
                        applied_rate_percent=rate_pct,
                        commission_amount=comm_amt,
                        status=CommissionStatus.PENDING
                    )
                    db.add(item_comm)
    except Exception as e:
        print(f"DEBUG: Referral commission creation error: {e}")

    # Clear cart
    await db.execute(
        delete(CartItemModel).where(CartItemModel.customer_id == customer_id)
    )
    
    print(f"\n[DEBUG] STAGE 5: BEFORE session.commit()")
    print(f"[DEBUG] STAGE 5: About to commit the transaction...")
    print()
    
    await db.commit()
    
    print(f"\n[DEBUG] STAGE 5: AFTER session.commit()")
    print(f"[DEBUG] STAGE 5: Querying database for the created order...")
    print()
    
    # Query the database for the SAME order that was just created
    # Get the most recent order for this customer
    import sqlalchemy as sql
    
    # Get the orders that were just created
    if created_order_ids:
        # Query Orders table
        orders_query = sql.select(
            OrderModel.id,
            OrderModel.is_inter_state,
            OrderModel.cgst_amount,
            OrderModel.sgst_amount,
            OrderModel.igst_amount
        ).where(OrderModel.id.in_(created_order_ids))
        
        orders_result = await db.execute(orders_query)
        orders = orders_result.mappings().all()
        
        print(f"[DEBUG] STAGE 5: Orders table values:")
        for order in orders:
            print(f"[DEBUG] STAGE 5:   Order ID: {order['id']}")
            print(f"[DEBUG] STAGE 5:   is_inter_state: {order['is_inter_state']}")
            print(f"[DEBUG] STAGE 5:   cgst_amount: {order['cgst_amount']}")
            print(f"[DEBUG] STAGE 5:   sgst_amount: {order['sgst_amount']}")
            print(f"[DEBUG] STAGE 5:   igst_amount: {order['igst_amount']}")
            print()
            
            # Query OrderItems table for this order
            items_query = sql.select(
                OrderItemModel.order_id,
                OrderItemModel.cgst_rate,
                OrderItemModel.sgst_rate,
                OrderItemModel.igst_rate,
                OrderItemModel.cgst_amount,
                OrderItemModel.sgst_amount,
                OrderItemModel.igst_amount
            ).where(OrderItemModel.order_id == order['id'])
            
            items_result = await db.execute(items_query)
            items = items_result.mappings().all()
            
            print(f"[DEBUG] STAGE 5: OrderItems table values:")
            for item in items:
                print(f"[DEBUG] STAGE 5:   Order ID: {item['order_id']}")
                print(f"[DEBUG] STAGE 5:   cgst_rate: {item['cgst_rate']}")
                print(f"[DEBUG] STAGE 5:   sgst_rate: {item['sgst_rate']}")
                print(f"[DEBUG] STAGE 5:   igst_rate: {item['igst_rate']}")
                print(f"[DEBUG] STAGE 5:   cgst_amount: {item['cgst_amount']}")
                print(f"[DEBUG] STAGE 5:   sgst_amount: {item['sgst_amount']}")
                print(f"[DEBUG] STAGE 5:   igst_amount: {item['igst_amount']}")
                print()
    
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
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            ),

            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns)
        )
        .order_by(OrderModel.created_at.desc())
    )
    return res.scalars().all()

@router.post("/orders/{order_id}/checkout", response_model=list, tags=["orders"])
async def checkout_pending_order(
    order_id: int,
    order_request: OrderRequest,
    background_tasks: BackgroundTasks,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Checkout an existing pending order (e.g. from an auction win)"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id, OrderModel.customer_id == current_user.id)
        .options(selectinload(OrderModel.items))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Order is not pending. Current status: {order.status}")
        
    if not order_request.address_id:
        raise HTTPException(status_code=400, detail="Shipping address is required")
        
    order.shipping_address_id = order_request.address_id
    order.payment_method = order_request.payment_method or "COD"
    order.status = OrderStatus.ORDER_PLACED
    
    for item in order.items:
        item.status = "order_placed"
        
    user_email = current_user.email
    order_id_val = order.id
    order_total = order.total_amount
    
    await db.commit()
    
    background_tasks.add_task(
        EmailService.send_order_confirmation,
        to_email=user_email,
        order_data={"ids": [order_id_val], "total": order_total}
    )
    
    try:
        from services.notification import AppNotificationService
        from models import NotificationType
        await AppNotificationService.create_notification(
            db,
            customer_id=current_user.id,
            type=NotificationType.ORDER_PLACED,
            title="Order Placed!",
            message=f"Your order ID {order_id_val} has been placed successfully. Thank you for shopping!"
        )
        await db.commit()
    except Exception as e:
        print(f"Error sending in-app notification: {e}")
        
    res = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order.id)
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            ),
            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns)
        )
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
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.children).selectinload(ProductModel.children),
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.dealer),
            selectinload(OrderModel.items).selectinload(OrderItemModel.product).selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
            selectinload(OrderModel.items).selectinload(OrderItemModel.variant),
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

@router.get("/orders/{order_id}/invoice", tags=["orders"])
async def download_invoice(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Download PDF invoice for an order"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id, OrderModel.customer_id == current_user.id)
        .options(
            selectinload(OrderModel.items).selectinload(OrderItemModel.product),
            selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.billing_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.invoices).selectinload(OrderInvoiceModel.dealer).selectinload(DealerModel.state_rel)
        )
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if not order.invoices:
        # Auto-create invoice on the fly if missing
        dealer_id = None
        if order.items and order.items[0].product:
            dealer_id = order.items[0].product.dealer_id
            
        if not dealer_id:
            # Try loading product dealer_id
            prod_res = await db.execute(select(ProductModel).where(ProductModel.id == order.items[0].product_id))
            prod = prod_res.scalar_one_or_none()
            if prod:
                dealer_id = prod.dealer_id

        if not dealer_id:
            raise HTTPException(status_code=404, detail="Dealer information not found for this order")

        from services.tax_service import TaxService
        inv_number = await TaxService.generate_tax_invoice_number(db)
        new_inv = OrderInvoiceModel(
            order_id=order.id,
            dealer_id=dealer_id,
            invoice_number=inv_number,
            total_amount=order.total_amount or 0.0,
            tax_amount=order.tax_amount or 0.0,
            is_reverse_charge=False
        )
        db.add(new_inv)
        await db.commit()
        await db.refresh(new_inv)
        
        dealer_res = await db.execute(
            select(DealerModel).where(DealerModel.id == dealer_id).options(selectinload(DealerModel.state_rel))
        )
        dealer = dealer_res.scalar_one_or_none()
        invoice = new_inv
    else:
        invoice = order.invoices[0]
        dealer = invoice.dealer
    
    from services.invoice_pdf import generate_invoice_pdf
    pdf_buffer = generate_invoice_pdf(
        invoice=invoice,
        dealer=dealer,
        order=order,
        order_items=order.items,
        billing_address=order.billing_address,
        shipping_address=order.shipping_address
    )
    
    filename = f"Invoice_{invoice.invoice_number}.pdf"
    
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
