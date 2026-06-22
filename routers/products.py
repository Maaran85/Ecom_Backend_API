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
from schemas.product import (
    Product, ProductCreate, ProductUpdate, 
    Category, CategoryCreate, CategoryUpdate, CategoryAttribute, CategoryAttributeCreate, CategoryAttributeUpdate
)
from models.product import Product as ProductModel, Category as CategoryModel, CategoryAttribute as CategoryAttributeModel
from models.search_history import SearchHistory as SearchHistoryModel
from models.user import UserRole
from models.dealer import Dealer as DealerModel
from models.partner import Partner as PartnerModel
from models.inventory import ProductInventory as ProductInventoryModel
from schemas.search_history import SearchHistory
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
        await db.commit()
        await db.refresh(db_category)
        
        # Manually construct response to avoid lazy-loading issues in async
        return {
            "id": db_category.id,
            "name": db_category.name,
            "image_url": db_category.image_url,
            "parent_id": db_category.parent_id,
            "is_active": db_category.is_active,
            "created_at": db_category.created_at,
            "attributes": []
        }
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
    query = select(CategoryModel)
    
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
    result = await db.execute(select(CategoryModel).where(CategoryModel.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    update_data = category_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_category, key, value)
    
    await db.commit()
    await db.refresh(db_category)
    return {
        "id": db_category.id,
        "name": db_category.name,
        "image_url": db_category.image_url,
        "parent_id": db_category.parent_id,
        "is_active": db_category.is_active,
        "created_at": db_category.created_at,
        "attributes": [] # Attributes can be loaded if needed, but [] is safe for simple update
    }

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
    
    # Check if category has products
    products_count = await db.execute(select(func.count(ProductModel.id)).where(ProductModel.category_id == category_id))
    if products_count.scalar() > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category with associated products")
    
    # Check if category has subcategories
    subdirs_count = await db.execute(select(func.count(CategoryModel.id)).where(CategoryModel.parent_id == category_id))
    if subdirs_count.scalar() > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category with subcategories")

    await db.delete(db_category)
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
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    )
    
    # Price filters
    if min_price is not None:
        query = query.where(ProductModel.price >= min_price)
    if max_price is not None:
        query = query.where(ProductModel.price <= max_price)
    
    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.price.asc() if sort_order == "asc" else ProductModel.price.desc())
    elif sort_by == "rating":
        query = query.order_by(ProductModel.average_rating.desc())
    elif sort_by == "newest":
        query = query.order_by(ProductModel.created_at.desc())
    else:  # name
        query = query.order_by(ProductModel.name.asc())
    
    query = query.offset(skip).limit(limit).options(
        joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
        joinedload(ProductModel.dealer)
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
        "datatype": db_attribute.datatype,
        "allowed_values": db_attribute.allowed_values
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
        "datatype": db_attribute.datatype,
        "allowed_values": db_attribute.allowed_values
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
    res = await db.execute(select(CategoryModel.id, CategoryModel.parent_id))
    all_cats = res.all()
    
    # Adjacency maps
    children_map = {}
    parent_map = {}
    for cid, pid in all_cats:
        if pid not in children_map:
            children_map[pid] = []
        children_map[pid].append(cid)
        parent_map[cid] = pid
        
    # Upward (parents)
    related_ids = set()
    curr = category_id
    while curr is not None:
        related_ids.add(curr)
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
                datatype=attr.datatype,
                allowed_values=list(attr.allowed_values) if attr.allowed_values else []
            )
        else:
            if attr.allowed_values:
                existing = merged[attr.name].allowed_values
                for val in attr.allowed_values:
                    if val not in existing:
                        existing.append(val)
                merged[attr.name].allowed_values = existing

    return list(merged.values())

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

    # Fetch mandatory attributes (including from parents)
    hierarchy = select(CategoryModel.id, CategoryModel.parent_id).where(CategoryModel.id == product_in.category_id).cte(name="hierarchy", recursive=True)
    alias = aliased(CategoryModel)
    hierarchy = hierarchy.union_all(
        select(alias.id, alias.parent_id).where(alias.id == hierarchy.c.parent_id)
    )
    attr_result = await db.execute(
        select(CategoryAttributeModel)
        .where(CategoryAttributeModel.category_id.in_(select(hierarchy.c.id)))
    )
    required_attributes = [attr for attr in attr_result.scalars().all() if attr.is_mandatory]
    
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
        if current_user.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN] and product_in.dealer_id:
             db_product.dealer_id = product_in.dealer_id
        else:
             raise HTTPException(status_code=400, detail="Dealer ID is required for product creation.")

    db.add(db_product)
    await db.flush() # Get product ID without committing
    
    # --- Parent-Child Variant Auto-Generation ---
    # If there are multiple sizes or colors, create child products for each combination
    colors = []
    for img in product_in.images:
        if isinstance(img, dict) and "color" in img and img["color"] != "Default":
            colors.append(img["color"])
    
    if not colors:
        colors = ["Default"]
        
    sizes = product_in.sizes if product_in.sizes else ["One Size"]
    
    # We only auto-generate children if there's more than 1 combination
    if len(sizes) > 1 or len(colors) > 1 or (len(sizes) == 1 and len(colors) == 1 and colors[0] != "Default"):
        for size in sizes:
            for color in colors:
                # Find images for this specific color
                color_images = []
                for img in product_in.images:
                    if isinstance(img, dict) and img.get("color") == color:
                        color_images = [img]
                        break
                
                if not color_images and product_in.images:
                    # Fallback to first image group if specific color not found
                    color_images = [product_in.images[0]]

                child_data = product_data.copy()
                child_data["parent_product_id"] = db_product.id
                child_data["sizes"] = [size]
                child_data["color"] = color
                child_data["images"] = color_images
                child_data["name"] = f"{db_product.name} ({size}, {color})"
                
                db_child = ProductModel(**child_data)
                db_child.dealer_id = db_product.dealer_id
                db.add(db_child)

    await db.commit()
    await db.refresh(db_product)
    
    # Fetch product with category and variants loaded for response
    result = await db.execute(
        select(ProductModel)
        .where(ProductModel.id == db_product.id)
        .options(
            joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.dealer),
            selectinload(ProductModel.children)
        )
    )
    return result.scalar_one()

@router.put("/products/{product_id}", response_model=Product, tags=["products"])
async def update_product(
    product_id: int, 
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
    for key, value in update_data.items():
        setattr(db_product, key, value)


    await db.commit()
    await db.refresh(db_product)
    
    # Return with relations loaded
    result = await db.execute(
        select(ProductModel)
        .where(ProductModel.id == db_product.id)
        .options(
            joinedload(ProductModel.category).selectinload(CategoryModel.attributes),
            joinedload(ProductModel.dealer),
            selectinload(ProductModel.children)
        )
    )
    return result.scalar_one()


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["products"])
async def delete_product(
    product_id: int, 
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

    await db.delete(db_product)
    await db.commit()
    return None

@router.get("/products", response_model=List[Product], tags=["products"])
async def get_products(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
    category_id: Optional[int] = None,
    dealer_id: Optional[int] = Query(None),
    hub_id: Optional[int] = Query(None),
    search: Optional[str] = None,
    is_approved: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get all products with pagination, search, and category filter"""
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id)
    
    # If no specific dealer is requested, show only active/approved products (Public view)
    if not dealer_id:
        query = query.where(
            DealerModel.access_status == 'active',
            DealerModel.is_active == True, DealerModel.is_deleted == False,
            ProductModel.is_approved == True,
            or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
        )

    
    if category_id:
        hierarchy = select(CategoryModel.id).where(CategoryModel.id == category_id).cte(name="hierarchy", recursive=True)
        alias = aliased(CategoryModel)
        hierarchy = hierarchy.union_all(
            select(alias.id).where(alias.parent_id == hierarchy.c.id)
        )
        query = query.where(ProductModel.category_id.in_(select(hierarchy.c.id)))
    
    if dealer_id:
        # For a specific dealer, show ALL their products including pending ones
        query = query.where(ProductModel.dealer_id == dealer_id)

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
        selectinload(ProductModel.children)
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
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    min_discount: Optional[int] = None,
    brands: Optional[List[str]] = Query(None),
    colors: Optional[List[str]] = Query(None),
    gender: Optional[str] = None,
    attributes: Optional[str] = None, # JSON string of selected dynamic attribute filters
    in_stock: bool = False,
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
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    )
    
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
                
        query = query.where(ProductModel.category_id.in_(list(visited)))
    
    # Price range
    if min_price is not None:
        query = query.where(ProductModel.price >= min_price)
    if max_price is not None:
        query = query.where(ProductModel.price <= max_price)
    
    # Rating filter
    if min_rating is not None:
        query = query.where(ProductModel.average_rating >= min_rating)
    
    # Discount filter
    if min_discount is not None:
        query = query.where(ProductModel.discount_percentage >= min_discount)

    # Brand filter
    if brands:
        query = query.where(ProductModel.brand.in_(brands))
    
    # Color filter
    if colors:
        query = query.where(ProductModel.color.in_(colors))
    
    # Gender filter
    if gender:
        query = query.where(ProductModel.gender == gender)
        
    # Dynamic Attributes Filter
    # attributes param comes as JSON string e.g. '{"RAM":["8GB","12GB"],"Storage":["128GB"]}'
    if attributes:
        try:
            attr_filters = json.loads(attributes)
            for attr_key, attr_values in attr_filters.items():
                if attr_values and isinstance(attr_values, list):
                    # We need to check if the JSON value stored at attr_key is in the list attr_values
                    # For PostgreSQL JSONB, we cast to String. Because the JSON element returns a string wrapped in quotes (e.g. "\"8GB\""), we wrap our values.
                    query = query.where(cast(ProductModel.attributes[attr_key], String).in_([f'"{v}"' for v in attr_values]))
        except (json.JSONDecodeError, TypeError):
            print(f"DEBUG: Failed to parse attributes JSON: {attributes}")
            pass
    
    # Stock filter
    if in_stock:
        query = query.where(ProductModel.stock > 0)
    
    # Sorting
    if sort_by == "price":
        query = query.order_by(ProductModel.price.asc() if sort_order == "asc" else ProductModel.price.desc())
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
        selectinload(ProductModel.children)
    )
    
    result = await db.execute(query)
    products = result.scalars().all()
    
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
        select(ProductModel.name, ProductModel.id, ProductModel.price, ProductModel.images)
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
        DealerModel.access_status == 'active',
        DealerModel.is_active == True, DealerModel.is_deleted == False,
        ProductModel.is_approved == True,
        or_(DealerModel.partner_id == None, PartnerModel.is_active == True)
    )
    if category_id:
        hierarchy = select(CategoryModel.id).where(CategoryModel.id == category_id).cte(name="hierarchy", recursive=True)
        alias = aliased(CategoryModel)
        hierarchy = hierarchy.union_all(
            select(alias.id).where(alias.parent_id == hierarchy.c.id)
        )
        query = query.where(ProductModel.category_id.in_(select(hierarchy.c.id)))
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    if not products:
        return {
            "price_range": {"min": 0, "max": 0},
            "rating_distribution": {}
        }
    
    # Calculate price range
    prices = [p.price for p in products]
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
    brands = sorted(list(set(p.brand for p in products if p.brand)))
    colors = sorted(list(set(p.color for p in products if p.color)))
    
    return {
        "price_range": price_range,
        "rating_distribution": rating_distribution,
        "brands": brands,
        "colors": colors,
        "total_products": len(products),
        "in_stock_count": len([p for p in products if p.stock > 0])
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
    product_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get a single product by ID. Dealers and Admins can see pending products."""
    query = select(ProductModel).join(DealerModel).outerjoin(PartnerModel, DealerModel.partner_id == PartnerModel.id).where(ProductModel.id == product_id)
    
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
            from sqlalchemy import or_
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
            joinedload(ProductModel.dealer),
            selectinload(ProductModel.children)
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
    CSV Header: name,description,price,stock,category_id,images,discount_price
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
            if not row.get('name') or not row.get('price') or not row.get('category_id'):
                raise ValueError("Missing required fields (name, price, category_id)")
             
            # Parse numeric fields safely
            try:
                price = float(row['price'])
                stock = int(row.get('stock', 0))
                category_id = int(row['category_id'])
                discount_price_str = row.get('discount_price')
                discount_price = float(discount_price_str) if discount_price_str else None
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
                price=price,
                discount_price=discount_price,
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
