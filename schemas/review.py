from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Review Schemas
class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5)  # 1-5 stars
    title: Optional[str] = None
    comment: Optional[str] = None
    images: Optional[List[str]] = None

class ReviewCreate(ReviewBase):
    product_id: UUID

class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    title: Optional[str] = None
    comment: Optional[str] = None
    images: Optional[List[str]] = None

class Review(ReviewBase):
    id: int
    product_id: UUID
    customer_id: int
    order_id: Optional[int] = None
    is_verified_purchase: bool
    is_approved: bool
    helpful_count: int
    images: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ReviewWithUser(Review):
    """Review with user information"""
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None

    class Config:
        from_attributes = True

# Review Vote Schemas
class ReviewVoteCreate(BaseModel):
    is_helpful: bool

class ReviewVote(BaseModel):
    id: int
    review_id: int
    customer_id: int
    is_helpful: bool
    created_at: datetime

    class Config:
        from_attributes = True
