import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

engine = create_async_engine("postgresql+asyncpg://postgres:admin@localhost:5432/onlineshopappdb")

async def fix_enums():
    # Use autocommit connection to alter types
    autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    async with autocommit_engine.connect() as conn:
        new_ticket_types = [
            "ORDER_MANAGEMENT", "order_management",
            "PAYMENT_REFUNDS", "payment_refunds",
            "RETURNS_EXCHANGES", "returns_exchanges",
            "PRODUCT_INQUIRIES", "product_inquiries",
            "ACCOUNT_PROFILE", "account_profile",
            "TECHNICAL_ISSUES", "technical_issues",
            "OTHERS", "others"
        ]
        
        for val in new_ticket_types:
            try:
                await conn.execute(text(f"ALTER TYPE tickettype ADD VALUE IF NOT EXISTS '{val}';"))
                print(f"Added {val} to tickettype")
            except Exception as e:
                pass
                
    # Use autocommit connection to update rows so one failure doesn't abort everything
    async with autocommit_engine.connect() as conn:
        mapping = {
            "ORDER_ISSUE": "ORDER_MANAGEMENT",
            "REFUND": "PAYMENT_REFUNDS",
            "PRODUCT_QUERY": "PRODUCT_INQUIRIES",
            "TECHNICAL": "TECHNICAL_ISSUES",
            "COMPLAINT": "OTHERS",
            "OTHER": "OTHERS",
        }
        
        for old_val, new_val in mapping.items():
            try:
                res = await conn.execute(text(f"UPDATE support_tickets SET ticket_type = '{new_val}' WHERE ticket_type = '{old_val}';"))
                print(f"Updated {res.rowcount} rows from {old_val} to {new_val}")
            except Exception as e:
                print(f"Error updating {old_val}: {e}")

if __name__ == "__main__":
    asyncio.run(fix_enums())
