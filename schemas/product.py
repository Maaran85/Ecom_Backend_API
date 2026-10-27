from typing import Optional, List, Union, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator

# Category Schemas
class CategoryAttributeBase(BaseModel):
    name: str
    is_mandatory: bool = True
    is_variant_key: bool = False
    datatype: str = "string"
    allowed_values: Optional[List[str]] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_filter: Optional[bool] = False

class CategoryAttributeCreate(CategoryAttributeBase):
    pass

class CategoryAttribute(CategoryAttributeBase):
    id: int
    category_id: int

    class Config:
        from_attributes = True

class CategoryBase(BaseModel):
    name: str
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: bool = True
    is_spec_group: bool = False

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_spec_group: Optional[bool] = None

class CategoryAttributeUpdate(BaseModel):
    name: Optional[str] = None
    is_mandatory: Optional[bool] = None
    is_variant_key: Optional[bool] = None
    datatype: Optional[str] = None
    allowed_values: Optional[List[str]] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_filter: Optional[bool] = None

class Category(CategoryBase):
    id: int
    created_at: datetime
    is_active: bool
    attributes: Optional[List[CategoryAttribute]] = None

    class Config:
        from_attributes = True



# Brand Schemas
class BrandBase(BaseModel):
    name: str
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

class BrandCreate(BrandBase):
    subcategory_id: Optional[int] = None

class BrandUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Brand(BrandBase):
    id: int
    
    class Config:
        from_attributes = True

# Product Schemas

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    sku: Optional[str] = None
    dealer_price: Optional[float] = None
    selling_price: Optional[float] = None
    mrp: Optional[float] = None
    discount_price: Optional[float] = None
    tax_perc: Optional[float] = None
    tax_price: Optional[float] = None
    stock: int = 0
    category_id: Optional[int] = None
    dealer_id: Optional[UUID] = None
    images: Optional[List[str]] = None
    subcategory_id: Optional[int] = None
    brand_id: Optional[int] = None
    hsn_code: Optional[str] = None
    tax_category_id: Optional[int] = None
    discount_percentage: Optional[int] = None
    average_rating: Optional[float] = None
    reject_reasons: Optional[List[dict]] = []
    attributes: Optional[dict] = None
    parent_product_id: Optional[UUID] = None
    
    # Return & Exchange Policy
    # Return & Exchange Policy
    is_returnable: bool = True
    return_window_days: int = 14
    is_exchangeable: bool = True
    return_policy_note: Optional[str] = None
    estimated_delivery_days: Optional[int] = None
    dealer_delivery_days: Optional[int] = None # Fallback from dealer if product-specific is null
    referral_commission_rate: Optional[float] = None # Optional product-level override rate


    @field_validator('images')
    @classmethod
    def images_must_not_be_empty(cls, v: List[Any]) -> List[Any]:
        if not v or len(v) == 0:
            return ["https://via.placeholder.com/300"]
        return v


class ChildProductCreate(BaseModel):
    id: Optional[UUID] = None
    sku: Optional[str] = None
    dealer_price: Optional[float] = None
    selling_price: Optional[float] = None
    mrp: Optional[float] = None
    tax_perc: Optional[float] = None
    tax_price: Optional[float] = None
    discount_price: Optional[float] = None
    discount_percentage: Optional[int] = None
    price_adjustment: Optional[float] = 0.0 # Kept for UI compatibility
    attributes: dict = {}
    images: Optional[List[str]] = []

class ProductCreate(ProductBase):
    variants: Optional[List[ChildProductCreate]] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sku: Optional[str] = None
    dealer_price: Optional[float] = None
    selling_price: Optional[float] = None
    mrp: Optional[float] = None
    discount_price: Optional[float] = None
    tax_perc: Optional[float] = None
    tax_price: Optional[float] = None
    discount_percentage: Optional[int] = None
    stock: Optional[int] = None
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
    brand_id: Optional[int] = None
    images: Optional[List[str]] = None
    attributes: Optional[dict] = None
    is_returnable: Optional[bool] = None
    return_window_days: Optional[int] = None
    is_exchangeable: Optional[bool] = None
    return_policy_note: Optional[str] = None
    hsn_code: Optional[str] = None
    tax_category_id: Optional[int] = None
    parent_product_id: Optional[UUID] = None
    referral_commission_rate: Optional[float] = None
    variants: Optional[List[ChildProductCreate]] = None

class Product(ProductBase):
    id: UUID
    is_approved: bool
    created_at: datetime
    category: Optional[Category] = None
    brand: Optional[Brand] = None
    children: Optional[List['Product']] = []
    hub_stock: Optional[int] = None

    class Config:
        from_attributes = True

# Deduction & Payout Estimation Schemas
class FeeDeductionItem(BaseModel):
    name: str
    category_key: str
    percentage: Optional[float] = None
    base_amount: float
    tax_rate: float
    tax_amount: float
    total_amount: float
    slab_applied: Optional[bool] = True

class PriceTaxRow(BaseModel):
    base_price: float
    tax_rate: float
    tax_amount: float
    total_amount: float
    discount_percentage: Optional[float] = None

class ProductPayoutEstimationRequest(BaseModel):
    dealer_price: float # Base MRP (Excl Tax)
    tax_perc: Optional[float] = 12.0
    discount_percentage: Optional[float] = 0.0
    selling_price: Optional[float] = None # Base selling price (excl tax)
    is_self_logistics: Optional[bool] = False

class ProductPayoutEstimationResponse(BaseModel):
    mrp: PriceTaxRow
    selling_price: PriceTaxRow
    discount: PriceTaxRow
    deductions: List[FeeDeductionItem]
    total_deductions: float
    estimated_payout: float
    disclaimer: str = "This is estimated payment. Final payout will be after deductions and settlement"
    all_slabs_applied: Optional[bool] = True
    missing_slab_categories: Optional[List[str]] = []

