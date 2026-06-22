from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.inventory import MovementType

# Stock Movement
class StockMovementResponse(BaseModel):
    id: int
    product_id: int
    movement_type: MovementType
    quantity: int
    stock_before: int
    stock_after: int
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None
    user_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# Stock Alert
class StockAlertCreate(BaseModel):
    product_id: int
    threshold: int = Field(default=10, ge=0)
    notify_admin: bool = True
    notify_dealer: bool = True

class StockAlertUpdate(BaseModel):
    threshold: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    notify_admin: Optional[bool] = None
    notify_dealer: Optional[bool] = None

class StockAlert(BaseModel):
    id: int
    product_id: int
    threshold: int
    is_active: bool
    last_alerted_at: Optional[datetime] = None
    notify_admin: bool
    notify_dealer: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Bulk Stock Update
class BulkStockUpdateItem(BaseModel):
    product_id: int
    quantity: int = Field(..., description="New stock quantity")
    notes: Optional[str] = None

class BulkStockUpdateRequest(BaseModel):
    updates: List[BulkStockUpdateItem]

class BulkStockUpdateResponse(BaseModel):
    success_count: int
    failed_count: int
    results: List[dict]

class HubStockAdd(BaseModel):
    product_id: int
    quantity: int = Field(..., description="Quantity of stock to add")
