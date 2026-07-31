import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, and_, cast, String, text
from sqlalchemy.orm import selectinload, aliased, joinedload
from typing import List, Optional
import csv
import codecs
import io
import json

from core.database import get_db

gst_logger = logging.getLogger("gst")
from schemas.product import (
    Product, ProductCreate, ProductUpdate, Brand, BrandCreate, BrandUpdate,
    Category, CategoryCreate, CategoryUpdate, CategoryAttribute, CategoryAttributeCreate, CategoryAttributeUpdate
)
from models.product import Product as ProductModel, Category as CategoryModel, CategoryAttribute as CategoryAttributeModel, Brand as BrandModel, SubcategoryBrand
from models.search_history import SearchHistory as SearchHistoryModel
from models.user import UserRole
from models.dealer import Dealer as DealerModel
from models.partner import Partner as PartnerModel
from models.inventory import ProductInventory as ProductInventoryModel
from schemas.search_history import SearchHistory
from models.cart import OrderItem as OrderItemModel
from core.permissions import (
    require_admin, get_current_active_user, 
    get_current_user_optional, require_dealer_or_admin
)
from models.customer_user import CustomerUser
from services.file_upload import FileUploadService as UploadService
from services.recommendation import RecommendationService
from models.user import User

router = APIRouter()

# Category endpoints
@router.post("/categories", response_model=Category, tags=["categories"])
async def create_category(
    category_in: CategoryCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new category"""
    try:
        db_category = CategoryModel(**category_in.model_dump())
        db.add(db_category)
        await db.flush()  # To get the assigned ID without expiring the object
        category_id = db_category.id
        await db.commit()
        
        result = await db.execute(
            select(CategoryModel)
            .options(selectinload(CategoryModel.attributes))
            .where(CategoryModel.id == category_id)
        )
        return result.scalar_one()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories", response_model=List[Category], tags=["categories"])
async def get_categories(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get all categories with pagination"""
    query = select(CategoryModel).where(CategoryModel.is_deleted == False)
    
    # Check if we should filter out inactive categories
    is_admin = False
    if current_user and current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        is_admin = True
        
    if not is_admin:
        query = query.where(CategoryModel.is_active == True)
        
    result = await db.execute(query.offset(skip).limit(limit).options(selectinload(CategoryModel.attributes)))
    categories = result.scalars().all()
    return categories

@router.put("/categories/{category_id}", response_model=Category, tags=["categories"])
async def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a category (admin only)"""
    result = await db.execute(select(CategoryModel).options(selectinload(CategoryModel.attributes)).where(CategoryModel.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    update_data = category_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)
    
    await db.commit()
    
    # Re-fetch to ensure attributes are eagerly loaded for Pydantic
    fresh_result = await db.execute(
        select(CategoryModel)
        .options(selectinload(CategoryModel.attributes))
        .where(CategoryModel.id == category_id)
    )
    return fresh_result.scalar_one()

@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["categories"])
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a category (admin only)"""
    # Verify category exists
    result = await db.execute(select(CategoryModel).where(CategoryModel.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Helper function to get all subcategories recursively
    async def get_all_subcategories(db_session, cat_id):
        sub_res = await db_session.execute(select(CategoryModel.id).where(CategoryModel.parent_id == cat_id))
        sub_ids = sub_res.scalars().all()
        all_ids = list(sub_ids)
        for sid in sub_ids:
            all_ids.extend(await get_all_subcategories(db_session, sid))
        return all_ids

    category_ids_to_delete = [category_id] + await get_all_subcategories(db, category_id)

    # Check if there are any products in these categories
    prod_res = await db.execute(
        select(ProductModel.id).where(ProductModel.category_id.in_(category_ids_to_delete))
    )
    product_ids_to_delete = prod_res.scalars().all()

    if not product_ids_to_delete:
        # 1. Hard delete Categories (no products exist)
        from sqlalchemy import delete
        
        # Delete attributes first to avoid foreign key constraints
        await db.execute(delete(CategoryAttributeModel).where(CategoryAttributeModel.category_id.in_(category_ids_to_delete)))
        
        # Then delete categories
        await db.execute(delete(CategoryModel).where(CategoryModel.id.in_(category_ids_to_delete)))
    else:
        # 1. Soft delete Categories
        from sqlalchemy import update
        await db.execute(
            update(CategoryModel)
            .where(CategoryModel.id.in_(category_ids_to_delete))
            .values(is_deleted=True, is_active=False)
        )

        # 2. Soft delete Products
        await db.execute(
            update(ProductModel)
            .where(ProductModel.id.in_(product_ids_to_delete))
            .values(is_deleted=True, is_approved=False)
        )

    await db.commit()
    return None

@router.get("/categories/{category_id}/products", response_model=List[Product], tags=["categories"])
async def get_category_products(
    category_id: int,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get products in a category with filters"""
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.category_id == category_id,
        ProductModel.is_deleted == False,
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    )
    
    # Price filters
    if min_price is not None:
        query = query.where(ProductModel.selling_price >= min_price)
    if max_price is not None:
        query = query.where(ProductModel.selling_price <= max_price)
    
    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.selling_price.asc() if sort_order == "asc" else ProductModel.selling_price.desc())
    elif sort_by == "rating":
        query = query.order_by(ProductModel.average_rating.desc())
    elif sort_by == "newest":
        query = query.order_by(ProductModel.created_at.desc())
    else:  # name
        query = query.order_by(ProductModel.name.asc())
    
    query = query.offset(skip).limit(limit).options(
        joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        joinedload(ProductModel.dealer),
        joinedload(ProductModel.brand),
        selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        selectinload(ProductModel.children).selectinload(ProductModel.children),
        selectinload(ProductModel.children).joinedload(ProductModel.brand)
    )
    result = await db.execute(query)
    products = result.scalars().all()
    
    return products

@router.post("/categories/{category_id}/attributes", response_model=CategoryAttribute, tags=["categories"])
async def create_category_attribute(
    category_id: int, 
    attribute_in: CategoryAttributeCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Add a mandatory or optional attribute to a category (admin only)"""
    # Verify category exists
    cat_result = await db.execute(select(CategoryModel).where(CategoryModel.id == category_id))
    if not cat_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Category not found")
        
    db_attribute = CategoryAttributeModel(**attribute_in.model_dump(), category_id=category_id)
    db.add(db_attribute)
    await db.commit()
    await db.refresh(db_attribute)
    return {
        "id": db_attribute.id,
        "category_id": db_attribute.category_id,
        "name": db_attribute.name,
        "is_mandatory": db_attribute.is_mandatory,
        "is_variant_key": db_attribute.is_variant_key,
        "datatype": db_attribute.datatype,
        "allowed_values": db_attribute.allowed_values,
        "unit": db_attribute.unit,
        "description": db_attribute.description,
        "is_filter": db_attribute.is_filter
    }

@router.put("/categories/{category_id}/attributes/{attribute_id}", response_model=CategoryAttribute, tags=["categories"])
async def update_category_attribute(
    category_id: int,
    attribute_id: int,
    attribute_in: CategoryAttributeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a category attribute (admin only)"""
    result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.id == attribute_id, CategoryAttributeModel.category_id == category_id)
    )
    db_attribute = result.scalar_one_or_none()
    if not db_attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    
    update_data = attribute_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_attribute, key, value)
    
    await db.commit()
    await db.refresh(db_attribute)
    return {
        "id": db_attribute.id,
        "category_id": db_attribute.category_id,
        "name": db_attribute.name,
        "is_mandatory": db_attribute.is_mandatory,
        "is_variant_key": db_attribute.is_variant_key,
        "datatype": db_attribute.datatype,
        "allowed_values": db_attribute.allowed_values,
        "unit": db_attribute.unit,
        "description": db_attribute.description,
        "is_filter": db_attribute.is_filter
    }

@router.delete("/categories/{category_id}/attributes/{attribute_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["categories"])
async def delete_category_attribute(
    category_id: int,
    attribute_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a category attribute (admin only)"""
    result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.id == attribute_id, CategoryAttributeModel.category_id == category_id)
    )
    db_attribute = result.scalar_one_or_none()
    if not db_attribute:
        raise HTTPException(status_code=404, detail="Attribute not found")
    
    await db.delete(db_attribute)
    await db.commit()
    return None

@router.get("/categories/{category_id}/attributes", response_model=List[CategoryAttribute], tags=["categories"])
async def get_category_attributes(category_id: int, db: AsyncSession = Depends(get_db)):
    """Get all required and optional attributes for a specific category (including inherited from parents and defined in children)"""
    
    # Fast, safe memory-level mapping
    res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id, CategoryModel.is_spec_group))
    all_cats = res.all()
    
    # Adjacency maps
    children_map = {}
    parent_map = {}
    spec_group_map = {}
    for cid, pid, is_sg in all_cats:
        if pid not in children_map:
            children_map[pid] = []
        children_map[pid].append(cid)
        parent_map[cid] = pid
        spec_group_map[cid] = is_sg
        
    # Upward (parents)
    related_ids = set()
    curr = category_id
    while curr is not None:
        related_ids.add(curr)
        # Add any spec groups attached to this parent
        for child_id in children_map.get(curr, []):
            if spec_group_map.get(child_id):
                related_ids.add(child_id)
        curr = parent_map.get(curr)

    # Downward (children)
    stack = [category_id]
    visited = set()
    while stack:
        curr = stack.pop()
        if curr in visited: continue
        visited.add(curr)
        related_ids.add(curr)
        for child_id in children_map.get(curr, []):
            stack.append(child_id)

    if not related_ids:
        return []

    # Get all attributes for gathered category IDs
    result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.category_id.in_(list(related_ids)))
    )
    
    attributes = result.scalars().all()
    
    # Deduplicate by attribute name
    merged = {}
    for attr in attributes:
        if attr.name not in merged:
            merged[attr.name] = CategoryAttributeModel(
                id=attr.id,
                category_id=attr.category_id,
                name=attr.name,
                is_mandatory=attr.is_mandatory,
                is_variant_key=attr.is_variant_key,
                datatype=attr.datatype,
                allowed_values=list(attr.allowed_values) if attr.allowed_values else [],
                unit=attr.unit,
                description=attr.description
            )
        else:
            if attr.allowed_values:
                existing = merged[attr.name].allowed_values
                for val in attr.allowed_values:
                    if val not in existing:
                        existing.append(val)
                merged[attr.name].allowed_values = existing

    return list(merged.values())


@router.get("/categories/{category_id}/spec-groups", tags=["categories"])
async def get_category_spec_groups(category_id: int, db: AsyncSession = Depends(get_db)):
    """
    Return attributes grouped by spec group.
    Returns a list of { group_name: str, attributes: [...] }.
    Attributes with no spec group fall under a 'General' group.
    """
    # Build adjacency maps
    res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id, CategoryModel.is_spec_group, CategoryModel.name))
    all_cats = res.all()

    children_map: dict = {}
    parent_map: dict = {}
    spec_group_map: dict = {}
    name_map: dict = {}
    for cid, pid, is_sg, cname in all_cats:
        children_map.setdefault(pid, []).append(cid)
        parent_map[cid] = pid
        spec_group_map[cid] = is_sg
        name_map[cid] = cname

    # Collect all relevant category IDs (same logic as existing endpoint)
    related_ids: set = set()
    curr = category_id
    while curr is not None:
        related_ids.add(curr)
        for child_id in children_map.get(curr, []):
            if spec_group_map.get(child_id):
                related_ids.add(child_id)
        curr = parent_map.get(curr)

    stack = [category_id]
    visited: set = set()
    while stack:
        curr = stack.pop()
        if curr in visited:
            continue
        visited.add(curr)
        related_ids.add(curr)
        for child_id in children_map.get(curr, []):
            stack.append(child_id)

    if not related_ids:
        return []

    # Fetch all attributes
    result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.category_id.in_(list(related_ids)))
        .order_by(CategoryAttributeModel.id)
    )
    attributes = result.scalars().all()

    # Identify which category IDs are spec groups
    spec_group_ids = {cid for cid in related_ids if spec_group_map.get(cid)}

    # Group attributes
    groups: dict = {}   # group_name -> list of attr dicts
    seen_names: set = set()

    for attr in attributes:
        if attr.name in seen_names:
            continue
        seen_names.add(attr.name)

        # Determine group name
        if attr.category_id in spec_group_ids:
            group_name = name_map.get(attr.category_id, "General")
        else:
            group_name = "General"

        if group_name not in groups:
            groups[group_name] = []

        groups[group_name].append({
            "id": attr.id,
            "name": attr.name,
            "category_id": attr.category_id,
            "is_mandatory": attr.is_mandatory,
            "is_variant_key": attr.is_variant_key,
            "datatype": attr.datatype,
            "allowed_values": list(attr.allowed_values) if attr.allowed_values else [],
            "unit": attr.unit,
            "description": attr.description,
        })

    # Build ordered result: General first, then alphabetical spec groups
    result_list = []
    if "General" in groups:
        result_list.append({"group_name": "General", "attributes": groups["General"]})
    for gname, attrs in sorted(groups.items()):
        if gname != "General":
            result_list.append({"group_name": gname, "attributes": attrs})

    return result_list


# Product endpoints
@router.post("/products", response_model=Product, tags=["products"])
async def create_product(
    product_in: ProductCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new product with mandatory attribute validation"""
    
    # Validate category exists
    cat_result = await db.execute(select(CategoryModel).where(CategoryModel.id == product_in.category_id))
    if not cat_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Category not found")

    # Fetch mandatory attributes (including from parents and their spec groups)
    start_id = product_in.subcategory_id if product_in.subcategory_id else product_in.category_id
    hierarchy = select(CategoryModel.id, CategoryModel.parent_id).where(CategoryModel.id == start_id).cte(name="hierarchy", recursive=True)
    alias = aliased(CategoryModel)
    hierarchy = hierarchy.union_all(
        select(alias.id, alias.parent_id).where(alias.id == hierarchy.c.parent_id)
    )
    
    spec_groups = select(CategoryModel.id).where(
        CategoryModel.parent_id.in_(select(hierarchy.c.id)),
        CategoryModel.is_spec_group == True
    )

    attr_result = await db.execute(
        select(CategoryAttributeModel)
        .where(
            or_(
                CategoryAttributeModel.category_id.in_(select(hierarchy.c.id)),
                CategoryAttributeModel.category_id.in_(spec_groups)
            )
        )
    )
    all_attributes = attr_result.scalars().all()
    required_attributes = [attr for attr in all_attributes if attr.is_mandatory]
    variant_attributes = [attr for attr in all_attributes if attr.is_variant_key]
    
    # Check if incoming product matches required attributes
    product_attributes = product_in.attributes or {}
    missing_attributes = []
    
    for req_attr in required_attributes:
        val = product_attributes.get(req_attr.name)
        if val is None or val == "":
            missing_attributes.append(req_attr.name)
            
    if missing_attributes:
        raise HTTPException(
            status_code=400, 
            detail=f"Missing mandatory attributes for this category: {', '.join(missing_attributes)}"
        )

    # Remove read-only or extra fields that are not columns in the Product model
    product_data = product_in.model_dump()
    product_data.pop("dealer_delivery_days", None)
    
    if product_data.get("sku") == "":
        product_data["sku"] = None
        
    variants_data = product_data.pop("variants", [])
    
    db_product = ProductModel(**product_data)
    
    # Automatically assign dealer_id if the user is a dealer
    if current_user.role == UserRole.DEALER:
        dealer_res = await db.execute(select(DealerModel).where(DealerModel.user_id == current_user.id))
        dealer = dealer_res.scalar_one_or_none()
        if dealer:
            if not dealer.is_active:
                raise HTTPException(status_code=403, detail="Your dealer account is currently inactive. Please contact support.")
            db_product.dealer_id = dealer.id
        else:
            raise HTTPException(status_code=403, detail="You must have a dealer profile to create products.")
    
    # If dealer_id is still not set (e.g. admin didn't provide one), check if it's mandatory
    if not db_product.dealer_id:
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
             db_product.dealer_id = product_in.dealer_id or 1
        else:
             raise HTTPException(status_code=400, detail="Dealer ID is required for product creation.")

    db.add(db_product)
    await db.flush() # Get product ID without committing
    
    if variants_data:
        if not variant_attributes:
            raise HTTPException(
                status_code=400,
                detail="Cannot create variants because the category does not have any variant keys defined."
            )
        for v_data in variants_data:
            # Backwards compatibility for price calculation
            child_price = v_data.get("dealer_price")
            if child_price is None:
                child_price = db_product.dealer_price + v_data.get("price_adjustment", 0.0)
                
            # Merge parent and child attributes
            parent_attrs = db_product.attributes or {}
            child_attrs = v_data.get("attributes", {})
            merged_attrs = {**parent_attrs, **child_attrs}
            
            if v_data.get("sku") == "":
                v_data["sku"] = None
                
            db_child = ProductModel(
                name=db_product.name,
                description=db_product.description,
                sku=v_data.get("sku"),
                dealer_price=child_price,
                selling_price=db_product.selling_price,
                category_id=db_product.category_id,
                subcategory=db_product.subcategory,
                brand_id=db_product.brand_id,
                dealer_id=db_product.dealer_id,
                is_approved=db_product.is_approved,
                is_returnable=db_product.is_returnable,
                return_window_days=db_product.return_window_days,
                is_exchangeable=db_product.is_exchangeable,
                return_policy_note=db_product.return_policy_note,
                estimated_delivery_days=db_product.estimated_delivery_days,
                hsn_code=db_product.hsn_code,
                tax_category_id=db_product.tax_category_id,
                parent_product_id=db_product.id,
                images=v_data.get("images") or db_product.images,
                attributes=merged_attrs
            )
            db.add(db_child)

    await db.commit()
    await db.refresh(db_product)

    gst_logger.info(
        "[GST] Creating Product | ID: %s | Name: %s | HSN: %s | tax_category_id: %s",
        db_product.id, db_product.name, db_product.hsn_code, db_product.tax_category_id
    )

    # Fetch product with category and children loaded for response
    result = await db.execute(
        select(ProductModel)
        .where(ProductModel.id == db_product.id)
        .options(
            joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.dealer),
        joinedload(ProductModel.brand),
            selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        selectinload(ProductModel.children).selectinload(ProductModel.children),
        selectinload(ProductModel.children).joinedload(ProductModel.brand)
        )
    )
    return result.scalar_one()

@router.put("/products/{product_id}", response_model=Product, tags=["products"])
async def update_product(
    product_id: UUID, 
    product_in: ProductUpdate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update an existing product (Dealer of the product or Admin)"""
    result = await db.execute(select(ProductModel).where(ProductModel.id == product_id))
    db_product = result.scalar_one_or_none()
    
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Permission check
    if current_user.role != UserRole.ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        dealer_res = await db.execute(select(DealerModel).where(DealerModel.user_id == current_user.id))
        dealer = dealer_res.scalar_one_or_none()
        if not dealer or db_product.dealer_id != dealer.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this product")
        if not dealer.is_active:
            raise HTTPException(status_code=403, detail="Your dealer account is currently inactive. You cannot update products.")
    update_data = product_in.model_dump(exclude_unset=True)
    if update_data.get("sku") == "":
        update_data["sku"] = None
        
    variants_data = update_data.pop("variants", None)
    
    # We should validate mandatory attributes if they are being updated
    variant_attributes = []
    if "attributes" in update_data or variants_data is not None:
        start_id = update_data.get("subcategory_id", db_product.subcategory_id) if update_data.get("subcategory_id", db_product.subcategory_id) else update_data.get("category_id", db_product.category_id)
        hierarchy = select(CategoryModel.id, CategoryModel.parent_id).where(CategoryModel.id == start_id).cte(name="hierarchy", recursive=True)
        alias = aliased(CategoryModel)
        hierarchy = hierarchy.union_all(
            select(alias.id, alias.parent_id).where(alias.id == hierarchy.c.parent_id)
        )
        spec_groups = select(CategoryModel.id).where(
            CategoryModel.parent_id.in_(select(hierarchy.c.id)),
            CategoryModel.is_spec_group == True
        )
        attr_result = await db.execute(
            select(CategoryAttributeModel).where(
                or_(
                    CategoryAttributeModel.category_id.in_(select(hierarchy.c.id)),
                    CategoryAttributeModel.category_id.in_(spec_groups)
                )
            )
        )
        all_attributes = attr_result.scalars().all()
        required_attributes = [attr for attr in all_attributes if attr.is_mandatory]
        variant_attributes = [attr for attr in all_attributes if attr.is_variant_key]
        
        if "attributes" in update_data:
            product_attributes = update_data["attributes"] or {}
            missing_attributes = []
            for req_attr in required_attributes:
                val = product_attributes.get(req_attr.name)
                if val is None or val == "":
                    missing_attributes.append(req_attr.name)
                    
            if missing_attributes:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing mandatory attributes for this category: {', '.join(missing_attributes)}"
                )

    # GST logging for product update — capture old values before applying
    old_tax_category_id = db_product.tax_category_id
    old_tax_rule_id = db_product.tax_rule_id

    for key, value in update_data.items():
        setattr(db_product, key, value)

    if "tax_category_id" in update_data:
        gst_logger.info(
            "[GST] Updating Product | ID: %s | Previous tax_category_id: %s | New tax_category_id: %s | tax_rule_id: %s",
            db_product.id, old_tax_category_id, db_product.tax_category_id,
            db_product.tax_rule_id or "NULL"
        )

    if variants_data is not None:
        if variants_data and not variant_attributes:
            raise HTTPException(
                status_code=400,
                detail="Cannot create variants because the category does not have any variant keys defined."
            )
        # Simple implementation: Delete existing children and insert new ones
        await db.execute(ProductModel.__table__.delete().where(ProductModel.parent_product_id == db_product.id))
        
        for v_data in variants_data:
            child_price = v_data.get("dealer_price")
            if child_price is None:
                child_price = db_product.dealer_price + v_data.get("price_adjustment", 0.0)
                
            parent_attrs = db_product.attributes or {}
            child_attrs = v_data.get("attributes", {})
            merged_attrs = {**parent_attrs, **child_attrs}
            
            if v_data.get("sku") == "":
                v_data["sku"] = None
                
            db_child = ProductModel(
                name=db_product.name,
                description=db_product.description,
                sku=v_data.get("sku"),
                dealer_price=child_price,
                selling_price=db_product.selling_price,
                category_id=db_product.category_id,
                subcategory_id=db_product.subcategory_id,
                brand_id=db_product.brand_id,
                dealer_id=db_product.dealer_id,
                is_approved=db_product.is_approved,
                is_returnable=db_product.is_returnable,
                return_window_days=db_product.return_window_days,
                is_exchangeable=db_product.is_exchangeable,
                return_policy_note=db_product.return_policy_note,
                estimated_delivery_days=db_product.estimated_delivery_days,
                hsn_code=db_product.hsn_code,
                tax_category_id=db_product.tax_category_id,
                parent_product_id=db_product.id,
                images=v_data.get("images") or db_product.images,
                attributes=merged_attrs
            )
            db.add(db_child)

    await db.commit()
    await db.refresh(db_product)
    
    # Return with relations loaded
    result = await db.execute(
        select(ProductModel)
        .where(ProductModel.id == db_product.id)
        .options(
            joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.dealer),
        joinedload(ProductModel.brand),
            selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        selectinload(ProductModel.children).selectinload(ProductModel.children),
        selectinload(ProductModel.children).joinedload(ProductModel.brand)
        )
    )
    return result.scalar_one()

@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["products"])
async def delete_product(
    product_id: UUID, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a product (Dealer of the product or Admin)"""
    result = await db.execute(select(ProductModel).where(ProductModel.id == product_id))
    db_product = result.scalar_one_or_none()
    
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    # Permission check
    if current_user.role != UserRole.ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        dealer_res = await db.execute(select(DealerModel).where(DealerModel.user_id == current_user.id))
        dealer = dealer_res.scalar_one_or_none()
        if not dealer or db_product.dealer_id != dealer.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this product")

    # Check if ordered
    order_result = await db.execute(select(OrderItemModel).where(OrderItemModel.product_id == product_id))
    has_orders = order_result.first() is not None

    # Check if in inventory
    inv_result = await db.execute(select(ProductInventoryModel).where(ProductInventoryModel.product_id == product_id))
    has_inventory = inv_result.first() is not None

    if has_orders or has_inventory:
        db_product.is_deleted = True
    else:
        await db.delete(db_product)
        
    await db.commit()
    return None

@router.get("/brands", response_model=List[Brand], tags=["products"])
async def get_brands(
    subcategory_id: Optional[int] = Query(None), 
    category_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get all active brands, optionally filtered by subcategory or category"""
    query = select(BrandModel).where(BrandModel.is_active == True)
    if subcategory_id:
        query = query.join(SubcategoryBrand, SubcategoryBrand.brand_id == BrandModel.id).where(SubcategoryBrand.subcategory_id == subcategory_id)
    elif category_id:
        query = query.join(SubcategoryBrand, SubcategoryBrand.brand_id == BrandModel.id)\
                     .join(CategoryModel, CategoryModel.id == SubcategoryBrand.subcategory_id)\
                     .where(CategoryModel.parent_id == category_id)
    
    query = query.order_by(BrandModel.name.asc()).distinct()
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/brands", response_model=Brand, tags=["products"])
async def create_brand(
    brand_in: BrandCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new brand"""
    try:
        brand_data = brand_in.model_dump()
        subcategory_id = brand_data.pop("subcategory_id", None)
        
        # Check if brand already exists (case-insensitive)
        existing_brand_result = await db.execute(select(BrandModel).where(func.lower(BrandModel.name) == brand_data["name"].lower()))
        existing_brand = existing_brand_result.scalar_one_or_none()
        
        if existing_brand:
            db_brand = existing_brand
        else:
            db_brand = BrandModel(**brand_data)
            db.add(db_brand)
            await db.flush()
        
        if subcategory_id:
            # check if mapping already exists
            existing_mapping = await db.execute(select(SubcategoryBrand).where(
                and_(
                    SubcategoryBrand.subcategory_id == subcategory_id,
                    SubcategoryBrand.brand_id == db_brand.id
                )
            ))
            if not existing_mapping.scalar_one_or_none():
                subcat_brand = SubcategoryBrand(subcategory_id=subcategory_id, brand_id=db_brand.id)
                db.add(subcat_brand)
            
        await db.commit()
        await db.refresh(db_brand)
        return db_brand
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/brands/{brand_id}", response_model=Brand, tags=["products"])
async def update_brand(
    brand_id: int,
    brand_in: BrandUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a brand"""
    result = await db.execute(select(BrandModel).where(BrandModel.id == brand_id))
    db_brand = result.scalar_one_or_none()
    if not db_brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    
    update_data = brand_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_brand, key, value)
    
    await db.commit()
    await db.refresh(db_brand)
    return db_brand

@router.delete("/brands/{brand_id}", tags=["products"])
async def delete_brand(
    brand_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a brand"""
    result = await db.execute(select(BrandModel).where(BrandModel.id == brand_id))
    db_brand = result.scalar_one_or_none()
    if not db_brand:
        raise HTTPException(status_code=404, detail="Brand not found")
        
    await db.delete(db_brand)
    await db.commit()
    return {"message": "Brand deleted successfully"}

@router.get("/products", response_model=List[Product], tags=["products"])
async def get_products(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
    category_id: Optional[int] = None,
    dealer_id: Optional[UUID] = Query(None),
    hub_id: Optional[int] = Query(None),
    search: Optional[str] = None,
    is_approved: Optional[bool] = Query(None),
    include_children: Optional[bool] = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Get all products with pagination, search, and category filter"""
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.is_deleted == False
    )
    
    # If no specific dealer is requested, show only active/approved parent products (Public view)
    if not dealer_id:
        query = query.where(
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id.is_(None), PartnerModel.is_active == True)
        )
        if not include_children:
            query = query.where(ProductModel.parent_product_id.is_(None))

    
    if category_id:
        hierarchy = select(CategoryModel.id).where(CategoryModel.id == category_id).cte(name="hierarchy", recursive=True)
        alias = aliased(CategoryModel)
        hierarchy = hierarchy.union_all(
            select(alias.id).where(alias.parent_id == hierarchy.c.id)
        )
        query = query.where(or_(
            ProductModel.category_id.in_(select(hierarchy.c.id)),
            ProductModel.subcategory_id.in_(select(hierarchy.c.id))
        ))
    
    if dealer_id:
        # For a specific dealer, show ALL their products including pending ones
        query = query.where(
            ProductModel.dealer_id == dealer_id
        )
        if not include_children:
            query = query.where(ProductModel.parent_product_id.is_(None))

    if search:
        query = query.where(ProductModel.name.ilike(f"%{search}%"))
        
    if is_approved is not None:
        query = query.where(ProductModel.is_approved == is_approved)
        
    if hub_id:
        query = query.join(ProductInventoryModel, and_(
            ProductModel.id == ProductInventoryModel.product_id,
            ProductInventoryModel.hub_id == hub_id
        ))
        
    # Get total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar_one_or_none() or 0
    response.headers["X-Total-Count"] = str(total_count)
    
    query = query.order_by(ProductModel.created_at.desc())
    
    query = query.offset(skip).limit(limit).options(
        joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        joinedload(ProductModel.dealer),
        joinedload(ProductModel.brand),
        selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        selectinload(ProductModel.children).selectinload(ProductModel.children),
        selectinload(ProductModel.children).joinedload(ProductModel.brand)
    )
    result = await db.execute(query)
    products = result.scalars().all()
    
    if hub_id and products:
        product_ids = [p.id for p in products]
        inv_result = await db.execute(
            select(ProductInventoryModel.product_id, ProductInventoryModel.stock)
            .where(ProductInventoryModel.hub_id == hub_id)
            .where(ProductInventoryModel.product_id.in_(product_ids))
        )
        inv_map = {row.product_id: row.stock for row in inv_result.all()}
        for p in products:
            p.hub_stock = inv_map.get(p.id, 0)
            
    return products

@router.get("/products/search/history", response_model=List[SearchHistory], tags=["products"])
async def get_search_history(
    limit: int = 10,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent search history for logged-in user"""
    result = await db.execute(
        select(SearchHistoryModel)
        .where(SearchHistoryModel.customer_id == current_user.id)
        .order_by(SearchHistoryModel.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()

@router.get("/products/search", response_model=List[Product], tags=["products"])
async def search_products(
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    subcategory_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    min_discount: Optional[int] = None,
    brands: Optional[List[int]] = Query(None),
    attributes: Optional[str] = None, # JSON string of selected dynamic attribute filters
    in_stock: bool = False,
    include_variants: bool = False,
    sort_by: str = "name",
    sort_order: str = "asc",
    skip: int = 0,
    limit: int = 20,
    user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Advanced product search with filters and sorting"""
    print(f"DEBUG: Search request received. q='{q}', cat={category_id}, user={user}")
    # Save search history if user is logged in and query is provided
    if user and getattr(user, 'is_customer', False) and q:
        history_entry = SearchHistoryModel(customer_id=user.id, query=q)
        db.add(history_entry)
        await db.commit()  # Commit history even if search fails or returns nothing
    
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.is_deleted == False,
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id.is_(None), PartnerModel.is_active == True)
    )
    if not include_variants:
        query = query.where(ProductModel.parent_product_id.is_(None))
    
    # Text search (name and description)
    if q:
        search_filter = or_(
            ProductModel.name.ilike(f"%{q}%"),
            ProductModel.description.ilike(f"%{q}%")
        )
        query = query.where(search_filter)
    
    # Category filter with subcategories (Iterative mapping)
    if category_id:
        # Fast, safe memory-level mapping
        res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id))
        all_cats = res.all()
        children_map = {}
        for cid, pid in all_cats:
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(cid)
            
        stack = [category_id]
        visited = set()
        while stack:
            curr = stack.pop()
            if curr in visited: continue
            visited.add(curr)
            for child_id in children_map.get(curr, []):
                stack.append(child_id)
                
        query = query.where(or_(
            ProductModel.category_id.in_(list(visited)),
            ProductModel.subcategory_id.in_(list(visited))
        ))
    
    if subcategory_id is not None:
        query = query.where(ProductModel.subcategory_id == subcategory_id)
        
    # Price range
    if min_price is not None:
        query = query.where(ProductModel.selling_price >= min_price)
    if max_price is not None:
        query = query.where(ProductModel.selling_price <= max_price)
    
    # Rating filter
    if min_rating is not None:
        query = query.where(ProductModel.average_rating >= min_rating)
    
    # Discount filter
    if min_discount is not None:
        query = query.where(ProductModel.discount_percentage >= min_discount)

    # Brand filter (by brand_id)
    if brands:
        query = query.where(ProductModel.brand_id.in_(brands))
    
    
        
    # Dynamic Attributes Filter
    # attributes param comes as JSON string e.g. '{"RAM":["8GB","12GB"],"Storage":["128GB"]}'
    if attributes:
        try:
            attr_filters = json.loads(attributes)
            for attr_key, attr_values in attr_filters.items():
                if attr_values and isinstance(attr_values, list):
                    # We need to check if the JSON value stored at attr_key is in the list attr_values
                    # Check parent product OR any of its children
                    formatted_values = [f'"{v}"' for v in attr_values]
                    parent_has_it = cast(ProductModel.attributes[attr_key], String).in_(formatted_values)
                    child_has_it = ProductModel.children.any(cast(ProductModel.attributes[attr_key], String).in_(formatted_values))
                    query = query.where(or_(parent_has_it, child_has_it))
        except (json.JSONDecodeError, TypeError):
            print(f"DEBUG: Failed to parse attributes JSON: {attributes}")
            pass
    
    # Stock filter - need to handle inventory
    if in_stock:
        # We can't filter purely on ProductModel.stock > 0 anymore in DB, we'd have to filter the results.
        pass
    
    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.selling_price.asc() if sort_order == "asc" else ProductModel.selling_price.desc())
    elif sort_by == "rating":
        query = query.order_by(ProductModel.average_rating.desc())
    elif sort_by == "newest":
        query = query.order_by(ProductModel.created_at.desc())
    elif sort_by == "name":
        query = query.order_by(ProductModel.name.asc() if sort_order == "asc" else ProductModel.name.desc())
    else:
        # Fallback for 'recommended' or any empty sort
        query = query.order_by(ProductModel.created_at.desc())
    
    query = query.offset(skip).limit(limit).options(
        joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        joinedload(ProductModel.dealer),
        joinedload(ProductModel.brand),
        selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        selectinload(ProductModel.children).selectinload(ProductModel.children),
        selectinload(ProductModel.children).joinedload(ProductModel.brand)
    )
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    if in_stock:
        # safely check inventory
        products = [p for p in products if (getattr(p, 'hub_stock', 0) or 0) > 0]
            
    return products

@router.get("/products/autocomplete", tags=["products"])
async def autocomplete_products(
    q: str = Query(..., min_length=2),
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Get product name and category suggestions for autocomplete"""
    
    # Get matching product names
    result = await db.execute(
        select(ProductModel.name, ProductModel.id, ProductModel.selling_price, ProductModel.images)
        .join(DealerModel)
        .outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id)
        .where(
            ProductModel.name.ilike(f"%{q}%"),
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
        )
        .limit(limit)
    )
    products = result.all()
    
    # Extract unique suggestions
    suggestions = list(set([p[0] for p in products]))[:5]
    
    # Format product results
    product_results = [
        {
            "id": p[1],
            "name": p[0],
            "price": p[2],
            "image": p[3][0] if p[3] and len(p[3]) > 0 else None
        }
        for p in products[:5]
    ]
    
    # Get matching categories
    cat_result = await db.execute(
        select(CategoryModel.id, CategoryModel.name)
        .where(
            CategoryModel.name.ilike(f"%{q}%"),
            CategoryModel.is_active == True
        )
        .limit(5)
    )
    categories = cat_result.all()
    category_suggestions = [
        {
            "id": c[0],
            "name": c[1]
        }
        for c in categories
    ]
    
    return {
        "suggestions": suggestions,
        "categories": category_suggestions,
        "products": product_results
    }

@router.get("/products/filters", tags=["products"])
async def get_filter_options(
    category_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get available filter options for products"""
    
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.is_deleted == False,
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        ProductModel.parent_product_id.is_(None),
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    ).options(joinedload(ProductModel.brand), selectinload(ProductModel.children))
    
    clean_visited = []
    all_category_ids_for_attrs = set()
    if category_id:
        res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id))
        all_cats = res.all()
        children_map = {}
        parent_map = {}
        for cid, pid in all_cats:
            parent_map[cid] = pid
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(cid)
            
        stack = [category_id]
        visited = set()
        while stack:
            curr = stack.pop()
            if curr in visited: continue
            visited.add(curr)
            for child_id in children_map.get(curr, []):
                stack.append(child_id)
                
        clean_visited = [int(x) for x in visited if x is not None]
        
        # Build hierarchy (including parents) for fetching attributes
        curr_parent = category_id
        while curr_parent is not None:
            all_category_ids_for_attrs.add(curr_parent)
            curr_parent = parent_map.get(curr_parent)
        for v in clean_visited:
            all_category_ids_for_attrs.add(v)
            
        query = query.where(or_(
            ProductModel.category_id.in_(clean_visited),
            ProductModel.subcategory_id.in_(clean_visited)
        ))
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    if not products:
        return {
            "price_range": {"min": 0, "max": 0},
            "rating_distribution": {},
            "brands": [],
            "colors": [],
            "dynamic_attributes": [],
            "total_products": 0,
            "in_stock_count": 0
        }
    
    # Fetch configured dynamic attributes for the given categories
    dynamic_attributes_schema = []
    if all_category_ids_for_attrs:
        attr_query = select(CategoryAttributeModel).where(
            CategoryAttributeModel.category_id.in_(list(all_category_ids_for_attrs)),
            CategoryAttributeModel.is_filter == True
        )
        attr_res = await db.execute(attr_query)
        dynamic_attributes_schema = attr_res.scalars().all()
    
    configured_attr_names = {attr.name for attr in dynamic_attributes_schema}
    
    # Calculate price range
    prices = [p.selling_price for p in products if p.selling_price is not None]
    price_range = {
        "min": min(prices) if prices else 0,
        "max": max(prices) if prices else 0
    }
    
    # Calculate rating distribution
    rating_distribution = {
        "5": len([p for p in products if p.average_rating is not None and p.average_rating >= 4.5]),
        "4": len([p for p in products if p.average_rating is not None and 3.5 <= p.average_rating < 4.5]),
        "3": len([p for p in products if p.average_rating is not None and 2.5 <= p.average_rating < 3.5]),
        "2": len([p for p in products if p.average_rating is not None and 1.5 <= p.average_rating < 2.5]),
        "1": len([p for p in products if p.average_rating is not None and p.average_rating < 1.5]),
    }

    # Extract facets
    brands_map = {}
    for p in products:
        if p.brand:
            brands_map[p.brand.id] = p.brand.name
    brands = [{"id": bid, "name": bname} for bid, bname in brands_map.items()]
    brands = sorted(brands, key=lambda x: x["name"])
    
    colors_set = set()
    dynamic_attributes_values = {attr_name: set() for attr_name in configured_attr_names}
    
    for p in products:
        all_items = [p] + (p.children if p.children else [])
        for item in all_items:
            if item.attributes and isinstance(item.attributes, dict):
                # Legacy explicit colors mapping
                if 'Color' in item.attributes:
                    colors_set.add(item.attributes['Color'])
                # Dynamic mapping
                for attr_name in configured_attr_names:
                    if attr_name in item.attributes:
                        val = item.attributes[attr_name]
                        if val:
                            dynamic_attributes_values[attr_name].add(str(val))
                            
    colors = sorted(list(colors_set))
    
    dynamic_attributes_list = []
    for attr_name, val_set in dynamic_attributes_values.items():
        if val_set:
            dynamic_attributes_list.append({
                "name": attr_name,
                "values": sorted(list(val_set))
            })
    
    # Safely get stock
    def get_stock(p):
        if hasattr(p, 'stock'): return p.stock
        if hasattr(p, 'hub_stock'): return p.hub_stock
        return 0
        
    return {
        "price_range": price_range,
        "rating_distribution": rating_distribution,
        "brands": brands,
        "colors": colors,
        "dynamic_attributes": dynamic_attributes_list,
        "total_products": len(products),
        "in_stock_count": len([p for p in products if get_stock(p) > 0])
    }

@router.get("/categories/{category_id}/filter-counts", tags=["products"])
async def get_filter_counts(category_id: int, db: AsyncSession = Depends(get_db)):
    """Returns the counts for dynamic attributes so the UI knows what to render"""
    
    # First get the attributes relevant for this category
    hierarchy = select(CategoryModel.id, CategoryModel.parent_id).where(CategoryModel.id == category_id).cte(name="hierarchy", recursive=True)
    alias = aliased(CategoryModel)
    hierarchy = hierarchy.union_all(
        select(alias.id, alias.parent_id).where(alias.id == hierarchy.c.parent_id)
    )
    attr_result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.category_id.in_(select(hierarchy.c.id)))
    )
    attributes = attr_result.scalars().all()
    dynamic_keys = set(attr.name for attr in attributes)

    result_counts = {}
    
    # For each dynamic key, group by value and count
    for key in dynamic_keys:
        query = select(
            ProductModel.attributes[key].astext.label('variant'),
            func.count(ProductModel.id).label('total')
        ).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
            ProductModel.category_id == category_id,
            ProductModel.attributes.has_key(key),
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
        ).group_by(ProductModel.attributes[key].astext)
        
        result = await db.execute(query)
        stats = [{"value": row.variant, "count": row.total} for row in result.all() if row.variant]
        if stats:
             result_counts[key] = stats

    return result_counts

@router.get("/products/{product_id}", response_model=Product, tags=["products"])
async def get_product(
    product_id: UUID, 
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get a single product by ID. Dealers and Admins can see pending products."""
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.id == product_id,
        ProductModel.is_deleted == False
    )
    
    # Execute query first to check permissions afterwards if needed, 
    # OR build a smart query. BUILDING A SMART QUERY IS BETTER:
    
    # Public restriction: must be active/approved
    public_condition = (
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    )
    
    if current_user:
        # If Admin or Super Admin, bypass all restrictions
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            pass # No extra filter
        # If Dealer, see own products regardless of approval status
        elif current_user.role == UserRole.DEALER:
            query = query.where(
                or_(
                    # Public view
                    *public_condition,
                    # Own view
                    ProductModel.dealer_id == current_user.dealer_id
                )
            )
        else:
            # Other logged-in users follow public rules
            query = query.where(*public_condition)
    else:
        # Non-logged users follow public rules
        query = query.where(*public_condition)

    result = await db.execute(
        query.options(
            joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.subcategory).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.dealer),
            joinedload(ProductModel.brand),
            selectinload(ProductModel.children).joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            selectinload(ProductModel.children).joinedload(ProductModel.subcategory).selectinload(CategoryModel.attributes),
            selectinload(ProductModel.children).selectinload(ProductModel.children),
            selectinload(ProductModel.children).joinedload(ProductModel.brand)
        )
    )
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or currently unavailable")
        
    return product

@router.post("/products/upload-image", response_model=dict, tags=["products"])
async def upload_product_image(
    file: UploadFile = File(...),
    current_user: User = Depends(require_dealer_or_admin)
):
    """Upload product image"""
    path = await UploadService.upload_image(file, "products")
    return {"path": path}

@router.get("/products/recommendations", response_model=List[Product], tags=["products"])
async def get_recommendations(
    limit: int = 10,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get AI-powered product recommendations.
    Personalized if logged in, otherwise generic top products.
    """
    user_id = current_user.id if current_user else None
    products = await RecommendationService.get_recommendations(db, user_id, limit)
    return products

@router.post("/admin/products/bulk-upload", status_code=status.HTTP_201_CREATED, tags=["products"])
async def bulk_upload_products(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Bulk upload products from CSV file (admin only)
    CSV Header: name,description,dealer_price,stock,category_id,images,selling_price
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    # Read file content
    content = await file.read()
    decoded_content = content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(decoded_content))
    
    added_count = 0
    errors = []
    
    # Process rows
    rows = list(csv_reader)
    if not rows:
        raise HTTPException(status_code=400, detail="CSV file is empty or invalid")
        
    for row_idx, row in enumerate(rows, start=1):
        try:
            # Validate required fields
            if not row.get('name') or not row.get('dealer_price') or not row.get('category_id'):
                raise ValueError("Missing required fields (name, price, category_id)")
             
            # Parse numeric fields safely
            try:
                dealer_price = float(row['dealer_price'])
                stock = int(row.get('stock', 0))
                category_id = int(row['category_id'])
                selling_price_str = row.get('selling_price')
                discount_price = float(selling_price_str) if selling_price_str else None
            except ValueError:
                raise ValueError("Invalid numeric format for price, stock, or category_id")

            # Check category existence (optional optimization: cache this)
            cat_result = await db.execute(select(CategoryModel).where(CategoryModel.id == category_id))
            if not cat_result.scalar_one_or_none():
                raise ValueError(f"Category ID {category_id} not found")
            
            # Parse images
            images_str = row.get('images', '')
            images_list = images_str.split('|') if images_str else []
            images_list = [img.strip() for img in images_list if img.strip()]
            
            # Create product
            product_data = ProductCreate(
                name=row['name'],
                description=row.get('description'),
                dealer_price=dealer_price,
                selling_price=selling_price,
                stock=stock,
                category_id=category_id,
                images=images_list
            )
            
            db_product = ProductModel(**product_data.model_dump())
            # Auto-approve admin uploads
            db_product.is_approved = True
            
            db.add(db_product)
            added_count += 1
            
        except Exception as e:
            errors.append(f"Row {row_idx}: {str(e)}")
            continue
    
    if added_count > 0:
        await db.commit()
    
    return {
        "message": f"Processed {len(rows)} rows",
        "added_count": added_count,
        "failed_count": len(errors),
        "errors": errors
    }


@router.post("/categories/seed_smartphones", tags=["categories"])
async def seed_smartphones(db: AsyncSession = Depends(get_db)):
    # Check Electronics
    res = await db.execute(select(CategoryModel).where(CategoryModel.name == 'Electronics'))
    elec = res.scalar_one_or_none()
    if not elec:
        elec = CategoryModel(name='Electronics')
        db.add(elec)
        await db.commit()
        await db.refresh(elec)
        
    # Check Smartphones
    res = await db.execute(select(CategoryModel).where(CategoryModel.name == 'Smartphones'))
    smart = res.scalar_one_or_none()
    if not smart:
        smart = CategoryModel(name='Smartphones', parent_id=elec.id)
        db.add(smart)
        await db.commit()
        await db.refresh(smart)
        
        import json
        attrs = [
            CategoryAttributeModel(category_id=smart.id, name='RAM', is_mandatory=True, datatype='string', allowed_values=json.dumps(['4GB', '6GB', '8GB', '12GB'])),
            CategoryAttributeModel(category_id=smart.id, name='Storage', is_mandatory=True, datatype='string', allowed_values=json.dumps(['64GB', '128GB', '256GB', '512GB'])),
            CategoryAttributeModel(category_id=smart.id, name='Color', is_mandatory=True, datatype='string', allowed_values=json.dumps([])),
            CategoryAttributeModel(category_id=smart.id, name='Battery', is_mandatory=False, datatype='string', allowed_values=json.dumps(['3000mAh', '4000mAh', '5000mAh'])),
        ]
        db.add_all(attrs)
        await db.commit()
        return {"msg": "Smartphones created"}
    return {"msg": "Already exists"}
