import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())

from core.database import SessionLocal
from services.tax_service import TaxService

PRODUCT_ID = "ce3e0999-9c62-4bd4-8727-24b393e4ca3f"  # GST Verification Test Product (tax_category_id=4, 18%)


async def main():
    async with SessionLocal() as db:
        print("=" * 70)
        print("TEST A: correct kwargs (buyer_state=..., seller_state=...)")
        print("=" * 70)
        try:
            r = await TaxService.calculate_item_tax(
                db=db, base_price=1180.0, qty=1, product_id=PRODUCT_ID,
                buyer_state="TN", seller_state="TN"
            )
            print("OK ->", r)
        except Exception as e:
            print("ERROR ->", type(e).__name__, e)

        print()
        print("=" * 70)
        print("TEST B: working-tree kwargs (buyer_state_id=..., seller_state_id=...)")
        print("=" * 70)
        try:
            r = await TaxService.calculate_item_tax(
                db=db, base_price=1180.0, qty=1, product_id=PRODUCT_ID,
                buyer_state_id=138, seller_state_id=138
            )
            print("OK ->", r)
        except Exception as e:
            print("ERROR ->", type(e).__name__, e)


if __name__ == "__main__":
    asyncio.run(main())
