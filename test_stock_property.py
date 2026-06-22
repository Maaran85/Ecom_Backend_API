import asyncio
from core.database import SessionLocal
from sqlalchemy import select
from models.product import Product
from models.inventory import ProductInventory
from sqlalchemy.orm import column_property, aliased
from sqlalchemy import func

# Dynamically add the column_property
ChildProduct = aliased(Product)
Product.stock = column_property(
    select(func.coalesce(func.sum(ProductInventory.stock), 0)).where(
        (ProductInventory.product_id == Product.id) | 
        ProductInventory.product_id.in_(
            select(ChildProduct.id).where(ChildProduct.parent_product_id == Product.id).correlate(Product)
        )
    ).correlate(Product).scalar_subquery()
)

async def test():
    async with SessionLocal() as db:
        # Just compile a query to see if it works
        query = select(Product.id, Product.stock).limit(5)
        print("SQL Query:\n", query)
        try:
            res = await db.execute(query)
            print("Results:", res.fetchall())
        except Exception as e:
            print("Error executing query:", e)

if __name__ == "__main__":
    asyncio.run(test())
