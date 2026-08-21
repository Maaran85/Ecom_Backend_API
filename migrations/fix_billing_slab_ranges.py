"""
Migration Script: Fix Billing Slab Ranges and Boundary Gaps
Date: 2026-08-17
Description: Updates PostgreSQL billing_slabs to continuously cover all product price ranges from INR 1.00 to infinity, resolving gaps, fractional boundary gaps (e.g. 500.01 to 500.99), and deactivating duplicate active marketing slabs (IDs 46 and 47).
"""

import asyncio
import os
import sys
from sqlalchemy import select, text

backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.database import SessionLocal
from models.billing_slab import BillingSlab

SLAB_UPDATES = [
    # -------------------------------------------------------------------------
    # 1. MARKETPLACE SLABS (Continuous INR 1.00 -> INF)
    # -------------------------------------------------------------------------
    # ID 12: 1.00 - 500.00 (Dealer%: 1.0%, Cust%: 0.5%, Active) -> Unchanged
    (13, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (14, {"min_price": 1000.01, "max_price": 5000.0, "is_active": True}),
    (17, {"min_price": 5000.01, "max_price": 10000.0, "is_active": True}),
    (18, {"min_price": 10000.01, "max_price": 20000.0, "dealer_percentage": 0.07, "customer_percentage": 0.018, "is_active": True}),
    (19, {"min_price": 20000.01, "max_price": 30000.0, "dealer_percentage": 0.07, "customer_percentage": 0.018, "is_active": True}),
    (22, {"min_price": 30000.01, "max_price": 35000.0, "dealer_percentage": 0.055, "customer_percentage": 0.012, "is_active": True}),
    (28, {"min_price": 35000.01, "max_price": 45000.0, "dealer_percentage": 0.05, "customer_percentage": 0.01, "is_active": True}),
    (25, {"min_price": 45000.01, "max_price": None, "dealer_percentage": 0.055, "customer_percentage": 0.012, "is_active": True}),

    # -------------------------------------------------------------------------
    # 2. MARKETING SLABS (Continuous INR 1.00 -> INF)
    # -------------------------------------------------------------------------
    # ID 15: 1.00 - 500.00 (Dealer%: 2.0%, Active) -> Unchanged
    (34, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (35, {"min_price": 1000.01, "max_price": 2000.0, "is_active": True}),
    (20, {"min_price": 2000.01, "max_price": 5000.0, "dealer_percentage": 0.08, "is_active": True}),
    (23, {"min_price": 5000.01, "max_price": 10000.0, "dealer_percentage": 0.075, "is_active": True}),
    (29, {"min_price": 10000.01, "max_price": 25000.0, "dealer_percentage": 0.07, "is_active": True}),
    (45, {"min_price": 25000.01, "max_price": None, "dealer_percentage": 0.05, "is_active": True}),
    (46, {"is_active": False}), # Deactivate duplicate marketing slab
    (47, {"is_active": False}), # Deactivate duplicate marketing slab

    # -------------------------------------------------------------------------
    # 3. LOGISTICS SLABS (Continuous INR 1.00 -> INF)
    # -------------------------------------------------------------------------
    # ID 16: 1.00 - 500.00 (Dealer%: 10.0%, Cust%: 9.0%, Active) -> Unchanged
    (36, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (37, {"min_price": 1000.01, "max_price": 2000.0, "is_active": True}),
    (21, {"min_price": 2000.01, "max_price": 5000.0, "dealer_percentage": 0.06, "is_active": True}),
    (24, {"min_price": 5000.01, "max_price": 10000.0, "dealer_percentage": 0.065, "is_active": True}),
    (30, {"min_price": 10000.01, "max_price": None, "dealer_percentage": 0.06, "is_active": True}),

    # -------------------------------------------------------------------------
    # 4. AUCTION MARKETPLACE SLABS
    # -------------------------------------------------------------------------
    # ID 31: 1.00 - 500.00 -> Unchanged
    (32, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (33, {"min_price": 1000.01, "max_price": None, "is_active": True}),

    # -------------------------------------------------------------------------
    # 5. REFERRAL PURCHASE SLABS
    # -------------------------------------------------------------------------
    # ID 39: 1.00 - 500.00 -> Unchanged
    (40, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (41, {"min_price": 1000.01, "max_price": None, "is_active": True}),

    # -------------------------------------------------------------------------
    # 6. SPIN & WIN SLABS
    # -------------------------------------------------------------------------
    # ID 42: 1.00 - 500.00 -> Unchanged
    (43, {"min_price": 500.01, "max_price": 1000.0, "is_active": True}),
    (44, {"min_price": 1000.01, "max_price": None, "is_active": True}),
]


async def run_migration():
    print("==========================================================================")
    print("APPLYING BILLING SLAB RANGE & FRACTIONAL GAP MIGRATION")
    print("==========================================================================")
    
    async with SessionLocal() as db:
        try:
            modified_count = 0
            for slab_id, field_dict in SLAB_UPDATES:
                stmt = select(BillingSlab).where(BillingSlab.id == slab_id)
                res = await db.execute(stmt)
                slab = res.scalar_one_or_none()
                if not slab:
                    print(f"  WARNING: BillingSlab ID {slab_id} not found in database!")
                    continue
                
                print(f"  Updating ID {slab.id:<2} ({slab.category_key:<20}): Old [Min={slab.min_price}, Max={slab.max_price}, Active={slab.is_active}]")
                for key, val in field_dict.items():
                    setattr(slab, key, val)
                
                print(f"                     -> New [Min={slab.min_price}, Max={slab.max_price}, Active={slab.is_active}]")
                modified_count += 1
            
            await db.commit()
            print(f"\n[SUCCESS] Migration committed. Successfully updated {modified_count} billing slabs.")
        except Exception as err:
            await db.rollback()
            print(f"\n[ERROR] Migration failed and rolled back: {err}")
            raise

if __name__ == "__main__":
    asyncio.run(run_migration())
