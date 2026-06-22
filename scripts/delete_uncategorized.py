import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models import (
    Category, Product, CategoryAttribute,
    CartItem, Order, OrderItem,
    WishlistItem, ProductVariant, Review,
    StockMovement, StockReservation, StockAlert,
    LocationInventory, SupportTicket, Payment,
    TaxLedger, OrderReturn, BulkDiscount, CouponUsage
)
from sqlalchemy import select, delete

async def main():
    async with SessionLocal() as db:
        # 1. Find Uncategorized category
        result = await db.execute(select(Category).where(Category.name == "Uncategorized").where(Category.parent_id == None))
        cat = result.scalars().first()
        if not cat:
            print("Uncategorized category not found.")
            return

        cid = cat.id
        print(f"Found Uncategorized category ID: {cid}")

        # 2. Get all product IDs in this category
        p_result = await db.execute(select(Product.id).where(Product.category_id == cid))
        product_ids = p_result.scalars().all()
        print(f"Found {len(product_ids)} products to delete.")

        if product_ids:
            # 3. Get all order IDs that contain these products
            o_result = await db.execute(select(OrderItem.order_id).where(OrderItem.product_id.in_(product_ids)).distinct())
            order_ids = o_result.scalars().all()
            print(f"Found {len(order_ids)} associated orders to delete.")

            # --- DELETE PRODUCT DEPENDENCIES ---
            print("Deleting Product Dependencies...")
            await db.execute(delete(CartItem).where(CartItem.product_id.in_(product_ids)))
            await db.execute(delete(WishlistItem).where(WishlistItem.product_id.in_(product_ids)))
            await db.execute(delete(ProductVariant).where(ProductVariant.product_id.in_(product_ids)))
            await db.execute(delete(Review).where(Review.product_id.in_(product_ids)))
            await db.execute(delete(StockMovement).where(StockMovement.product_id.in_(product_ids)))
            await db.execute(delete(StockReservation).where(StockReservation.product_id.in_(product_ids)))
            await db.execute(delete(StockAlert).where(StockAlert.product_id.in_(product_ids)))
            await db.execute(delete(LocationInventory).where(LocationInventory.product_id.in_(product_ids)))
            await db.execute(delete(SupportTicket).where(SupportTicket.product_id.in_(product_ids)))
            await db.execute(delete(BulkDiscount).where(BulkDiscount.product_id.in_(product_ids)))

            # --- DELETE ORDER DEPENDENCIES ---
            if order_ids:
                print("Deleting Order Dependencies...")
                await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
                await db.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
                await db.execute(delete(TaxLedger).where(TaxLedger.order_id.in_(order_ids)))
                await db.execute(delete(OrderReturn).where(OrderReturn.order_id.in_(order_ids)))
                await db.execute(delete(CouponUsage).where(CouponUsage.order_id.in_(order_ids)))
                await db.execute(delete(SupportTicket).where(SupportTicket.order_id.in_(order_ids)))
                await db.execute(delete(Review).where(Review.order_id.in_(order_ids)))
                
                print("Deleting Orders...")
                await db.execute(delete(Order).where(Order.id.in_(order_ids)))

            print("Deleting Products...")
            await db.execute(delete(Product).where(Product.category_id == cid))
        
        print("Deleting Category Attributes...")
        await db.execute(delete(CategoryAttribute).where(CategoryAttribute.category_id == cid))

        print("Deleting Uncategorized Category...")
        await db.execute(delete(Category).where(Category.id == cid))

        await db.commit()
        print("Cleanup successful.")

if __name__ == "__main__":
    asyncio.run(main())
