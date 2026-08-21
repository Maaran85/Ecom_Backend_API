import os, sys, asyncio
backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import update, select
from core.database import SessionLocal
from models.billing_slab import BillingSlab

async def align_slabs():
    print("==========================================================================")
    print("ALIGNING PRE-EXISTING SLABS TO MATCH CONFIRMED BUSINESS MATRIX")
    print("==========================================================================")
    async with SessionLocal() as db:
        # Align Marketplace ID 12 (Min 1, Max 500) -> Dealer 1% (0.01), Customer 0.5% (0.005)
        m12 = await db.get(BillingSlab, 12)
        if m12:
            m12.dealer_percentage = 0.01
            m12.customer_percentage = 0.005
            m12.gst_type = "STANDARD_18"
            m12.sac_hsn_code = "998314"
            print("  Updated Marketplace ID 12 -> Dealer 1%, Customer 0.5%")

        # Align Marketplace ID 13 (Min 501, Max 1000) -> Dealer 1.5% (0.015), Customer 0.75% (0.0075)
        m13 = await db.get(BillingSlab, 13)
        if m13:
            m13.dealer_percentage = 0.015
            m13.customer_percentage = 0.0075
            m13.gst_type = "STANDARD_18"
            m13.sac_hsn_code = "998314"
            print("  Updated Marketplace ID 13 -> Dealer 1.5%, Customer 0.75%")

        # Align Marketplace ID 14 (Min 1001+) -> Min 1001, Max None, Dealer 2% (0.02), Customer 1% (0.01)
        m14 = await db.get(BillingSlab, 14)
        if m14:
            m14.max_price = None
            m14.dealer_percentage = 0.02
            m14.customer_percentage = 0.01
            m14.gst_type = "STANDARD_18"
            m14.sac_hsn_code = "998314"
            print("  Updated Marketplace ID 14 -> Min 1001, Max None, Dealer 2%, Customer 1%")

        # Align Marketing ID 15 (Min 1, Max 2000) -> Max 500, Dealer 2% (0.02)
        m15 = await db.get(BillingSlab, 15)
        if m15:
            m15.max_price = 500.0
            m15.dealer_percentage = 0.02
            m15.customer_percentage = None
            m15.gst_type = "STANDARD_18"
            m15.sac_hsn_code = "998314"
            print("  Updated Marketing ID 15 -> Min 1, Max 500, Dealer 2%")

        # Align Logistics ID 16 (Min 1, Max 2000) -> Max 500, Dealer 10% (0.10), Customer 9% (0.09)
        l16 = await db.get(BillingSlab, 16)
        if l16:
            l16.max_price = 500.0
            l16.dealer_percentage = 0.10
            l16.customer_percentage = 0.09
            l16.gst_type = "STANDARD_18"
            l16.sac_hsn_code = "996812"
            print("  Updated Logistics ID 16 -> Min 1, Max 500, Dealer 10%, Customer 9%")

        await db.commit()
        print("[PASS] Pre-existing slabs aligned to confirmed business matrix!")

if __name__ == "__main__":
    asyncio.run(align_slabs())
