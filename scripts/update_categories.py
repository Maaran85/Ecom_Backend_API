import asyncio
import sys
import os

sys.path.append(os.getcwd())
from core.database import SessionLocal
from models.product import Category, Product, CategoryAttribute
from models.tax import TaxRule
from sqlalchemy import select, delete, update

async def get_all_children_ids(db, parent_id):
    result = await db.execute(select(Category).where(Category.parent_id == parent_id))
    children = result.scalars().all()
    all_ids = []
    for c in children:
        all_ids.extend(await get_all_children_ids(db, c.id))
        all_ids.append(c.id)
    return all_ids

async def get_or_create_uncategorized(db):
    result = await db.execute(select(Category).where(Category.name == "Uncategorized").where(Category.parent_id == None))
    cat = result.scalars().first()
    if not cat:
        cat = Category(name="Uncategorized", parent_id=None)
        db.add(cat)
        await db.flush() # to get cat.id
    return cat.id

async def delete_category_recursively(db, cat_id, uncategorized_id, safe_tax_rule_id):
    children_ids = await get_all_children_ids(db, cat_id)
    all_cats_to_delete = children_ids + [cat_id]
    
    for cid in all_cats_to_delete:
        # Move products to uncategorized
        await db.execute(update(Product).where(Product.category_id == cid).values(category_id=uncategorized_id))
        
        # Unlink tax rules
        tr_result = await db.execute(select(TaxRule.id).where(TaxRule.category_id == cid))
        tax_rule_ids = tr_result.scalars().all()
        if tax_rule_ids:
            # Any product using these tax rules gets a safe fallback
            await db.execute(update(Product).where(Product.tax_rule_id.in_(tax_rule_ids)).values(tax_rule_id=safe_tax_rule_id))
            
        # Delete category attributes
        await db.execute(delete(CategoryAttribute).where(CategoryAttribute.category_id == cid))
        
        # Delete category
        await db.execute(delete(Category).where(Category.id == cid))

async def main():
    async with SessionLocal() as db:
        uncategorized_id = await get_or_create_uncategorized(db)
        
        # Get a safe tax rule that is global
        tr_res = await db.execute(select(TaxRule.id).where(TaxRule.category_id == None))
        safe_tax_rule_id = tr_res.scalars().first()
        if not safe_tax_rule_id:
            safe_tax_rule_id = 1 # Fallback, hope it exists

        # 1. Rename categories
        renames = {
            "Men": "Men Fashion",
            "Women": "Women Fashion",
            "Mobiles": "Mobile and Computer",
            "Beauty & Toys": "Toys"
        }
        for old_name, new_name in renames.items():
            result = await db.execute(select(Category).where(Category.name == old_name).where(Category.parent_id == None))
            cat = result.scalars().first()
            if cat:
                cat.name = new_name
                print(f"Renamed {old_name} to {new_name}")

        # 2. Delete categories recursively
        to_delete = [
            ("Fashion", None),
            ("Home & Living", None)
        ]
        
        # Find Kids category to get Brands under it
        result = await db.execute(select(Category).where(Category.name == "Kids").where(Category.parent_id == None))
        kids_cat = result.scalars().first()
        if kids_cat:
            to_delete.append(("Brands", kids_cat.id))
            
        for name, parent_id in to_delete:
            query = select(Category).where(Category.name == name)
            if parent_id is not None:
                query = query.where(Category.parent_id == parent_id)
            else:
                query = query.where(Category.parent_id == None)
                
            result = await db.execute(query)
            cat = result.scalars().first()
            
            if cat:
                print(f"Deleting {name} ({cat.id}) and moving its products to Uncategorized")
                await delete_category_recursively(db, cat.id, uncategorized_id, safe_tax_rule_id)

        # 3. Add subcategories
        targets = {
            "Electronics": ["Projectors", "Lightings"],
            "Kids": ["Automobiles", "Tools"],
            "Home & Furniture": ["Bathroom", "Travel Kits"]
        }
        
        for p_name, subcats in targets.items():
            result = await db.execute(select(Category).where(Category.name == p_name).where(Category.parent_id == None))
            parent_cat = result.scalars().first()
            if parent_cat:
                for sub_name in subcats:
                    existing = await db.execute(select(Category).where(Category.name == sub_name).where(Category.parent_id == parent_cat.id))
                    if not existing.scalars().first():
                        new_cat = Category(name=sub_name, parent_id=parent_cat.id)
                        db.add(new_cat)
                        print(f"Added {sub_name} under {p_name}")

        await db.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
