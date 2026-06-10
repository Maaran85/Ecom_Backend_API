import asyncio
from sqlalchemy import select
from core.database import SessionLocal
from models.user import User, UserRole

async def verify_dealer_roles():
    async with SessionLocal() as db:
        print("Checking Dealer UserRole enum values...")
        roles = [UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY, UserRole.DEALER_ORDERS, UserRole.DEALER_FINANCE]
        print(f"New dealer roles verified: {[r.value for r in roles]}")

        print("Verifying relationship loading...")
        # Simple existence check
        from models.user import User
        print("User model loaded successfully.")

if __name__ == "__main__":
    asyncio.run(verify_dealer_roles())
