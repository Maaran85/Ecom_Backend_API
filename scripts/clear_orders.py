import asyncio
from sqlalchemy import text
from core.database import SessionLocal

async def clear_data():
    async with SessionLocal() as session:
        try:
            print("Cleaning up database tables...")
            
            # Use raw SQL for simplicity and speed in a cleanup task
            # Order of deletion matters due to foreign key constraints
            tables = [
                "dealer_remittances",
                "logistics_remittances",
                "order_returns",
                "payment_webhooks",
                "payments",
                "rider_earnings",  # Link to order_items
                "order_items",
                "orders",
                "audit_logs" # Cleanup logs that might reference orders
            ]
            
            for table in tables:
                print(f"Clearing table: {table}")
                await session.execute(text(f"DELETE FROM {table}"))
            
            await session.commit()
            print("Successfully cleared all orders, remittances, earnings and related data.")
        except Exception as e:
            print(f"Error clearing data: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(clear_data())
