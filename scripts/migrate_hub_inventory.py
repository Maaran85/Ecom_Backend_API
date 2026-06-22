import asyncio
import os
import sys

# Add parent directory to path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import SessionLocal, engine, Base
from models.dealer import Dealer
from models.hub import DeliveryHub
from models.product import Product
from models.inventory import ProductInventory

async def migrate_data():
    print("Starting Data Migration for Hub Inventory...")

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database schema synchronized.")

    async with SessionLocal() as session:
        # 1. Create Default Hubs for Dealers without them
        print("\n--- Phase 1: Migrating Dealers ---")
        
        # Pre-fetch valid countries and states to avoid IntegrityError
        from sqlalchemy import text
        try:
            valid_countries = await session.execute(text("SELECT id FROM countries"))
            valid_countries = {row[0] for row in valid_countries}
        except Exception:
            valid_countries = set()
            
        try:
            valid_states = await session.execute(text("SELECT id FROM states"))
            valid_states = {row[0] for row in valid_states}
        except Exception:
            valid_states = set()

        result = await session.execute(select(Dealer))
        dealers = result.scalars().all()
        
        hub_count = 0
        for dealer in dealers:
            # Check if dealer already has a hub
            hub_result = await session.execute(
                select(DeliveryHub).where(DeliveryHub.dealer_id == dealer.id)
            )
            existing_hub = hub_result.scalars().first()
            
            if not existing_hub:
                print(f"Creating Primary Warehouse for Dealer ID {dealer.id}")
                safe_country_id = dealer.country_id if dealer.country_id in valid_countries else None
                safe_state_id = dealer.state_id if dealer.state_id in valid_states else None

                default_hub = DeliveryHub(
                    dealer_id=dealer.id,
                    name="Primary Warehouse",
                    address=dealer.business_address or "Head Office",
                    city=dealer.city,
                    state=dealer.state,
                    state_id=safe_state_id,
                    country_id=safe_country_id,
                    pincode=dealer.pincode,
                    lat_long=dealer.lat_long,
                    phone=dealer.business_phone,
                    is_active=True,
                    is_showroom=False,
                    hub_type="Warehouse"
                )
                session.add(default_hub)
                hub_count += 1
                
        if hub_count > 0:
            await session.commit()
            print(f"Created {hub_count} new Default Hubs.")
        else:
            print("All dealers already have at least one hub.")

        # 2. Migrate Product Stock to ProductInventory
        print("\n--- Phase 2: Migrating Product Stock ---")
        prod_result = await session.execute(select(Product))
        products = prod_result.scalars().all()
        
        inventory_count = 0
        for product in products:
            # Check if inventory already exists
            inv_result = await session.execute(
                select(ProductInventory).where(ProductInventory.product_id == product.id)
            )
            existing_inv = inv_result.scalars().first()
            
            if not existing_inv:
                # Find the primary hub for this product's dealer
                hub_result = await session.execute(
                    select(DeliveryHub)
                    .where(DeliveryHub.dealer_id == product.dealer_id)
                    .order_by(DeliveryHub.id.asc())
                )
                primary_hub = hub_result.scalars().first()
                
                if primary_hub:
                    new_inv = ProductInventory(
                        hub_id=primary_hub.id,
                        product_id=product.id,
                        stock=product.stock
                    )
                    session.add(new_inv)
                    inventory_count += 1
                else:
                    print(f"WARNING: No hub found for Dealer {product.dealer_id} (Product {product.id})")
        
        if inventory_count > 0:
            await session.commit()
            print(f"Migrated stock for {inventory_count} products to ProductInventory.")
        else:
            print("All product stock is already tracked in ProductInventory.")

        print("\nMigration Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(migrate_data())
