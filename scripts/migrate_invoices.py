import asyncio
import sys
import os
from dotenv import load_dotenv

# Load .env file BEFORE any core imports
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

# Add the current directory to the Python path
sys.path.append(os.getcwd())

from core.database import SessionLocal
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import Order, OrderStatus
from core.order_status_logic import calculate_and_update_order_status

async def migrate_missing_invoices():
    print("Starting migration: Generating missing tax invoice numbers...")
    async with SessionLocal() as db:
        # Find all orders in status ORDER_PLACED onward that don't have an invoice number
        result = await db.execute(
            select(Order).where(
                Order.tax_invoice_no.is_(None),
                Order.status.in_([
                    OrderStatus.ORDER_PLACED,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PROCESSING,
                    OrderStatus.PACKAGING,
                    OrderStatus.PACKED,
                    OrderStatus.SHIPPED,
                    OrderStatus.DISPATCHED,
                    OrderStatus.OUT_FOR_DELIVERY,
                    OrderStatus.DELIVERED
                ])
            )
        )
        orders = result.scalars().all()
        
        print(f"Found {len(orders)} orders missing invoice numbers.")
        
        count = 0
        for order in orders:
            try:
                # This will generate the invoice number based on our new logic in order_status_logic.py
                await calculate_and_update_order_status(db, order.id)
                count += 1
            except Exception as e:
                print(f"Failed to process order {order.id}: {e}")
        
        await db.commit()
        print(f"Successfully updated {count} orders with tax invoice numbers.")

if __name__ == "__main__":
    asyncio.run(migrate_missing_invoices())
