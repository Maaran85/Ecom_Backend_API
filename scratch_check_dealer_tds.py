import asyncio
import sys
import os
from uuid import UUID

sys.path.insert(0, os.getcwd())

from core.database import SessionLocal
from models.product import Product
from models.dealer import Dealer
from services.tds_resolver import resolve_tds_rate, applicable_rate_and_exemption
from services.configuration_service import get_active_tds_config_required

async def main():
    async with SessionLocal() as db:
        prod = await db.get(Product, UUID("e28f3e9d-4dae-48d2-9aba-e6a30df2781a"))
        dealer = await db.get(Dealer, prod.dealer_id) if prod else None
        print(f"Product: {prod.name}, dealer_id: {prod.dealer_id}")
        if dealer:
            print(f"Dealer: {dealer.business_name}, org_type: {dealer.organization_type}, pan: {dealer.pan_number}")
            tds_cfg = await get_active_tds_config_required(db, dealer.organization_type)
            rate, ex = applicable_rate_and_exemption(tds_cfg, bool(dealer.pan_number))
            print(f"TDS config: rate={rate}, exemption={ex}")

if __name__ == "__main__":
    asyncio.run(main())
