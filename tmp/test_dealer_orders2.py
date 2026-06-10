import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from core.database import SessionLocal
from models.user import User
from models.dealer import Dealer
from routers.dealers import get_dealer_orders

async def main():
    async with SessionLocal() as db:
        res = await db.execute(select(Dealer).limit(1))
        dealer = res.scalar_one_or_none()
        if not dealer:
            print("No dealers found")
            return
            
        print(f"Using dealer {dealer.id} with user_id {dealer.user_id}")
        res_user = await db.execute(select(User).where(User.id == dealer.user_id))
        user = res_user.scalar_one_or_none()
        if not user:
            print("User not found")
            return
            
        res2 = await get_dealer_orders(page=1, limit=10, type="new", status=None, search=None, start_date=None, end_date=None, hub_id=None, current_user=user, db=db)
        print("Total:", res2['total'])
        print("Orders fetched:", len(res2['items']))
        for i, order in enumerate(res2['items']):
            print(f"Order {i}: items count =", len(order.items))
            for item in order.items:
                print("Item prod name", item.product_name)

if __name__ == "__main__":
    asyncio.run(main())
