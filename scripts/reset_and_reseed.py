import asyncio
import os
import sys
import random

sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, text
from core.database import SessionLocal, engine
from models import (
    Product, Order, OrderItem, DealerRemittance, 
    TaxLedger, Dealer, TaxRule, Category, ProductVariant,
    RiderEarning, Review, WishlistItem, CartItem
)

async def reset_and_reseed():
    async with SessionLocal() as db:
        try:
            print("🚀 Starting Database Reset...")
            
            # 1. Clear Tables in correct order (child then parent)
            # Use raw SQL for tables with unknown model names if necessary
            await db.execute(delete(RiderEarning))
            await db.execute(text("DELETE FROM rider_reviews"))
            await db.execute(text("DELETE FROM review_votes"))
            await db.execute(delete(Review))
            await db.execute(delete(TaxLedger))
            await db.execute(text("DELETE FROM stock_movements"))
            await db.execute(delete(WishlistItem))
            await db.execute(delete(OrderItem))
            await db.execute(delete(Order))
            await db.execute(delete(DealerRemittance))
            await db.execute(delete(ProductVariant))
            await db.execute(delete(CartItem))
            await db.execute(delete(Product))
            
            await db.commit()
            print("✅ Orders, Items, Remittances, and Products cleared.")

            # 2. Re-Seed Products
            print("🌱 Seeding 500 New Products...")
            
            # Get needed IDs
            dealer_res = await db.execute(select(Dealer).limit(10))
            dealers = dealer_res.scalars().all()
            
            tax_rule_res = await db.execute(select(TaxRule).limit(10))
            tax_rules = tax_rule_res.scalars().all()
            
            cat_res = await db.execute(select(Category).where(Category.parent_id.isnot(None)))
            categories = cat_res.scalars().all()
            
            if not dealers or not tax_rules or not categories:
                print("❌ Missing prerequisite data (Dealers/TaxRules/Categories). Abortion.")
                return

            print(f"   Using {len(dealers)} dealers, {len(tax_rules)} tax rules, and {len(categories)} categories.")

            for i in range(1, 501):
                dealer = random.choice(dealers)
                tax_rule = random.choice(tax_rules)
                # Cycle through categories to ensure even distribution
                category = categories[i % len(categories)]

                
                # GST Rate (from TaxRule)
                # Need to Eager Load TaxCategory info
                # Let's simplify and just assume 18% if relationship not loaded
                gst_rate = 18.0
                fee_percent = dealer.platform_fee_percent or 5.0
                
                base_price = random.randint(100, 10000)
                
                # Calculation Logic:
                # 1. Product Inclusive = Base * (1 + GST_Rate/100)
                product_inclusive = base_price * (1 + (gst_rate / 100))
                # 2. Final MRP = product_inclusive * (1 + Platform_Fee/100)
                final_mrp = round(product_inclusive * (1 + (fee_percent / 100)), 2)
                
                # Optional discount
                discount_price = None
                discount_percent = None
                if random.random() > 0.7:
                    discount_percent = random.choice([10, 20, 30, 50])
                    discount_price = round(final_mrp * (1 - (discount_percent / 100)), 2)

                # Sizes only for apparel
                product_sizes = []
                if category.name.lower() in ["men", "women", "boys", "girls", "kids", "footwear", "clothing"]:
                    product_sizes = ["S", "M", "L", "XL", "XXL"]
                elif "shoe" in category.name.lower() or "footwear" in category.name.lower():
                    product_sizes = ["6", "7", "8", "9", "10"]

                p = Product(
                    name=f"Authentic Product {1000 + i}",
                    description=f"A premium quality product verified for your comfort. SKU {i}.",
                    price=final_mrp,
                    discount_price=discount_price,
                    discount_percentage=discount_percent,
                    stock=random.randint(20, 500),
                    category_id=category.id,
                    subcategory=category.name,
                    dealer_id=dealer.id,
                    is_approved=True,
                    gender=random.choice(["Men", "Women", "Unisex"]),
                    brand=random.choice(["Nike", "Adidas", "Puma", "Levis", "Lotto"]),
                    sizes=product_sizes,
                    hsn_code=f"HSN-{7000 + i}",
                    tax_rule_id=tax_rule.id,
                    images=["https://images.unsplash.com/photo-1542291026-7eec264c27ff"] # Shoestore example
                )
                db.add(p)
                
                if i % 100 == 0:
                    print(f"   Seeding products... {i}/500")

            await db.commit()
            print(f"🎉 SUCCESS! reset and seeded 500 products with proper Hidden Markup calculation.")
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Error during reset/seed: {e}")
        finally:
            await db.close()

if __name__ == "__main__":
    asyncio.run(reset_and_reseed())
