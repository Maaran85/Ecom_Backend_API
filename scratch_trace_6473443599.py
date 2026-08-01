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
from sqlalchemy import select
from models.cart import Order as OrderModel, OrderItem as OrderItemModel
from models import OrderInvoice as OrderInvoiceModel
from models.product import Product as ProductModel
from models.dealer import Dealer as DealerModel
from models.address import Address as AddressModel

TestSession = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    try:
        async with TestSession() as db:
            res = await db.execute(
                select(OrderModel)
                .where(OrderModel.order_number == '6473443599')
                .options(
                    selectinload(OrderModel.items).joinedload(OrderItemModel.product).joinedload(ProductModel.dealer).selectinload(DealerModel.state_rel),
                    selectinload(OrderModel.shipping_address).selectinload(AddressModel.state_rel),
                    selectinload(OrderModel.invoices)
                )
            )
            order = res.scalars().first()
            print('=== STEP 1: LOAD ORDER 6473443599 ===')
            if not order:
                print('Order 6473443599 not found!')
                return

            print('  Order ID:', order.id)
            print('  Order Number:', order.order_number)
            item = order.items[0] if order.items else None
            prod = item.product if item else None
            dealer = prod.dealer if prod else None
            addr = order.shipping_address

            print('  Dealer ID:', dealer.id if dealer else None)
            print('  Customer ID:', order.customer_id)
            print('  Shipping Address ID:', order.shipping_address_id)

            print('\n=== STEP 2: DEALER DETAILS ===')
            if dealer:
                print('  Dealer Name:', dealer.business_name)
                print('  Dealer GSTIN:', dealer.gst_number)
                print('  Dealer Address:', dealer.business_address, dealer.city)
                print('  Dealer State:', dealer.state_rel.name if dealer.state_rel else None)
                print('  Dealer State Code:', dealer.state_code)

            print('\n=== STEP 3: SHIPPING ADDRESS ===')
            if addr:
                print('  Shipping Address:', addr.address_line1, addr.city)
                print('  State:', addr.state_rel.name if addr.state_rel else None)
                print('  State Code:', addr.state_rel.state_code if addr.state_rel else None)
                print('  Pincode:', addr.pincode)

            print('\n=== STEP 4: GST DECISION AT ORDER CREATION ===')
            print('  is_inter_state stored on order:', order.is_inter_state)
            print('  Order cgst_amount:', order.cgst_amount)
            print('  Order sgst_amount:', order.sgst_amount)
            print('  Order igst_amount:', order.igst_amount)
            print('  Order total_tax:', order.tax_amount)

            print('\n=== STEP 5: ORDERITEM DATABASE SNAPSHOT ===')
            if item:
                print('  cgst_rate:', item.cgst_rate)
                print('  cgst_amount:', item.cgst_amount)
                print('  sgst_rate:', item.sgst_rate)
                print('  sgst_amount:', item.sgst_amount)
                print('  igst_rate:', item.igst_rate)
                print('  igst_amount:', item.igst_amount)
                print('  tax_amount:', item.tax_amount)

            print('\n=== STEP 6: INVOICE RECORD ===')
            if order.invoices:
                inv = order.invoices[0]
                print('  Invoice ID:', inv.id)
                print('  Invoice Number:', inv.invoice_number)
                print('  Invoice Total Amount:', inv.total_amount)
                print('  Invoice Tax Amount:', inv.tax_amount)
    except Exception:
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
