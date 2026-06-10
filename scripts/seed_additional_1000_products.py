import asyncio
import os
import sys
import random

# Fix to point to right working dir and import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from core.database import SessionLocal
from models import Product, Dealer, TaxRule, Category

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def seed_products():
    with open("output.txt", "w") as f:
        f.write("Starting script...\n")
    async with SessionLocal() as db:
        try:
            print("Starting Database Seeding (Additional 1000 Products)...")
            
            # Get Needed Data
            dealer_res = await db.execute(select(Dealer))
            dealers = dealer_res.scalars().all()
            
            tax_rule_res = await db.execute(select(TaxRule))
            tax_rules = tax_rule_res.scalars().all()
            
            # Use ALL categories for mixed categories
            cat_res = await db.execute(select(Category))
            all_categories = cat_res.scalars().all()
            
            if not dealers or not tax_rules or not all_categories:
                msg = f"❌ Missing prerequisite data (Dealers: {len(dealers)}, TaxRules: {len(tax_rules)}, Categories: {len(all_categories)})."
                print(msg)
                with open("output.txt", "a") as f:
                    f.write(msg + "\n")
                return

            print(f"   Using {len(dealers)} dealers, {len(tax_rules)} tax rules, and {len(all_categories)} categories.")
            
            images_map = {
                "electronics": [
                    "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=500&q=80",
                    "https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=500&q=80",
                    "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=500&q=80"
                ],
                "clothing": [
                    "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500&q=80",
                    "https://images.unsplash.com/photo-1503342217505-b0a15ec3261c?w=500&q=80",
                    "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=500&q=80"
                ],
                "shoes": [
                    "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500&q=80",
                    "https://images.unsplash.com/photo-1560769629-975ec94e6a86?w=500&q=80",
                    "https://images.unsplash.com/photo-1608231387042-66d1773070a5?w=500&q=80"
                ],
                "home": [
                    "https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=500&q=80",
                    "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=500&q=80"
                ],
                "beauty": [
                    "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=500&q=80",
                    "https://images.unsplash.com/photo-1522337360788-8b13fee7a3af?w=500&q=80"
                ],
                "food": [
                     "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=500&q=80",
                     "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500&q=80"
                ],
                "sports": [
                     "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=500&q=80",
                     "https://images.unsplash.com/photo-1541534741688-6078c6bfb5c5?w=500&q=80"
                ],
                "default": [
                    "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500&q=80",
                    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500&q=80",
                    "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=500&q=80",
                    "https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=500&q=80"
                ]
            }

            for i in range(1, 1001):
                dealer = random.choice(dealers)
                tax_rule = random.choice(tax_rules)
                category = random.choice(all_categories)
                
                cat_name_lower = category.name.lower()
                image_set = images_map["default"]
                if "electronic" in cat_name_lower or "mobile" in cat_name_lower or "laptop" in cat_name_lower:
                    image_set = images_map["electronics"]
                elif "cloth" in cat_name_lower or "apparel" in cat_name_lower or "fashion" in cat_name_lower or "men" in cat_name_lower or "women" in cat_name_lower:
                    image_set = images_map["clothing"]
                elif "shoe" in cat_name_lower or "footwear" in cat_name_lower:
                    image_set = images_map["shoes"]
                elif "home" in cat_name_lower or "furniture" in cat_name_lower or "decor" in cat_name_lower:
                    image_set = images_map["home"]
                elif "beauty" in cat_name_lower or "health" in cat_name_lower or "makeup" in cat_name_lower or "care" in cat_name_lower:
                    image_set = images_map["beauty"]
                elif "food" in cat_name_lower or "grocery" in cat_name_lower:
                    image_set = images_map["food"]
                elif "sport" in cat_name_lower or "fitness" in cat_name_lower:
                    image_set = images_map["sports"]
                
                product_images = [random.choice(image_set), random.choice(image_set)]

                gst_rate = 18.0
                fee_percent = dealer.platform_fee_percent or 5.0
                base_price = random.randint(100, 10000)
                product_inclusive = base_price * (1 + (gst_rate / 100))
                final_mrp = round(product_inclusive * (1 + (fee_percent / 100)), 2)
                
                discount_price = None
                discount_percent = None
                if random.random() > 0.5:
                    discount_percent = random.choice([10, 20, 30, 40, 50, 60])
                    discount_price = round(final_mrp * (1 - (discount_percent / 100)), 2)

                product_sizes = []
                if "men" in cat_name_lower or "women" in cat_name_lower or "kids" in cat_name_lower or "wear" in cat_name_lower or "cloth" in cat_name_lower or "apparel" in cat_name_lower:
                    product_sizes = ["S", "M", "L", "XL", "XXL"]
                elif "shoe" in cat_name_lower or "footwear" in cat_name_lower:
                    product_sizes = ["6", "7", "8", "9", "10", "11"]

                p = Product(
                    name=f"Premium {category.name} Select {random.randint(1000, 9999)}",
                    description=f"A top-quality authentic product from {dealer.business_name} in the {category.name} category. 100% genuine guaranteed.",
                    price=final_mrp,
                    discount_price=discount_price,
                    discount_percentage=discount_percent,
                    stock=random.randint(10, 1000),
                    category_id=category.id,
                    subcategory=category.name,
                    dealer_id=dealer.id,
                    is_approved=True,
                    gender=random.choice(["Men", "Women", "Unisex", "Kids"]),
                    brand=random.choice(["EliteBrand", "NextStyle", "CoreCo", "EcoLine", "PureFit", "MaxPro"]),
                    color=random.choice(["Black", "White", "Blue", "Red", "Green", "Silver", "Gold", "Grey"]),
                    sizes=product_sizes,
                    hsn_code=f"HSN-{random.randint(1000, 9999)}",
                    tax_rule_id=tax_rule.id,
                    images=product_images
                )
                db.add(p)
                
                if i % 100 == 0:
                    print(f"   Seeding additional products... {i}/1000")

            await db.commit()
            print("SUCCESS! seeded 1000 additional products correctly.")
            with open("output.txt", "a") as f:
                f.write("SUCCESS! seeded 1000 additional products correctly.\n")
            
        except Exception as e:
            await db.rollback()
            print(f"Error during seed: {e}")
            with open("output.txt", "a") as f:
                f.write(f"ERROR: {e}\n")
        finally:
            await db.close()

if __name__ == "__main__":
    asyncio.run(seed_products())
