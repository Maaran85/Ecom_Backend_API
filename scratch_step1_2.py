import os, sys, traceback
backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)
from dotenv import load_dotenv
load_dotenv()
import asyncio
from core.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload, joinedload
from sqlalchemy import select, text
from models.cart import Order as OrderModel, OrderItem as OrderItemModel
from models.settlement import Settlement, SettlementItem
from models.settlement_configuration import SettlementConfiguration
from models.product import Product as ProductModel
from models.dealer import Dealer as DealerModel

TestSession = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def check_order_and_config():
    try:
        async with TestSession() as db:
            # Step 1: Verify Order
            res_o = await db.execute(
                select(OrderModel)
                .where(OrderModel.order_number == '0679582988')
                .options(
                    selectinload(OrderModel.items).joinedload(OrderItemModel.product).joinedload(ProductModel.dealer)
                )
            )
            order = res_o.scalars().first()

            print('=== STEP 1: VERIFY ORDER 0679582988 ===')
            if not order:
                print('Order 0679582988 not found!')
                return

            print('  Order ID:', order.id)
            print('  Order Number:', order.order_number)
            prod = order.items[0].product if order.items else None
            print('  Product Name:', prod.name if prod else None)
            dealer = prod.dealer if prod else None
            print('  Dealer Name:', dealer.business_name if dealer else None)
            print('  Customer ID:', order.customer_id)
            print('  Status:', order.status)
            print('  created_at:', order.created_at)
            print('  delivered_at:', order.delivered_at)

            # Check existing settlements for this order
            res_si = await db.execute(select(SettlementItem).where(SettlementItem.order_id == order.id))
            settlement_item = res_si.scalars().first()
            print('  Settlement Item ID:', settlement_item.id if settlement_item else 'None')
            print('  Has this order already been settled?:', 'YES' if settlement_item else 'NO')

            # Step 2: Verify Settlement Configuration
            res_cfg = await db.execute(select(SettlementConfiguration).limit(1))
            cfg = res_cfg.scalars().first()
            print('\n=== STEP 2: SETTLEMENT CONFIGURATION ===')
            if cfg:
                print('  return_window_days:', cfg.return_window_days)
                print('  is_daily_auto_enabled:', cfg.is_daily_auto_enabled)
            else:
                print('  No settlement configuration found!')
    except Exception:
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(check_order_and_config())
