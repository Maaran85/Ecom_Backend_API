import sys
import asyncio
from sqlalchemy.future import select
from core.database import SessionLocal
from models.partner import Partner
from datetime import datetime, timedelta, timezone

async def seed_partner():
    async with SessionLocal() as db:
        try:
            # Check if any partner exists
            result = await db.execute(select(Partner))
            existing = result.scalars().first()
            if existing:
                print("Partner already exists. Skipping seed.")
                return

            partner = Partner(
                partner_name="Myntra Corp",
                support_email="support@myntra.com",
                support_phone="+91-1234567890",
                address="123 Fashion Street, Tech Park, Bangalore",
                tax_id="GSTIN123456789",
                license_key="MYNTRA-ENTERPRISE-2026",
                plan_type="Enterprise",
                valid_until=datetime.now(timezone.utc) + timedelta(days=365*5),
                max_dealers=1000,
                default_currency="INR",
                timezone="Asia/Kolkata",
                is_active=True
            )
            db.add(partner)
            await db.commit()
            await db.refresh(partner)
            print(f"Successfully seeded partner: {partner.partner_name}")
        except Exception as e:
            print(f"Error seeding partner: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(seed_partner())
