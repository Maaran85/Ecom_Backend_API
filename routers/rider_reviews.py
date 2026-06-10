from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.database import get_db
from core.permissions import get_current_active_user
from models import User, DeliveryRider, RiderReview, OrderItem
from schemas.rider_review import RiderReviewCreate, RiderReview as RiderReviewSchema

router = APIRouter()

@router.post("/review", response_model=RiderReviewSchema)
async def create_rider_review(
    review: RiderReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a review for a delivery rider"""
    
    # 1. Check if rider exists
    rider_result = await db.execute(select(DeliveryRider).where(DeliveryRider.id == review.rider_id))
    rider = rider_result.scalar_one_or_none()
    if not rider:
        raise HTTPException(status_code=404, detail="Delivery rider not found")
    
    # 2. Check if the user had a relevant order with this rider
    if review.order_item_id:
        item_result = await db.execute(
            select(OrderItem)
            .where(OrderItem.id == review.order_item_id)
            .where(OrderItem.rider_id == review.rider_id)
            .where(OrderItem.status == "delivered")
        )
        item = item_result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=400, detail="Invalid order item for this rider")
            
        # Optional: check if already reviewed
        existing_result = await db.execute(
            select(RiderReview).where(RiderReview.order_item_id == review.order_item_id)
        )
        if existing_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="You have already reviewed this delivery")

    # 3. Create review
    new_review = RiderReview(
        rider_id=review.rider_id,
        user_id=current_user.id,
        order_item_id=review.order_item_id,
        rating=review.rating,
        comment=review.comment
    )
    db.add(new_review)
    
    # 4. Update Rider average rating
    # Re-calculate average (could be done via trigger or here)
    total_reviews = rider.total_reviews + 1
    new_avg = ((rider.average_rating * rider.total_reviews) + review.rating) / total_reviews
    
    rider.total_reviews = total_reviews
    rider.average_rating = round(new_avg, 1)
    
    await db.commit()
    await db.refresh(new_review)
    return new_review
