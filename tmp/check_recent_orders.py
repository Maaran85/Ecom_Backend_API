import asyncio
from sqlalchemy import select, join
from core.database import SessionLocal, engine
from models.cart import Order, OrderItem, OrderStatus
from models.product import Product
from models.dealer import Dealer

async def check():
    async with engine.connect() as conn:
        # Check all orders
        res = await conn.execute(select(Order.id, Order.order_number, Order.status).order_by(Order.id.desc()).limit(5))
        orders = res.fetchall()
        print(f"Latest 5 orders: {orders}")
        
        # Check items for the latest order
        if orders:
            oid = orders[0][0]
            res = await conn.execute(
                select(OrderItem.id, OrderItem.product_id, Product.dealer_id)
                .join(Product, OrderItem.product_id == Product.id)
                .where(OrderItem.order_id == oid)
            )
            items = res.fetchall()
            print(f"Items for latest order {oid}: {items}")
            
            if items:
                did = items[0][2]
                print(f"Dealer ID of first item: {did}")
                
                # Check dealer user
                res = await conn.execute(select(Dealer.user_id).where(Dealer.id == did))
                uid = res.scalar()
                print(f"Dealer user ID: {uid}")

if __name__ == "__main__":
    asyncio.run(check())
