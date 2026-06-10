import asyncio
from sqlalchemy import select
from core.database import SessionLocal, engine
from models.cart import Order, OrderItem
from models.product import Product

async def check():
    async with engine.connect() as conn:
        res = await conn.execute(
            select(Order.id, OrderItem.id, Product.name, Product.dealer_id)
            .join(OrderItem, Order.id == OrderItem.order_id)
            .join(Product, OrderItem.product_id == Product.id)
            .order_by(Order.id.desc())
            .limit(10)
        )
        print("Recent orders -> items -> dealers:")
        for r in res.fetchall():
            print(r)

if __name__ == "__main__":
    asyncio.run(check())
