import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete
from core.database import SessionLocal
from models.order_return import OrderReturn
from models import OrderItem, Order
from models.payment import Payment

async def main():
    async with SessionLocal() as db:
        try:
            # Delete order returns first
            await db.execute(delete(OrderReturn))
            # Payments are usually linked to orders
            await db.execute(delete(Payment))
            # Delete order items
            await db.execute(delete(OrderItem))
            # Delete orders
            await db.execute(delete(Order))
            
            await db.commit()
            print("Successfully deleted all orders, order items, returns and payments from the database.")
        except Exception as e:
            await db.rollback()
            print("Error deleting orders:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
