import os, sys, asyncio
backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from core.database import SessionLocal
from models.billing_slab import BillingSlab

CONFIRMED_DEFAULT_SLABS = [
    # 1. Auction Marketplace Charges
    {"category_key": "auction_marketplace", "min_price": 1.0, "max_price": 500.0, "dealer_percentage": 0.02, "customer_percentage": 0.005, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "auction_marketplace", "min_price": 501.0, "max_price": 1000.0, "dealer_percentage": 0.03, "customer_percentage": 0.0075, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "auction_marketplace", "min_price": 1001.0, "max_price": None, "dealer_percentage": 0.04, "customer_percentage": 0.01, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},

    # 2. Marketplace Charges
    {"category_key": "marketplace", "min_price": 1.0, "max_price": 500.0, "dealer_percentage": 0.01, "customer_percentage": 0.005, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "marketplace", "min_price": 501.0, "max_price": 1000.0, "dealer_percentage": 0.015, "customer_percentage": 0.0075, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "marketplace", "min_price": 1001.0, "max_price": None, "dealer_percentage": 0.02, "customer_percentage": 0.01, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},

    # 3. Marketing Commission (Dealer side only)
    {"category_key": "marketing", "min_price": 1.0, "max_price": 500.0, "dealer_percentage": 0.02, "customer_percentage": None, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "marketing", "min_price": 501.0, "max_price": 1000.0, "dealer_percentage": 0.03, "customer_percentage": None, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},
    {"category_key": "marketing", "min_price": 1001.0, "max_price": None, "dealer_percentage": 0.04, "customer_percentage": None, "gst_type": "STANDARD_18", "sac_hsn_code": "998314"},

    # 4. Logistics Charges
    {"category_key": "logistics", "min_price": 1.0, "max_price": 500.0, "dealer_percentage": 0.10, "customer_percentage": 0.09, "gst_type": "STANDARD_18", "sac_hsn_code": "996812"},
    {"category_key": "logistics", "min_price": 501.0, "max_price": 1000.0, "dealer_percentage": 0.09, "customer_percentage": 0.08, "gst_type": "STANDARD_18", "sac_hsn_code": "996812"},
    {"category_key": "logistics", "min_price": 1001.0, "max_price": None, "dealer_percentage": 0.10, "customer_percentage": 0.07, "gst_type": "STANDARD_18", "sac_hsn_code": "996812"},

    # 5. Referral Amount
    {"category_key": "referral", "min_price": 0.0, "max_price": None, "dealer_amount": 100.0, "customer_amount": 100.0, "notes": "Only customer referral commission will be paid. Payment to be made after 3 transactions from the referred customer."},

    # 6. Referral Purchase Commission (Customer-side only, Net Selling Price basis)
    {"category_key": "referral_purchase", "min_price": 1.0, "max_price": 500.0, "customer_percentage": 0.0010, "calculation_basis": "Net Selling Price"},
    {"category_key": "referral_purchase", "min_price": 501.0, "max_price": 1000.0, "customer_percentage": 0.0015, "calculation_basis": "Net Selling Price"},
    {"category_key": "referral_purchase", "min_price": 1001.0, "max_price": None, "customer_percentage": 0.0020, "calculation_basis": "Net Selling Price"},

    # 7. Spin & Win (Fixed Customer Amount ₹)
    {"category_key": "spin_win", "min_price": 1.0, "max_price": 500.0, "customer_amount": 5.0},
    {"category_key": "spin_win", "min_price": 501.0, "max_price": 1000.0, "customer_amount": 10.0},
    {"category_key": "spin_win", "min_price": 1001.0, "max_price": None, "customer_amount": 15.0},
]


async def seed_slabs_idempotent():
    print("==========================================================================")
    print("IDEMPOTENT SEEDING FOR 7 BILLING CONFIGURATION CATEGORIES")
    print("==========================================================================")
    async with SessionLocal() as db:
        added_count = 0
        for item in CONFIRMED_DEFAULT_SLABS:
            # Check if matching slab already exists for category_key + min_price
            stmt = select(BillingSlab).where(
                BillingSlab.category_key == item["category_key"],
                BillingSlab.min_price == item["min_price"]
            )
            res = await db.execute(stmt)
            existing = res.scalar_one_or_none()

            if not existing:
                slab = BillingSlab(**item, is_active=True)
                db.add(slab)
                added_count += 1
                print(f"  + Created missing slab: {item['category_key']} min INR {item['min_price']}")

        await db.commit()
        print(f"[PASS] Idempotent seed finished. Added {added_count} missing slabs.")

if __name__ == "__main__":
    asyncio.run(seed_slabs_idempotent())
