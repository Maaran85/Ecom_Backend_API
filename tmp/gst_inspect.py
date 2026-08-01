import asyncio
import sys
import os
sys.path.insert(0, os.getcwd())

from sqlalchemy import select, text
from core.database import SessionLocal
from models.location import State
from models.dealer import Dealer
from models.tax import TaxCategory, TaxRule
from models.product import Product, Category
from models.customer_user import CustomerUser
from models.address import Address


async def main():
    async with SessionLocal() as db:
        print("=" * 100)
        print("STATES")
        res = await db.execute(select(State).order_by(State.name))
        for s in res.scalars().all():
            print(f"  id={s.id} name={s.name!r} code={s.state_code!r} active={s.is_active}")

        print("=" * 100)
        print("DEALERS")
        res = await db.execute(select(Dealer).order_by(Dealer.created_at.desc()).limit(20))
        for d in res.scalars().all():
            st = await db.get(State, d.state_id) if d.state_id else None
            print(f"  id={d.id} user_id={d.user_id} name={d.business_name!r} "
                  f"state_id={d.state_id} state={st.name if st else None} "
                  f"access={d.access_status} active={d.is_active} approved={d.is_approved}")

        print("=" * 100)
        print("TAX CATEGORIES")
        res = await db.execute(select(TaxCategory).order_by(TaxCategory.id))
        for tc in res.scalars().all():
            print(f"  id={tc.id} name={tc.name!r} cgst={tc.cgst_rate} sgst={tc.sgst_rate} "
                  f"igst={tc.igst_rate} active={tc.is_active} type={tc.tax_type}")

        print("=" * 100)
        print("TAX RULES")
        res = await db.execute(select(TaxRule).order_by(TaxRule.id))
        for tr in res.scalars().all():
            print(f"  id={tr.id} name={tr.name!r} category_id={tr.category_id} product_id={tr.product_id} "
                  f"tax_category_id={tr.tax_category_id} priority={tr.priority} state_code={tr.state_code} "
                  f"active={tr.is_active}")

        print("=" * 100)
        print("CATEGORIES")
        res = await db.execute(select(Category).order_by(Category.id).limit(30))
        for c in res.scalars().all():
            print(f"  id={c.id} name={c.name!r} parent_id={c.parent_id} active={c.is_active}")

        print("=" * 100)
        print("PRODUCTS (approved, not deleted)")
        res = await db.execute(
            select(Product).where(Product.is_approved == True, Product.is_deleted == False).limit(40)
        )
        for p in res.scalars().all():
            tc = await db.get(TaxCategory, p.tax_category_id) if p.tax_category_id else None
            print(f"  id={p.id} name={p.name!r} price={p.selling_price} mrp={p.mrp} "
                  f"dealer_id={p.dealer_id} cat_id={p.category_id} hsn={p.hsn_code!r} "
                  f"tax_rule_id={p.tax_rule_id} tax_category_id={p.tax_category_id} "
                  f"tax_cat={tc.name if tc else None} stock={p.stock}")

        print("=" * 100)
        print("CUSTOMERS")
        res = await db.execute(select(CustomerUser).order_by(CustomerUser.id).limit(20))
        for c in res.scalars().all():
            print(f"  id={c.id} name={c.full_name!r} phone={c.phone!r} email={c.email!r} active={c.is_active}")

        print("=" * 100)
        print("ADDRESSES")
        res = await db.execute(select(Address).order_by(Address.id).limit(30))
        for a in res.scalars().all():
            st = await db.get(State, a.state_id) if a.state_id else None
            print(f"  id={a.id} customer_id={a.customer_id} city={a.city!r} "
                  f"state_id={a.state_id} state={st.name if st else None} pincode={a.pincode!r}")


if __name__ == "__main__":
    asyncio.run(main())
