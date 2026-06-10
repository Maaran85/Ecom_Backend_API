from pydantic import BaseModel, conint
from typing import Optional
from datetime import datetime

class RiderReviewBase(BaseModel):
    rider_id: int
    order_item_id: Optional[int] = None
    rating: int # 1 to 5
    comment: Optional[str] = None

class RiderReviewCreate(RiderReviewBase):
    pass

class RiderReview(RiderReviewBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True
