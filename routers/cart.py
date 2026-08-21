import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Response
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
from uuid import UUID
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

    # Buy Now fields
    is_buy_now: Optional[bool] = False
    product_id: Optional[UUID] = None
    variant_id: Optional[UUID] = None
    quantity: Optional[int] = 1
    size: Optional[str] = None

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
    
    # Verify product exists, is approved, and seller is active
    prod_check = await db.execute(
        select(ProductModel)
        .join(DealerModel, ProductModel.dealer_id == DealerModel.id)
        .where(
            ProductModel.id == product_id,
            ProductModel.is_deleted == False,
            ProductModel.is_approved == True,
            DealerModel.access_status == 'active',
            DealerModel.is_active == True,
            DealerModel.is_deleted == False
        )
    )
    product_exists = prod_check.scalar_one_or_none()
    if product_exists is None:
        raise HTTPException(
            status_code=400,
            detail="This product is currently unavailable or the seller is inactive."
        )

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

    # Re-fetch with eager loading
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
    cart_item = res.scalar_one_or_none()
    if not cart_item:
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
    result = await db.execute(
        select(CartItemModel.id)
        .where(CartItemModel.id == item_id, CartItemModel.customer_id == current_user.id)
    )
    if not result.first():
        raise HTTPException(status_code=404, detail="Cart item not found")
    if update_in.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")

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
    """Create order (Supports both Cart Checkout and Buy Now)"""
    customer_id = int(current_user.id)
    user_email = str(current_user.email)

    total_amount = 0.0
    total_delivery_charge = 0.0
    order_items_data = []
    stock_updates = []
    dealer_subtotals: dict[int, float] = {}

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

    if order_request and order_request.is_buy_now:
        # ── PATH B: BUY NOW FLOW (Direct Purchase - Does NOT query or clear Cart) ──
        if not order_request.product_id:
            raise HTTPException(status_code=400, detail="product_id is required for Buy Now order.")

        qty = max(1, int(order_request.quantity or 1))

        # Load product directly
        prod_res = await db.execute(
            select(ProductModel)
            .where(ProductModel.id == order_request.product_id)
            .options(
                joinedload(ProductModel.dealer).selectinload(DealerModel.state_rel),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            )
        )
        product = prod_res.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found.")
        if not product.is_approved:
            raise HTTPException(status_code=400, detail="This product is currently pending approval.")
        if product.is_deleted:
            raise HTTPException(status_code=400, detail="This product is no longer available.")
        if not product.dealer or not product.dealer.is_active or product.dealer.access_status != 'active' or getattr(product.dealer, 'is_deleted', False):
            raise HTTPException(status_code=400, detail="The seller for this product is currently inactive.")

        # Check stock
        if order_request.variant_id:
            target_variant = next((v for v in (product.children or []) if v.id == order_request.variant_id), None)
            if not target_variant:
                res_v = await db.execute(select(ProductModel).where(ProductModel.id == order_request.variant_id))
                target_variant = res_v.scalar_one_or_none()
            if not target_variant:
                raise HTTPException(status_code=404, detail="Selected variant not found.")
            if target_variant.stock < qty:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name}")
        else:
            if product.stock < qty:
                raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name}")

        price = float(product.selling_price if product.selling_price else (product.mrp or product.dealer_price))
        total_amount = price * qty
        if product.dealer_id:
            dealer_subtotals[product.dealer_id] = total_amount

        buyer_state = shipping_address.state_rel.state_code if (shipping_address and shipping_address.state_rel) else None
        seller_state = product.dealer.state_code if product.dealer else None

        tax_res = await TaxService.calculate_item_tax(
            db=db,
            base_price=price,
            qty=qty,
            product_id=product.id,
            buyer_state=buyer_state,
            seller_state=seller_state
        )

        fee_amount = product.dealer.platform_fee_amount if product.dealer else 5.0
        platform_fee = fee_amount * qty

        order_items_data.append({
            "product_id": product.id,
            "product_name": product.name,
            "variant_id": order_request.variant_id,
            "category_id": product.category_id,
            "quantity": qty,
            "price": price,
            "size": order_request.size,
            "variant_attributes": None,
            "dealer_id": product.dealer_id,
            "tax_data": tax_res,
            "platform_fee": platform_fee,
            "referral_commission_rate": product.referral_commission_rate,
            "return_window_days": getattr(product, "return_window_days", None),
            "is_returnable": getattr(product, "is_returnable", True),
            "is_exchangeable": getattr(product, "is_exchangeable", True),
        })
        stock_updates.append({
            "product_id": product.id,
            "variant_id": order_request.variant_id,
            "quantity": qty
        })
    else:
        # ── PATH A: CART CHECKOUT FLOW ──
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
        
        # Clean up any orphaned/unapproved/inactive cart items for this customer
        all_cart_ids_res = await db.execute(select(CartItemModel.id).where(CartItemModel.customer_id == customer_id))
        all_cart_ids = {row[0] for row in all_cart_ids_res.fetchall()}
        valid_cart_ids = {ci.id for ci in cart_items}
        invalid_cart_ids = list(all_cart_ids - valid_cart_ids)

        if invalid_cart_ids:
            await db.execute(delete(CartItemModel).where(CartItemModel.id.in_(invalid_cart_ids)))
            await db.commit()

        if not cart_items:
            raise HTTPException(status_code=400, detail="The items in your cart are no longer available. Please update your cart.")
        
        for cart_item in cart_items:
            product = cart_item.product

            if not product:
                raise HTTPException(status_code=404, detail=f"Product {cart_item.product_id} not found")

            if cart_item.variant_id:
                variant = next((v for v in (product.children or []) if v.id == cart_item.variant_id), None)
                if not variant:
                    res = await db.execute(select(ProductModel).where(ProductModel.id == cart_item.variant_id))
                    variant = res.scalar_one_or_none()
                
                if not variant:
                     raise HTTPException(status_code=404, detail=f"Variant {cart_item.variant_id} not found")
                
                if variant.stock < cart_item.quantity:
                    raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name} (Size: {variant.sizes[0] if variant.sizes else 'Unknown'})")
            else:
                if product.stock < cart_item.quantity:
                    raise HTTPException(status_code=400, detail=f"Not enough stock for {product.name}")

            price = float(product.selling_price if product.selling_price else (product.mrp or product.dealer_price))
            line_total = price * cart_item.quantity
            total_amount += line_total

            d_id = product.dealer_id
            if d_id:
                dealer_subtotals[d_id] = dealer_subtotals.get(d_id, 0.0) + line_total

            buyer_state = shipping_address.state_rel.state_code if (shipping_address and shipping_address.state_rel) else None
            seller_state = product.dealer.state_code if product.dealer else None
            
            tax_res = await TaxService.calculate_item_tax(
                db=db,
                base_price=price,
                qty=cart_item.quantity,
                product_id=product.id,
                buyer_state=buyer_state,
                seller_state=seller_state
            )
            
            fee_amount = product.dealer.platform_fee_amount if product.dealer else 5.0
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
                "tax_data": tax_res,
                "platform_fee": platform_fee,
                "referral_commission_rate": product.referral_commission_rate,
                "return_window_days": getattr(product, "return_window_days", None),
                "is_returnable": getattr(product, "is_returnable", True),
                "is_exchangeable": getattr(product, "is_exchangeable", True),
            })
            stock_updates.append({
                "product_id": product.id,
                "variant_id": cart_item.variant_id,
                "quantity": int(cart_item.quantity)
            })

    # ── Delivery Charge Breakdown ──────────────────────────────────────────────
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
        
        from models.inventory import ProductInventory
        inv_result = await db.execute(
            select(ProductInventory)
            .where(ProductInventory.product_id == target_id)
            .order_by(ProductInventory.stock.desc())
            .with_for_update()
        )
        inv = inv_result.scalars().first()
        if not inv or inv.stock < qty:
            raise HTTPException(
                status_code=400,
                detail="Not enough stock available to complete this order."
            )
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
        
        item_discount = 0.0
        if total_amount > 0:
            item_discount = round((item_subtotal / total_amount) * total_discount_amount, 2)
            
        item_wallet_discount = 0.0
        if total_amount > 0 and total_wallet_discount > 0:
            item_wallet_discount = round((item_subtotal / total_amount) * total_wallet_discount, 2)
            
        item_delivery = 0.0
        dealer_info = dealer_fees_map.get(item_data["dealer_id"], {"fee": 0.0, "total_dealer_subtotal": 0.0})
        if dealer_info["total_dealer_subtotal"] > 0:
            item_delivery = round((item_subtotal / dealer_info["total_dealer_subtotal"]) * dealer_info["fee"], 2)
            
        total_item_discount = round(item_discount + item_wallet_discount, 2)
        final_item_total = round(max(0.0, item_subtotal - total_item_discount) + item_delivery + item_data["platform_fee"], 2)
        
        tax_data = item_data["tax_data"]
        
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
                tax_amount=tax_data["total_tax"],
                cgst_amount=tax_data["cgst_amount"],
                sgst_amount=tax_data["sgst_amount"],
                igst_amount=tax_data["igst_amount"],
                is_inter_state=tax_data["is_inter_state"],
                billing_address_id=order_request.billing_address_id if order_request else None,
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
        
        # Compute transaction-time billing slab snapshot values
        gross_sale_val = Decimal(str(max(0.0, item_subtotal - total_item_discount)))
        from services.fee_service import get_applicable_slab
        mp_slab = await get_applicable_slab(db, "marketplace", gross_sale_val)
        mkt_slab = await get_applicable_slab(db, "marketing", gross_sale_val)
        log_slab = await get_applicable_slab(db, "logistics", gross_sale_val)

        snap_mp_cust = round(float(gross_sale_val * Decimal(str(mp_slab.customer_percentage))), 2) if (mp_slab and mp_slab.customer_percentage) else 0.0
        snap_mp_dealer = round(float(gross_sale_val * Decimal(str(mp_slab.dealer_percentage))), 2) if mp_slab else 0.0
        snap_mkt = round(float(gross_sale_val * Decimal(str(mkt_slab.dealer_percentage))), 2) if mkt_slab else 0.0
        snap_log_dealer = round(float(gross_sale_val * Decimal(str(log_slab.dealer_percentage))), 2) if log_slab else 0.0
        snap_log_cust = round(float(gross_sale_val * Decimal(str(log_slab.customer_percentage))), 2) if (log_slab and log_slab.customer_percentage) else item_delivery

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
                platform_fee=item_data["platform_fee"],
                marketplace_customer_charge=snap_mp_cust,
                marketplace_dealer_fee=snap_mp_dealer,
                marketing_fee_amount=snap_mkt,
                logistics_charge_amount=snap_log_dealer,
                logistics_customer_charge=snap_log_cust,
                return_window_days=item_data.get("return_window_days"),
                is_returnable=item_data.get("is_returnable"),
                is_exchangeable=item_data.get("is_exchangeable"),
            ).returning(OrderItemModel.id)
        )
        new_item_id = item_result.scalar_one()
        created_order_items_list.append((new_order_id, new_item_id, item_data))

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
        
        await db.execute(
            sql_insert(OrderInvoiceModel).values(
                order_id=new_order_id,
                dealer_id=item_data["dealer_id"],
                invoice_number=await TaxService.generate_tax_invoice_number(db),
                total_amount=final_item_total,
                tax_amount=tax_data["total_tax"],
                is_reverse_charge=False
            )
        )
        
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

    # Clear cart only for normal Cart Checkout (Path A)
    if not (order_request and order_request.is_buy_now):
        await db.execute(
            delete(CartItemModel).where(CartItemModel.customer_id == customer_id)
        )
    
    await db.commit()

    background_tasks.add_task(
        EmailService.send_order_confirmation,
        to_email=user_email,
        order_data={"ids": created_order_ids, "total": total_amount}
    )

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
            selectinload(OrderModel.returns),
            selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.billing_address).selectinload(AddressModel.state_rel)
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
        raise HTTPException(status_code=400, detail="Order is not in pending status")
        
    if order_request.address_id:
        order.shipping_address_id = order_request.address_id
    if order_request.billing_address_id:
        order.billing_address_id = order_request.billing_address_id
    if order_request.payment_method:
        order.payment_method = order_request.payment_method
        
    order.status = OrderStatus.ORDER_PLACED.value
    await db.commit()
    
    res = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id)
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            ),
            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns),
            selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.billing_address).selectinload(AddressModel.state_rel)
        )
    )
    return [res.scalar_one()]

@router.get("/orders", response_model=List[Order], tags=["orders"])
async def get_orders(
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders for current user"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.customer_id == current_user.id)
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            ),
            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns),
            selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.billing_address).selectinload(AddressModel.state_rel)
        )
        .order_by(OrderModel.created_at.desc())
    )
    return result.scalars().all()

@router.get("/orders/{order_id}", response_model=Order, tags=["orders"])
async def get_order(
    order_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific order details"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id, OrderModel.customer_id == current_user.id)
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).options(
                joinedload(ProductModel.dealer),
                selectinload(ProductModel.category).selectinload(CategoryModel.attributes),
                selectinload(ProductModel.children).selectinload(ProductModel.children)
            ),
            selectinload(OrderModel.items).joinedload(OrderItemModel.hub),
            selectinload(OrderModel.returns),
            selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
            selectinload(OrderModel.billing_address).selectinload(AddressModel.state_rel)
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@router.get("/orders/{order_id}/invoice", tags=["orders"])
async def download_order_invoice(
    order_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Generate and download order invoice PDF"""
    result = await db.execute(
        select(OrderModel)
        .where(OrderModel.id == order_id)
        .options(
            selectinload(OrderModel.items).joinedload(OrderItemModel.product).joinedload(ProductModel.dealer),
            selectinload(OrderModel.invoices),
            joinedload(OrderModel.shipping_address),
            joinedload(OrderModel.billing_address)
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    invoice = order.invoices[0] if order.invoices else None
    if not invoice:
        from services.tax_service import TaxService
        invoice = OrderInvoiceModel(
            order_id=order.id,
            invoice_number=await TaxService.generate_tax_invoice_number(db),
            taxable_amount=getattr(order, 'subtotal', 0.0) or 0.0,
            cgst_amount=getattr(order, 'cgst_amount', 0.0) or 0.0,
            sgst_amount=getattr(order, 'sgst_amount', 0.0) or 0.0,
            igst_amount=getattr(order, 'igst_amount', 0.0) or 0.0,
            total_tax=getattr(order, 'tax_amount', 0.0) or 0.0,
            total_amount=getattr(order, 'total_amount', 0.0) or 0.0,
            pdf_url=None
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)

    dealer = None
    if order.items and order.items[0].product:
        dealer = order.items[0].product.dealer

    mkt_sac = "998314"
    log_sac = "996812"
    try:
        from models.billing_slab import BillingSlab
        res_mkt = await db.execute(select(BillingSlab.sac_hsn_code).where(BillingSlab.category_key == 'marketplace', BillingSlab.is_active == True).limit(1))
        found_mkt = res_mkt.scalars().first()
        if found_mkt: mkt_sac = found_mkt

        res_log = await db.execute(select(BillingSlab.sac_hsn_code).where(BillingSlab.category_key == 'logistics', BillingSlab.is_active == True).limit(1))
        found_log = res_log.scalars().first()
        if found_log: log_sac = found_log
    except Exception as e:
        logger.warning(f"Error resolving SAC codes for invoice PDF: {e}")

    from services.invoice_pdf import generate_invoice_pdf
    pdf_buffer = generate_invoice_pdf(
        invoice=invoice,
        dealer=dealer,
        order=order,
        order_items=order.items,
        billing_address=order.billing_address or order.shipping_address,
        shipping_address=order.shipping_address,
        marketplace_sac=mkt_sac,
        logistics_sac=log_sac
    )

    pdf_bytes = pdf_buffer.getvalue()
    filename = f"Invoice_{order.order_number or order.id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )
