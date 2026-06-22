import asyncio
from core.database import SessionLocal
from models import OrderReturn, OrderItem, ReturnStatus
from sqlalchemy import select

async def run():
    async with SessionLocal() as db:
        res = await db.execute(select(OrderReturn).where(OrderReturn.order_id == 50))
        ret = res.scalar_one_or_none()
        
        if ret:
            ret.status = ReturnStatus.REQUESTED
            
            # Sync hub_id and logistics_partner_id from OrderItem
            item_res = await db.execute(select(OrderItem).where(OrderItem.id == ret.order_item_id))
            item = item_res.scalar_one_or_none()
            if item:
                ret.hub_id = item.hub_id
                ret.logistics_partner_id = item.logistics_partner_id
                
            print(f'Updated existing return to REQUESTED, hub_id={ret.hub_id}, logistics_partner_id={ret.logistics_partner_id}')
            await db.commit()
        else:
            print('No return found for order 50, let me check OrderItem')
            items_res = await db.execute(select(OrderItem).where(OrderItem.order_id == 50))
            items = items_res.scalars().all()
            if not items:
                print('No order items found for order 50')
                return
            
            # create a return for the first item
            first_item = items[0]
            new_ret = OrderReturn(
                order_id=50,
                order_item_id=first_item.id,
                customer_id=1,  # dummy or fetch from order
                reason="Test",
                is_exchange=False,
                status=ReturnStatus.REQUESTED,
                hub_id=first_item.hub_id,
                logistics_partner_id=first_item.logistics_partner_id
            )
            db.add(new_ret)
            await db.commit()
            print('Created new return for order 50 with status REQUESTED')

if __name__ == "__main__":
    asyncio.run(run())
