import logging
from decimal import Decimal
import uuid
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, and_, cast, String, text
from sqlalchemy.exc import IntegrityError
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
    Category, CategoryCreate, CategoryUpdate, CategoryAttribute, CategoryAttributeCreate, CategoryAttributeUpdate,
    FeeDeductionItem, PriceTaxRow, ProductPayoutEstimationRequest, ProductPayoutEstimationResponse
)
from models.product import Product as ProductModel, Category as CategoryModel, CategoryAttribute as CategoryAttributeModel, Brand as BrandModel, SubcategoryBrand
from models.tax import TaxCategory as TaxCategoryModel
from models.search_history import SearchHistory as SearchHistoryModel
from models.user import UserRole
from models.dealer import Dealer as DealerModel
from models.partner import Partner as PartnerModel
from models.inventory import ProductInventory as ProductInventoryModel
from schemas.search_history import SearchHistory
from models.cart import OrderItem as OrderItemModel, CartItem as CartItemModel
from core.permissions import (
    require_admin, get_current_active_user, 
    get_current_user_optional, require_dealer_or_admin
)
from models.customer_user import CustomerUser
from services.file_upload import FileUploadService as UploadService
from services.recommendation import RecommendationService
from services.fee_service import get_applicable_slab, resolve_slab_gst_rate, get_all_active_tax_categories
from services.configuration_service import get_fee_config
from services.tax_service import TaxService
from models.user import User

router = APIRouter()

async def get_category_descendant_ids(category_id: int, db: AsyncSession) -> List[int]:
    """Get all descendant category IDs (including the category itself) dynamically."""
    res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id))
    all_cats = res.all()
    children_map: dict = {}
    for cid, pid in all_cats:
        if pid not in children_map:
            children_map[pid] = []
        children_map[pid].append(cid)
    
    stack = [category_id]
    visited = set()
    descendants = []
    while stack:
        curr = stack.pop()
        if curr in visited:
            continue
        visited.add(curr)
        descendants.append(curr)
        for child_id in children_map.get(curr, []):
            stack.append(child_id)
            
    return descendants

async def get_category_ancestor_ids(category_id: int, db: AsyncSession) -> List[int]:
    """Get all ancestor category IDs (including the category itself) dynamically."""
    res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id))
    all_cats = res.all()
    parent_map = {cid: pid for cid, pid in all_cats}
    
    ancestors = []
    curr = category_id
    visited = set()
    while curr is not None and curr not in visited:
        visited.add(curr)
        ancestors.append(curr)
        curr = parent_map.get(curr)
        
    return ancestors

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
    descendant_ids = await get_category_descendant_ids(category_id, db)
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        or_(
            ProductModel.category_id.in_(descendant_ids),
            ProductModel.subcategory_id.in_(descendant_ids)
        ),
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
    # If parent_product_id is provided, inherit category_id if omitted
    parent_obj = None
    if product_in.parent_product_id:
        parent_res = await db.execute(select(ProductModel).where(ProductModel.id == product_in.parent_product_id))
        parent_obj = parent_res.scalar_one_or_none()
        if parent_obj and product_in.category_id is None:
            product_in.category_id = parent_obj.category_id

    # Validate category exists
    if product_in.category_id is None:
        raise HTTPException(status_code=400, detail="Category ID is required")
    cat_result = await db.execute(select(CategoryModel).where(CategoryModel.id == product_in.category_id))
    if not cat_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Category not found")

    # Validate subcategory belongs to category hierarchy if provided
    if product_in.subcategory_id:
        descendants = await get_category_descendant_ids(product_in.category_id, db)
        if product_in.subcategory_id not in descendants:
            raise HTTPException(
                status_code=400,
                detail="Selected subcategory does not belong to the selected category hierarchy"
            )

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
        
    if product_data.get("brand_id") == -1:
        other_brand = await get_or_create_other_brand(db)
        product_data["brand_id"] = other_brand.id

    variants_data = product_data.pop("variants", [])
    if product_in.parent_product_id and variants_data:
        raise HTTPException(
            status_code=400,
            detail="Cannot create child variants for an existing variant. Multi-level variant nesting is not supported."
        )
    
    db_product = ProductModel(**product_data)
    
    # Automatically assign dealer_id if the user is a dealer
    if current_user.role in [UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY, UserRole.DEALER_ORDERS, UserRole.DEALER_FINANCE]:
        resolved_d_id = current_user.dealer_id
        if not resolved_d_id:
            dealer_res = await db.execute(select(DealerModel).where(DealerModel.user_id == current_user.id))
            dealer = dealer_res.scalar_one_or_none()
            if dealer:
                if not dealer.is_active:
                    raise HTTPException(status_code=403, detail="Your dealer account is currently inactive. Please contact support.")
                resolved_d_id = dealer.id
                current_user.dealer_id = dealer.id
        if resolved_d_id:
            db_product.dealer_id = resolved_d_id
        else:
            raise HTTPException(status_code=403, detail="You must have a dealer profile to create products.")
    
    # If dealer_id is still not set (e.g. admin didn't provide one), check if it's mandatory
    if not db_product.dealer_id:
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
             db_product.dealer_id = product_in.dealer_id or 1
        else:
             raise HTTPException(status_code=400, detail="Dealer ID is required for product creation.")

    # Inherit from parent product if creating a child product directly
    if db_product.parent_product_id:
        if not parent_obj:
            parent_res = await db.execute(select(ProductModel).where(ProductModel.id == db_product.parent_product_id))
            parent_obj = parent_res.scalar_one_or_none()
        if parent_obj:
            if db_product.category_id is None:
                db_product.category_id = parent_obj.category_id
            if db_product.dealer_price is None or db_product.dealer_price == 0:
                db_product.dealer_price = parent_obj.dealer_price
            if db_product.mrp is None or db_product.mrp == 0:
                db_product.mrp = parent_obj.mrp
            if db_product.selling_price is None or db_product.selling_price == 0:
                db_product.selling_price = parent_obj.selling_price
            if db_product.discount_price is None or db_product.discount_price == 0:
                db_product.discount_price = parent_obj.discount_price
            if db_product.tax_category_id is None:
                db_product.tax_category_id = parent_obj.tax_category_id
            if db_product.tax_perc is None:
                db_product.tax_perc = parent_obj.tax_perc
            if db_product.discount_percentage is None:
                db_product.discount_percentage = parent_obj.discount_percentage
            if db_product.is_approved is None:
                db_product.is_approved = parent_obj.is_approved
            if not db_product.hsn_code:
                db_product.hsn_code = parent_obj.hsn_code
            if not db_product.images:
                db_product.images = parent_obj.images or ["https://via.placeholder.com/300"]
            if not db_product.brand_id:
                db_product.brand_id = parent_obj.brand_id
    else:
        if db_product.dealer_price is None:
            raise HTTPException(status_code=400, detail="Dealer price is required for products.")
        if not db_product.hsn_code:
            raise HTTPException(status_code=400, detail="HSN code is required for products.")
        if not db_product.images:
            db_product.images = ["https://via.placeholder.com/300"]

    # Resolve tax_perc from TaxCategory if tax_category_id is provided and tax_perc is None
    if db_product.tax_category_id is not None and db_product.tax_perc is None:
        tc_res = await db.execute(select(TaxCategoryModel).where(TaxCategoryModel.id == db_product.tax_category_id))
        tc = tc_res.scalar_one_or_none()
        if tc:
            db_product.tax_perc = tc.igst_rate or (tc.cgst_rate + tc.sgst_rate)

    # Calculate parent price/tax fields if not fully provided
    if db_product.tax_perc is not None and db_product.tax_price is None and db_product.dealer_price is not None:
        db_product.tax_price = round(db_product.dealer_price * (db_product.tax_perc / 100.0), 2)
    if db_product.mrp is None and db_product.dealer_price is not None:
        db_product.mrp = round(db_product.dealer_price + (db_product.tax_price or 0.0), 2)
    if db_product.discount_percentage is not None and db_product.selling_price is None:
        db_product.selling_price = round((db_product.mrp or db_product.dealer_price) * (1.0 - db_product.discount_percentage / 100.0), 2)
    if db_product.mrp is not None and db_product.selling_price is not None:
        if db_product.mrp > db_product.selling_price:
            db_product.discount_price = round(db_product.mrp - db_product.selling_price, 2)
            if db_product.discount_percentage is None and db_product.mrp > 0:
                db_product.discount_percentage = int(round((db_product.discount_price / db_product.mrp) * 100))
        else:
            db_product.discount_price = None
            db_product.discount_percentage = None

    db.add(db_product)
    await db.flush() # Get product ID without committing
    
    if variants_data:
        if not variant_attributes:
            raise HTTPException(
                status_code=400,
                detail="Cannot create variants because the category does not have any variant keys defined."
            )
        for v_data in variants_data:
            # 1. Child dealer price (base price excl tax)
            child_price = v_data.get("dealer_price")
            if child_price is None:
                price_adj = v_data.get("price_adjustment", 0.0) or 0.0
                child_price = round(db_product.dealer_price + price_adj, 2)
            else:
                child_price = round(float(child_price), 2)

            # 2. Child tax_perc and tax_price
            child_tax_perc = v_data.get("tax_perc") if v_data.get("tax_perc") is not None else db_product.tax_perc
            child_tax_price = v_data.get("tax_price")
            if child_tax_price is None and child_tax_perc is not None and child_price is not None:
                child_tax_price = round(child_price * (child_tax_perc / 100.0), 2)
            elif child_tax_price is not None:
                child_tax_price = round(float(child_tax_price), 2)

            # 3. Child MRP (incl tax)
            child_mrp = v_data.get("mrp")
            if child_mrp is None:
                if child_price is not None and child_tax_price is not None:
                    child_mrp = round(child_price + child_tax_price, 2)
                elif child_price is not None and child_tax_perc is not None:
                    child_mrp = round(child_price * (1.0 + child_tax_perc / 100.0), 2)
                else:
                    child_mrp = child_price
            else:
                child_mrp = round(float(child_mrp), 2)

            # 4. Child discount percentage and selling price
            child_discount_pct = v_data.get("discount_percentage") if v_data.get("discount_percentage") is not None else db_product.discount_percentage
            child_selling_price = v_data.get("selling_price")
            if child_selling_price is None:
                if child_discount_pct is not None and child_discount_pct > 0 and child_mrp is not None:
                    child_selling_price = round(child_mrp * (1.0 - child_discount_pct / 100.0), 2)
                elif db_product.selling_price is not None and db_product.mrp and child_mrp is not None and db_product.mrp > 0:
                    discount_ratio = (db_product.mrp - db_product.selling_price) / db_product.mrp
                    child_selling_price = round(child_mrp * (1.0 - discount_ratio), 2)
                else:
                    child_selling_price = child_mrp
            else:
                child_selling_price = round(float(child_selling_price), 2)

            # 5. Child discount price (amount saved)
            child_discount_price = v_data.get("discount_price")
            if child_discount_price is None and child_mrp is not None and child_selling_price is not None:
                child_discount_price = round(child_mrp - child_selling_price, 2)
            elif child_discount_price is not None:
                child_discount_price = round(float(child_discount_price), 2)
                
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
                selling_price=child_selling_price,
                mrp=child_mrp,
                tax_perc=child_tax_perc,
                tax_price=child_tax_price,
                discount_price=child_discount_price,
                discount_percentage=child_discount_pct,
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
        
    if update_data.get("brand_id") == -1:
        other_brand = await get_or_create_other_brand(db)
        update_data["brand_id"] = other_brand.id
    elif "brand_id" in update_data and update_data["brand_id"] is None and db_product.brand_id is not None:
        update_data.pop("brand_id")

    variants_data = update_data.pop("variants", None)
    if (db_product.parent_product_id or update_data.get("parent_product_id")) and variants_data:
        raise HTTPException(
            status_code=400,
            detail="Cannot create child variants for an existing variant. Multi-level variant nesting is not supported."
        )

    # Validate subcategory belongs to category hierarchy if provided/updated
    target_category_id = update_data.get("category_id", db_product.category_id)
    target_subcategory_id = update_data.get("subcategory_id", db_product.subcategory_id)
    if target_subcategory_id and target_category_id:
        descendants = await get_category_descendant_ids(target_category_id, db)
        if target_subcategory_id not in descendants:
            raise HTTPException(
                status_code=400,
                detail="Selected subcategory does not belong to the selected category hierarchy"
            )
    
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
        if db_product.tax_category_id is not None and "tax_perc" not in update_data:
            tc_res = await db.execute(select(TaxCategoryModel).where(TaxCategoryModel.id == db_product.tax_category_id))
            tc = tc_res.scalar_one_or_none()
            if tc:
                db_product.tax_perc = tc.igst_rate or (tc.cgst_rate + tc.sgst_rate)

    # Recalculate parent price/tax fields if needed
    if db_product.tax_perc is not None and db_product.dealer_price is not None:
        db_product.tax_price = round(db_product.dealer_price * (db_product.tax_perc / 100.0), 2)
        if db_product.mrp is None or "dealer_price" in update_data or "tax_category_id" in update_data:
            db_product.mrp = round(db_product.dealer_price + db_product.tax_price, 2)
        if db_product.discount_percentage is not None:
            db_product.selling_price = round(db_product.mrp * (1.0 - db_product.discount_percentage / 100.0), 2)
            db_product.discount_price = round(db_product.mrp - db_product.selling_price, 2)

    if variants_data is not None:
        if variants_data and not variant_attributes:
            raise HTTPException(
                status_code=400,
                detail="Cannot create variants because the category does not have any variant keys defined."
            )
        # Load existing children of this product
        existing_children_res = await db.execute(
            select(ProductModel).where(ProductModel.parent_product_id == db_product.id)
        )
        existing_children = list(existing_children_res.scalars().all())

        children_by_id = {str(c.id): c for c in existing_children}
        children_by_sku = {c.sku: c for c in existing_children if c.sku}
        retained_child_ids = set()

        for v_data in variants_data:
            # Match existing child variant
            matched_child = None
            v_id_raw = v_data.get("id")
            v_id = str(v_id_raw) if v_id_raw else None
            v_sku = v_data.get("sku") or None
            child_attrs = v_data.get("attributes", {})

            if v_id and v_id in children_by_id:
                matched_child = children_by_id[v_id]
            elif v_sku and v_sku in children_by_sku:
                matched_child = children_by_sku[v_sku]
            elif len(existing_children) == 1 and len(variants_data) == 1 and not retained_child_ids:
                matched_child = existing_children[0]
            else:
                for c in existing_children:
                    if c.id not in retained_child_ids and (c.attributes or {}) == child_attrs:
                        matched_child = c
                        break

            if matched_child:
                retained_child_ids.add(matched_child.id)

            # 1. Child dealer price (base price excl tax)
            child_price = v_data.get("dealer_price")
            if child_price is None:
                price_adj = v_data.get("price_adjustment", 0.0) or 0.0
                child_price = round(db_product.dealer_price + price_adj, 2)
            else:
                child_price = round(float(child_price), 2)

            # 2. Child tax_perc and tax_price
            child_tax_perc = v_data.get("tax_perc") if v_data.get("tax_perc") is not None else db_product.tax_perc
            if child_tax_perc is None and db_product.tax_category_id:
                tc_res = await db.execute(select(TaxCategoryModel).where(TaxCategoryModel.id == db_product.tax_category_id))
                tc = tc_res.scalar_one_or_none()
                if tc:
                    child_tax_perc = tc.igst_rate or (tc.cgst_rate + tc.sgst_rate)
            child_tax_price = v_data.get("tax_price")
            if child_tax_price is None and child_tax_perc is not None and child_price is not None:
                child_tax_price = round(child_price * (child_tax_perc / 100.0), 2)
            elif child_tax_price is not None:
                child_tax_price = round(float(child_tax_price), 2)

            # 3. Child MRP (incl tax)
            child_mrp = v_data.get("mrp")
            if child_mrp is None:
                if child_price is not None and child_tax_price is not None:
                    child_mrp = round(child_price + child_tax_price, 2)
                elif child_price is not None and child_tax_perc is not None:
                    child_mrp = round(child_price * (1.0 + child_tax_perc / 100.0), 2)
                else:
                    child_mrp = child_price
            else:
                child_mrp = round(float(child_mrp), 2)

            # 4. Child discount percentage and selling price
            child_discount_pct = v_data.get("discount_percentage") if v_data.get("discount_percentage") is not None else db_product.discount_percentage
            child_selling_price = v_data.get("selling_price")
            if child_selling_price is None:
                if child_discount_pct is not None and child_discount_pct > 0 and child_mrp is not None:
                    child_selling_price = round(child_mrp * (1.0 - child_discount_pct / 100.0), 2)
                elif db_product.selling_price is not None and db_product.mrp and child_mrp is not None and db_product.mrp > 0:
                    discount_ratio = (db_product.mrp - db_product.selling_price) / db_product.mrp
                    child_selling_price = round(child_mrp * (1.0 - discount_ratio), 2)
                else:
                    child_selling_price = child_mrp
            else:
                child_selling_price = round(float(child_selling_price), 2)

            # 5. Child discount price (amount saved)
            child_discount_price = v_data.get("discount_price")
            if child_discount_price is None and child_mrp is not None and child_selling_price is not None:
                child_discount_price = round(child_mrp - child_selling_price, 2)
            elif child_discount_price is not None:
                child_discount_price = round(float(child_discount_price), 2)
                
            parent_attrs = db_product.attributes or {}
            merged_attrs = {**parent_attrs, **child_attrs}
            
            sku_val = v_data.get("sku") or None
            if sku_val == "":
                sku_val = None

            if matched_child:
                matched_child.name = db_product.name
                matched_child.description = db_product.description
                if sku_val:
                    matched_child.sku = sku_val
                matched_child.dealer_price = child_price
                matched_child.selling_price = child_selling_price
                matched_child.mrp = child_mrp
                matched_child.tax_perc = child_tax_perc
                matched_child.tax_price = child_tax_price
                matched_child.discount_price = child_discount_price
                matched_child.discount_percentage = child_discount_pct
                matched_child.category_id = db_product.category_id
                matched_child.subcategory_id = db_product.subcategory_id
                matched_child.brand_id = db_product.brand_id
                matched_child.dealer_id = db_product.dealer_id
                matched_child.is_approved = db_product.is_approved
                matched_child.is_returnable = db_product.is_returnable
                matched_child.return_window_days = db_product.return_window_days
                matched_child.is_exchangeable = db_product.is_exchangeable
                matched_child.return_policy_note = db_product.return_policy_note
                matched_child.estimated_delivery_days = db_product.estimated_delivery_days
                matched_child.hsn_code = db_product.hsn_code
                matched_child.tax_category_id = db_product.tax_category_id
                matched_child.images = v_data.get("images") or db_product.images
                matched_child.attributes = merged_attrs
                matched_child.is_deleted = False
            else:
                db_child = ProductModel(
                    name=db_product.name,
                    description=db_product.description,
                    sku=sku_val,
                    dealer_price=child_price,
                    selling_price=child_selling_price,
                    mrp=child_mrp,
                    tax_perc=child_tax_perc,
                    tax_price=child_tax_price,
                    discount_price=child_discount_price,
                    discount_percentage=child_discount_pct,
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

        # Handle removed variants (orphans) safely
        for orphan in existing_children:
            if orphan.id not in retained_child_ids:
                from sqlalchemy import delete
                await db.execute(delete(CartItemModel).where(CartItemModel.variant_id == orphan.id))
                try:
                    async with db.begin_nested():
                        await db.delete(orphan)
                        await db.flush()
                except Exception:
                    orphan.is_deleted = True
                    if orphan.sku:
                        orphan.sku = f"{orphan.sku}_del_{uuid.uuid4().hex[:8]}"

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
    res_product = result.scalar_one()
    await TaxService.apply_dynamic_product_pricing(db, res_product)
    return res_product

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

async def get_or_create_other_brand(db: AsyncSession) -> BrandModel:
    res = await db.execute(select(BrandModel).where(func.lower(BrandModel.name) == 'other'))
    brand = res.scalar_one_or_none()
    if not brand:
        brand = BrandModel(name="Other", description="Other / Unlisted Brand", is_active=True)
        db.add(brand)
        await db.commit()
        await db.refresh(brand)
    return brand

@router.get("/brands", response_model=List[Brand], tags=["products"])
async def get_brands(
    subcategory_id: Optional[int] = Query(None), 
    category_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get all active brands, optionally filtered by subcategory or category"""
    await get_or_create_other_brand(db)
    query = select(BrandModel).where(BrandModel.is_active == True)
    if subcategory_id:
        family_ids = await get_category_descendant_ids(subcategory_id, db)
        ancestor_ids = await get_category_ancestor_ids(subcategory_id, db)
        all_ids = list(set(family_ids + ancestor_ids))
        query = query.outerjoin(SubcategoryBrand, SubcategoryBrand.brand_id == BrandModel.id).where(
            or_(
                SubcategoryBrand.subcategory_id.in_(all_ids),
                func.lower(BrandModel.name) == 'other'
            )
        )
    elif category_id:
        family_ids = await get_category_descendant_ids(category_id, db)
        query = query.outerjoin(SubcategoryBrand, SubcategoryBrand.brand_id == BrandModel.id).where(
            or_(
                SubcategoryBrand.subcategory_id.in_(family_ids),
                func.lower(BrandModel.name) == 'other'
            )
        )
    
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

def get_search_variations(term: str) -> List[str]:
    clean = term.strip()
    if not clean:
        return []
    variations = [clean]
    lower = clean.lower()

    # Plural to singular
    if lower.endswith("ies") and len(clean) > 4:
        variations.append(clean[:-3] + "y")
    elif lower.endswith("es") and len(clean) > 4 and (lower[-3] in "sxyz" or lower.endswith(("ches", "shes"))):
        variations.append(clean[:-2])
    elif lower.endswith("s") and len(clean) > 3 and not lower.endswith("ss"):
        variations.append(clean[:-1])

    # Singular to plural
    if lower.endswith("y") and len(clean) > 3 and lower[-2] not in "aeiou":
        variations.append(clean[:-1] + "ies")
    elif lower.endswith(("s", "x", "z", "ch", "sh")) and not lower.endswith("es"):
        variations.append(clean + "es")
    elif not lower.endswith("s"):
        variations.append(clean + "s")

    seen = set()
    result = []
    for v in variations:
        v_low = v.lower()
        if v_low not in seen:
            seen.add(v_low)
            result.append(v)
    return result

@router.get("/products", response_model=List[Product], tags=["products"])
async def get_products(
    response: Response,
    skip: int = 0,
    limit: int = 100,
    category_id: Optional[int] = None,
    subcategory_id: Optional[int] = None,
    dealer_id: Optional[UUID] = None,
    my_products: Optional[bool] = False,
    hub_id: Optional[int] = None,
    search: Optional[str] = None,
    q: Optional[str] = None,
    is_approved: Optional[bool] = None,
    include_children: Optional[bool] = False,
    min_discount: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get all products with pagination, search, category, and subcategory filter"""
    target_dealer_id = dealer_id
    if (my_products or (not target_dealer_id and my_products is not False)) and current_user and hasattr(current_user, 'role') and current_user.role in [UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY, UserRole.DEALER_ORDERS, UserRole.DEALER_FINANCE]:
        if my_products:
            if getattr(current_user, 'dealer_id', None):
                target_dealer_id = current_user.dealer_id
            else:
                d_check = await db.execute(select(DealerModel.id).where(DealerModel.user_id == current_user.id))
                target_dealer_id = d_check.scalar_one_or_none()

    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(
        ProductModel.is_deleted == False
    )
    
    # If no specific dealer is requested, show only active/approved parent products (Public view)
    if not target_dealer_id:
        query = query.where(
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id.is_(None), PartnerModel.is_active == True)
        )
        if not include_children:
            query = query.where(ProductModel.parent_product_id.is_(None))

    
    if subcategory_id is not None and category_id is not None:
        subcat_family = await get_category_descendant_ids(subcategory_id, db)
        cat_family = await get_category_descendant_ids(category_id, db)
        target_ids = list(set(subcat_family).intersection(set(cat_family)))
        query = query.where(or_(
            ProductModel.category_id.in_(target_ids),
            ProductModel.subcategory_id.in_(target_ids)
        ))
    elif subcategory_id is not None:
        subcat_family = await get_category_descendant_ids(subcategory_id, db)
        query = query.where(or_(
            ProductModel.category_id.in_(subcat_family),
            ProductModel.subcategory_id.in_(subcat_family)
        ))
    elif category_id is not None:
        cat_family = await get_category_descendant_ids(category_id, db)
        query = query.where(or_(
            ProductModel.category_id.in_(cat_family),
            ProductModel.subcategory_id.in_(cat_family)
        ))
    
    if target_dealer_id:
        # For a specific dealer, show ALL their products including pending ones
        query = query.where(
            ProductModel.dealer_id == target_dealer_id
        )
        if not include_children:
            query = query.where(ProductModel.parent_product_id.is_(None))

    search_term = (q or search or "").strip()
    if search_term:
        SubcategoryModel = aliased(CategoryModel)
        variations = get_search_variations(search_term)
        search_clauses = []
        for term in variations:
            search_clauses.extend([
                ProductModel.name.ilike(f"%{term}%"),
                ProductModel.description.ilike(f"%{term}%"),
                BrandModel.name.ilike(f"%{term}%"),
                and_(CategoryModel.name.ilike(f"%{term}%"), CategoryModel.is_active == True, CategoryModel.is_deleted == False),
                and_(SubcategoryModel.name.ilike(f"%{term}%"), SubcategoryModel.is_active == True, SubcategoryModel.is_deleted == False)
            ])
        query = (
            query
            .outerjoin(BrandModel, ProductModel.brand_id == BrandModel.id)
            .outerjoin(CategoryModel, ProductModel.category_id == CategoryModel.id)
            .outerjoin(SubcategoryModel, ProductModel.subcategory_id == SubcategoryModel.id)
            .where(or_(*search_clauses))
        )
        
    if is_approved is not None:
        query = query.where(ProductModel.is_approved == is_approved)
        
    if min_discount is not None:
        query = query.where(
            or_(
                ProductModel.discount_percentage >= min_discount,
                and_(ProductModel.mrp.isnot(None), ProductModel.mrp > ProductModel.selling_price)
            )
        )
        
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
    
    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.selling_price.asc() if sort_order == "asc" else ProductModel.selling_price.desc())
    elif sort_by == "rating":
        query = query.order_by(ProductModel.average_rating.desc())
    elif sort_by == "newest":
        query = query.order_by(ProductModel.created_at.desc())
    elif sort_by == "discount":
        query = query.order_by(ProductModel.discount_percentage.desc().nullslast(), ProductModel.created_at.desc())
    elif sort_by == "name":
        query = query.order_by(ProductModel.name.asc() if sort_order == "asc" else ProductModel.name.desc())
    else:
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
    products = result.scalars().unique().all()
    
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
            
    await TaxService.apply_dynamic_product_pricing(db, products)
    return products

@router.get("/products/search/history", response_model=List[SearchHistory], tags=["products"])
async def get_search_history(
    limit: int = 10,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent search history for logged-in user"""
    target_id = current_user.id
    user_exists = await db.scalar(select(User.id).where(User.id == current_user.id))
    if not user_exists and (getattr(current_user, 'phone', None) or getattr(current_user, 'email', None)):
        conds = []
        if getattr(current_user, 'phone', None):
            conds.append(User.phone == current_user.phone)
        if getattr(current_user, 'email', None):
            conds.append(User.email == current_user.email)
        matched_id = await db.scalar(select(User.id).where(or_(*conds)))
        if matched_id:
            target_id = matched_id
        else:
            return []
    elif not user_exists:
        return []

    result = await db.execute(
        select(SearchHistoryModel)
        .where(SearchHistoryModel.customer_id == target_id)
        .order_by(SearchHistoryModel.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()

@router.get("/products/search", response_model=List[Product], tags=["products"])
async def search_products(
    response: Response = None,
    q: Optional[str] = None,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    subcategory_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    min_discount: Optional[int] = None,
    brands: Optional[List[str]] = Query(default=None),
    colors: Optional[List[str]] = Query(default=None),
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
    search_term = (q or search or "").strip()
    # Save search history if user is logged in and query is provided
    if user and getattr(user, 'is_customer', False) and search_term:
        try:
            # Check if customer has a valid referenced user ID in the users table
            target_user_id = await db.scalar(select(User.id).where(User.id == user.id))
            if not target_user_id and (getattr(user, 'phone', None) or getattr(user, 'email', None)):
                conds = []
                if getattr(user, 'phone', None):
                    conds.append(User.phone == user.phone)
                if getattr(user, 'email', None):
                    conds.append(User.email == user.email)
                target_user_id = await db.scalar(select(User.id).where(or_(*conds)))

            if target_user_id:
                history_entry = SearchHistoryModel(customer_id=target_user_id, query=search_term)
                db.add(history_entry)
                await db.commit()
        except IntegrityError:
            await db.rollback()
        except Exception as e:
            await db.rollback()
            gst_logger.warning("Failed to record search history: %s", e)
    
    SubcategoryModel = aliased(CategoryModel)
    query = (
        select(ProductModel)
        .join(DealerModel)
        .outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id)
        .outerjoin(BrandModel, ProductModel.brand_id == BrandModel.id)
        .outerjoin(CategoryModel, ProductModel.category_id == CategoryModel.id)
        .outerjoin(SubcategoryModel, ProductModel.subcategory_id == SubcategoryModel.id)
        .where(
            ProductModel.is_deleted == False,
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id.is_(None), PartnerModel.is_active == True)
        )
    )
    if not include_variants:
        query = query.where(ProductModel.parent_product_id.is_(None))
    
    # Text search (name, description, brand, category, subcategory with singular/plural variations)
    if search_term:
        variations = get_search_variations(search_term)
        search_clauses = []
        for term in variations:
            search_clauses.extend([
                ProductModel.name.ilike(f"%{term}%"),
                ProductModel.description.ilike(f"%{term}%"),
                BrandModel.name.ilike(f"%{term}%"),
                and_(CategoryModel.name.ilike(f"%{term}%"), CategoryModel.is_active == True, CategoryModel.is_deleted == False),
                and_(SubcategoryModel.name.ilike(f"%{term}%"), SubcategoryModel.is_active == True, SubcategoryModel.is_deleted == False)
            ])
        query = query.where(or_(*search_clauses))
    
    # Category filter with subcategories
    if subcategory_id is not None and category_id is not None:
        subcat_family = await get_category_descendant_ids(subcategory_id, db)
        cat_family = await get_category_descendant_ids(category_id, db)
        target_ids = list(set(subcat_family).intersection(set(cat_family)))
        query = query.where(or_(
            ProductModel.category_id.in_(target_ids),
            ProductModel.subcategory_id.in_(target_ids)
        ))
    elif subcategory_id is not None:
        subcat_family = await get_category_descendant_ids(subcategory_id, db)
        query = query.where(or_(
            ProductModel.category_id.in_(subcat_family),
            ProductModel.subcategory_id.in_(subcat_family)
        ))
    elif category_id is not None:
        cat_family = await get_category_descendant_ids(category_id, db)
        query = query.where(or_(
            ProductModel.category_id.in_(cat_family),
            ProductModel.subcategory_id.in_(cat_family)
        ))
        
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
        query = query.where(
            or_(
                ProductModel.discount_percentage >= min_discount,
                and_(ProductModel.mrp.isnot(None), ProductModel.mrp > ProductModel.selling_price)
            )
        )

    # Brand filter (by brand_id or brand name)
    actual_brands = brands if isinstance(brands, (list, tuple, set)) else None
    if actual_brands:
        brand_id_filters = []
        brand_name_filters = []
        for b in actual_brands:
            b_str = str(b).strip()
            if b_str.isdigit():
                brand_id_filters.append(int(b_str))
            elif b_str:
                brand_name_filters.append(b_str)
        brand_clauses = []
        if brand_id_filters:
            brand_clauses.append(ProductModel.brand_id.in_(brand_id_filters))
        if brand_name_filters:
            for bn in brand_name_filters:
                brand_clauses.append(BrandModel.name.ilike(f"%{bn}%"))
        if brand_clauses:
            query = query.where(or_(*brand_clauses))
    
    # Color filter (checks ProductModel.attributes and child variant attributes)
    if colors and isinstance(colors, list):
        color_clauses = []
        for c in colors:
            color_clauses.append(
                or_(
                    cast(ProductModel.attributes['Color'], String).ilike(f'%{c}%'),
                    cast(ProductModel.attributes['Colour'], String).ilike(f'%{c}%'),
                    ProductModel.name.ilike(f'%{c}%'),
                    ProductModel.children.any(
                        or_(
                            cast(ProductModel.attributes['Color'], String).ilike(f'%{c}%'),
                            cast(ProductModel.attributes['Colour'], String).ilike(f'%{c}%'),
                            ProductModel.name.ilike(f'%{c}%')
                        )
                    )
                )
            )
        if color_clauses:
            query = query.where(or_(*color_clauses))
        
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
            pass
    
    # Stock filter - applied in SQL before count & pagination
    if in_stock:
        from models.inventory import ProductInventory
        query = query.where(
            select(ProductInventory.id).where(
                and_(
                    ProductInventory.product_id == ProductModel.id,
                    ProductInventory.stock > 0
                )
            ).exists()
        )
    
    # Total count before pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar_one_or_none() or 0
    if response:
        response.headers["X-Total-Count"] = str(total_count)

    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.selling_price.asc() if sort_order == "asc" else ProductModel.selling_price.desc())
    elif sort_by == "rating":
        query = query.order_by(ProductModel.average_rating.desc())
    elif sort_by == "newest":
        query = query.order_by(ProductModel.created_at.desc())
    elif sort_by == "discount":
        query = query.order_by(ProductModel.discount_percentage.desc().nullslast(), ProductModel.created_at.desc())
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
    products = result.scalars().unique().all()
    await TaxService.apply_dynamic_product_pricing(db, products)
    return products

@router.get("/products/autocomplete", tags=["products"])
async def autocomplete_products(
    q: str = Query(..., min_length=2),
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """Get product name and category suggestions for autocomplete"""
    variations = get_search_variations(q)
    SubcategoryModel = aliased(CategoryModel)
    
    product_clauses = []
    for term in variations:
        product_clauses.extend([
            ProductModel.name.ilike(f"%{term}%"),
            BrandModel.name.ilike(f"%{term}%"),
            and_(CategoryModel.name.ilike(f"%{term}%"), CategoryModel.is_active == True, CategoryModel.is_deleted == False),
            and_(SubcategoryModel.name.ilike(f"%{term}%"), SubcategoryModel.is_active == True, SubcategoryModel.is_deleted == False)
        ])
    
    # Get matching product names
    result = await db.execute(
        select(ProductModel.name, ProductModel.id, ProductModel.selling_price, ProductModel.images)
        .join(DealerModel)
        .outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id)
        .outerjoin(BrandModel, ProductModel.brand_id == BrandModel.id)
        .outerjoin(CategoryModel, ProductModel.category_id == CategoryModel.id)
        .outerjoin(SubcategoryModel, ProductModel.subcategory_id == SubcategoryModel.id)
        .where(
            or_(*product_clauses),
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            ProductModel.is_deleted == False,
            ProductModel.parent_product_id.is_(None),
            or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
        )
        .limit(limit * 2)
    )
    products_raw = result.all()
    
    # Deduplicate products by product ID in Python (since ProductModel.images is JSON)
    seen_ids = set()
    products = []
    for p in products_raw:
        if p[1] not in seen_ids:
            seen_ids.add(p[1])
            products.append(p)
            if len(products) >= limit:
                break
    
    # Extract unique suggestions
    suggestions = list(dict.fromkeys([p[0] for p in products]))[:5]
    
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
    cat_clauses = []
    for term in variations:
        cat_clauses.append(CategoryModel.name.ilike(f"%{term}%"))

    cat_result = await db.execute(
        select(CategoryModel.id, CategoryModel.name)
        .where(
            or_(*cat_clauses),
            CategoryModel.is_active == True,
            CategoryModel.is_deleted == False
        )
        .distinct()
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

@router.post("/products/estimate-payout", response_model=ProductPayoutEstimationResponse, tags=["products"])
async def estimate_product_payout(
    payload: ProductPayoutEstimationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Computes estimated product price breakdown, platform fee deductions, and dealer net payout.
    Referral commission is NOT deducted from the dealer.
    """
    dealer_price = float(payload.dealer_price)
    tax_perc = float(payload.tax_perc if payload.tax_perc is not None else 12.0)
    
    # Calculate base selling price
    if payload.selling_price is not None and float(payload.selling_price) > 0:
        sp_input = float(payload.selling_price)
        mrp_total_est = round(dealer_price * (1.0 + tax_perc / 100.0), 2)
        if sp_input > dealer_price and sp_input <= mrp_total_est:
            selling_base = round(sp_input / (1.0 + tax_perc / 100.0), 2)
        else:
            selling_base = sp_input
        discount_pct = round(((dealer_price - selling_base) / dealer_price) * 100.0, 2) if dealer_price > 0 else 0.0
    elif payload.discount_percentage:
        discount_pct = float(payload.discount_percentage)
        selling_base = round(dealer_price * (1.0 - discount_pct / 100.0), 2)
    else:
        selling_base = dealer_price
        discount_pct = 0.0

    mrp_tax = round(dealer_price * (tax_perc / 100.0), 2)
    mrp_total = round(dealer_price + mrp_tax, 2)
    
    selling_tax = round(selling_base * (tax_perc / 100.0), 2)
    selling_total = round(selling_base + selling_tax, 2)
    
    discount_base = round(dealer_price - selling_base, 2)
    discount_tax = round(mrp_tax - selling_tax, 2)
    discount_total = round(mrp_total - selling_total, 2)

    # Fee Deductions based on active BillingSlabs and FeeConfigurations
    net_basic_dec = Decimal(str(selling_base))
    missing_slab_categories = []

    marketplace_cfg = await get_fee_config(db, "marketplace_fee")
    marketing_cfg = await get_fee_config(db, "marketing_fee")
    logistics_cfg = await get_fee_config(db, "partner_logistics_fee")
    active_tax_cats = await get_all_active_tax_categories(db)
    
    # 1. Marketplace Fee
    mp_slab = await get_applicable_slab(db, "marketplace", net_basic_dec)
    mp_slab_found = mp_slab is not None and mp_slab.dealer_percentage is not None
    if mp_slab_found:
        mp_disp_rate, mp_factor, mp_is_app = resolve_slab_gst_rate(
            mp_slab.gst_type if mp_slab else None,
            "marketplace",
            marketplace_cfg,
            tax_categories=active_tax_cats
        )
        mp_tax_rate = float(mp_disp_rate) if mp_is_app else 0.0
        mp_pct = float(mp_slab.dealer_percentage)
        mp_base = round(selling_base * mp_pct, 2)
        mp_tax = round(float(Decimal(str(mp_base)) * mp_factor), 2) if mp_is_app else 0.0
        mp_total = round(mp_base + mp_tax, 2)
    else:
        mp_tax_rate = 0.0
        mp_pct = None
        mp_base = 0.0
        mp_tax = 0.0
        mp_total = 0.0
        missing_slab_categories.append("marketplace")

    # 2. Marketing Fee
    mkt_slab = await get_applicable_slab(db, "marketing", net_basic_dec)
    mkt_slab_found = mkt_slab is not None and mkt_slab.dealer_percentage is not None
    if mkt_slab_found:
        mkt_disp_rate, mkt_factor, mkt_is_app = resolve_slab_gst_rate(
            mkt_slab.gst_type if mkt_slab else None,
            "marketing",
            marketing_cfg,
            tax_categories=active_tax_cats
        )
        mkt_tax_rate = float(mkt_disp_rate) if mkt_is_app else 0.0
        mkt_pct = float(mkt_slab.dealer_percentage)
        mkt_base = round(selling_base * mkt_pct, 2)
        mkt_tax = round(float(Decimal(str(mkt_base)) * mkt_factor), 2) if mkt_is_app else 0.0
        mkt_total = round(mkt_base + mkt_tax, 2)
    else:
        mkt_tax_rate = 0.0
        mkt_pct = None
        mkt_base = 0.0
        mkt_tax = 0.0
        mkt_total = 0.0
        missing_slab_categories.append("marketing")

    # 3. Shipment / Logistics Fee
    if not payload.is_self_logistics:
        log_slab = await get_applicable_slab(db, "logistics", net_basic_dec)
        log_slab_found = log_slab is not None and log_slab.dealer_percentage is not None
        if log_slab_found:
            log_disp_rate, log_factor, log_is_app = resolve_slab_gst_rate(
                log_slab.gst_type if log_slab else None,
                "logistics",
                logistics_cfg,
                tax_categories=active_tax_cats
            )
            log_tax_rate = float(log_disp_rate) if log_is_app else 0.0
            log_pct = float(log_slab.dealer_percentage)
            log_base = round(selling_base * log_pct, 2)
            log_tax = round(float(Decimal(str(log_base)) * log_factor), 2) if log_is_app else 0.0
            log_total = round(log_base + log_tax, 2)
        else:
            log_tax_rate = 0.0
            log_pct = None
            log_base = 0.0
            log_tax = 0.0
            log_total = 0.0
            missing_slab_categories.append("logistics")
    else:
        log_slab_found = True
        log_pct = 0.0
        log_tax_rate = 0.0
        log_base = 0.0
        log_tax = 0.0
        log_total = 0.0

    deductions = [
        FeeDeductionItem(
            name="Market place",
            category_key="marketplace",
            percentage=round(mp_pct * 100.0, 2) if mp_pct is not None else None,
            base_amount=mp_base,
            tax_rate=mp_tax_rate,
            tax_amount=mp_tax,
            total_amount=mp_total,
            slab_applied=mp_slab_found
        ),
        FeeDeductionItem(
            name="Marketing fee",
            category_key="marketing",
            percentage=round(mkt_pct * 100.0, 2) if mkt_pct is not None else None,
            base_amount=mkt_base,
            tax_rate=mkt_tax_rate,
            tax_amount=mkt_tax,
            total_amount=mkt_total,
            slab_applied=mkt_slab_found
        ),
        FeeDeductionItem(
            name="Shipment fee",
            category_key="logistics",
            percentage=round(log_pct * 100.0, 2) if log_pct is not None else None,
            base_amount=log_base,
            tax_rate=log_tax_rate,
            tax_amount=log_tax,
            total_amount=log_total,
            slab_applied=log_slab_found
        )
    ]

    total_deductions = round(mp_total + mkt_total + log_total, 2)
    estimated_payout = round(selling_total - total_deductions, 2)

    return ProductPayoutEstimationResponse(
        mrp=PriceTaxRow(
            base_price=dealer_price,
            tax_rate=tax_perc,
            tax_amount=mrp_tax,
            total_amount=mrp_total
        ),
        selling_price=PriceTaxRow(
            base_price=selling_base,
            tax_rate=tax_perc,
            tax_amount=selling_tax,
            total_amount=selling_total,
            discount_percentage=discount_pct
        ),
        discount=PriceTaxRow(
            base_price=discount_base,
            tax_rate=tax_perc,
            tax_amount=discount_tax,
            total_amount=discount_total,
            discount_percentage=discount_pct
        ),
        deductions=deductions,
        total_deductions=total_deductions,
        estimated_payout=estimated_payout,
        disclaimer="Estimated payout excludes applicable Section 194-O TDS (0.1% with PAN / 5% without PAN), which is evaluated based on dealer turnover and exemption limits at final settlement.",
        all_slabs_applied=len(missing_slab_categories) == 0,
        missing_slab_categories=missing_slab_categories
    )

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
        
    await TaxService.apply_dynamic_product_pricing(db, product)
    return product

@router.get("/products/{product_id}/payout-estimate", response_model=ProductPayoutEstimationResponse, tags=["products"])
async def get_product_payout_estimate(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get payout estimation breakdown for an existing product.
    """
    product = await db.get(ProductModel, product_id)
    if not product or product.is_deleted:
        raise HTTPException(status_code=404, detail="Product not found")
        
    await TaxService.apply_dynamic_product_pricing(db, product)
    req = ProductPayoutEstimationRequest(
        dealer_price=product.dealer_price,
        tax_perc=product.tax_perc or 12.0,
        discount_percentage=float(product.discount_percentage or 0.0),
        selling_price=product.selling_price
    )
    return await estimate_product_payout(req, db, current_user)

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
