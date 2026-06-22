from typing import Optional, List, Union, Any
from datetime import datetime
from pydantic import BaseModel, field_validator

# Category Schemas
class CategoryAttributeBase(BaseModel):
    name: str
    is_mandatory: bool = True
    datatype: str = "string"
    allowed_values: Optional[List[str]] = None

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

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None

class CategoryAttributeUpdate(BaseModel):
    name: Optional[str] = None
    is_mandatory: Optional[bool] = None
    datatype: Optional[str] = None
    allowed_values: Optional[List[str]] = None

class Category(CategoryBase):
    id: int
    created_at: datetime
    is_active: bool
    attributes: Optional[List[CategoryAttribute]] = None

    class Config:
        from_attributes = True



class ColorImage(BaseModel):
    color: str
    is_available: bool = True
    image_urls: List[str]

# Product Schemas
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    discount_price: Optional[float] = None
    stock: int = 0
    category_id: int
    dealer_id: Optional[int] = None
    images: List[Union[ColorImage, str]]
    subcategory: str
    gender: str
    brand: str
    sizes: List[str]
    hsn_code: str
    tax_rule_id: int
    discount_percentage: Optional[int] = None
    average_rating: Optional[float] = None
    attributes: Optional[dict] = None
    color: Optional[str] = None
    parent_product_id: Optional[int] = None
    
    # Return & Exchange Policy
    # Return & Exchange Policy
    is_returnable: bool = True
    return_window_days: int = 14
    is_exchangeable: bool = True
    return_policy_note: Optional[str] = None
    estimated_delivery_days: Optional[int] = None
    dealer_delivery_days: Optional[int] = None # Fallback from dealer if product-specific is null


    @field_validator('images')
    @classmethod
    def images_must_not_be_empty(cls, v: List[Any]) -> List[Any]:
        if not v or len(v) == 0:
            raise ValueError('At least one product image is required')
        return v


class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    stock: Optional[int] = None
    category_id: Optional[int] = None
    subcategory: Optional[str] = None
    brand: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    images: Optional[List[Union[ColorImage, str]]] = None
    attributes: Optional[dict] = None
    is_returnable: Optional[bool] = None
    return_window_days: Optional[int] = None
    is_exchangeable: Optional[bool] = None
    return_policy_note: Optional[str] = None
    hsn_code: Optional[str] = None
    tax_rule_id: Optional[int] = None
    parent_product_id: Optional[int] = None
class Product(ProductBase):
    id: int
    is_approved: bool
    created_at: datetime
    category: Optional[Category] = None
    children: Optional[List['Product']] = []
    hub_stock: Optional[int] = None

    class Config:
        from_attributes = True
