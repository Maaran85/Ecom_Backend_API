"""
Product reviews and ratings router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, Review, ReviewVote, Product, Order, OrderItem, CustomerUser
from schemas.review import ReviewCreate, ReviewUpdate, Review as ReviewSchema, ReviewWithUser, ReviewVoteCreate

router = APIRouter()

@router.post("", response_model=ReviewSchema, status_code=status.HTTP_201_CREATED)
async def create_review(
    review_data: ReviewCreate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create product review"""
    
    # Check if product exists
    result = await db.execute(select(Product).where(Product.id == review_data.product_id))
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Check if user already reviewed this product
    result = await db.execute(
        select(Review).where(
            Review.product_id == review_data.product_id,
            Review.customer_id == current_user.id
        )
    )
    existing_review = result.scalar_one_or_none()
    
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have already reviewed this product"
        )
    
    # Check if user purchased this product (for verified purchase badge)
    is_verified = False
    order_id = None
    result = await db.execute(
        select(OrderItem).join(Order).where(
            Order.customer_id == current_user.id,
            OrderItem.product_id == review_data.product_id
        )
    )
    order_item = result.scalar_one_or_none()
    if order_item:
        is_verified = True
        order_id = order_item.order_id
    
    review = Review(
        product_id=review_data.product_id,
        customer_id=current_user.id,
        order_id=order_id,
        rating=review_data.rating,
        title=review_data.title,
        comment=review_data.comment,
        images=review_data.images,
        is_verified_purchase=is_verified
    )
    
    db.add(review)
    await db.commit()
    await db.refresh(review)
    
    return review

@router.get("/product/{product_id}", response_model=list[ReviewWithUser])
async def get_product_reviews(
    product_id: int,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get all reviews for a product"""
    # Eagerly load the user to avoid N+1 queries
    from sqlalchemy.orm import selectinload
    
    result = await db.execute(
        select(Review)
        .where(
            Review.product_id == product_id,
            Review.is_approved == True
        )
        .options(selectinload(Review.customer))
        .offset(skip)
        .limit(limit)
    )
    reviews = result.scalars().all()
    
    # Transform to schema
    enriched_reviews = []
    for review in reviews:
        # Customer is already loaded
        customer = review.customer
        
        enriched_review = {
            **review.__dict__,
            "user_name": customer.full_name if customer else "Anonymous",
            "user_email": customer.email if customer else None
        }
        enriched_reviews.append(enriched_review)
    
    return enriched_reviews

@router.get("/{review_id}", response_model=ReviewSchema)
async def get_review(
    review_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get specific review"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    return review

@router.put("/{review_id}", response_model=ReviewSchema)
async def update_review(
    review_id: int,
    review_data: ReviewUpdate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update own review"""
    result = await db.execute(
        select(Review).where(
            Review.id == review_id,
            Review.customer_id == current_user.id
        )
    )
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    for field, value in review_data.model_dump(exclude_unset=True).items():
        setattr(review, field, value)
    
    await db.commit()
    await db.refresh(review)
    
    return review

@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: int,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete own review"""
    result = await db.execute(
        select(Review).where(
            Review.id == review_id,
            Review.customer_id == current_user.id
        )
    )
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    await db.delete(review)
    await db.commit()
    
    return None

@router.post("/{review_id}/vote", status_code=status.HTTP_201_CREATED)
async def vote_review(
    review_id: int,
    vote_data: ReviewVoteCreate,
    current_user: CustomerUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Vote if review is helpful"""
    
    # Check if review exists
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    # Check if user already voted
    result = await db.execute(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id,
            ReviewVote.customer_id == current_user.id
        )
    )
    existing_vote = result.scalar_one_or_none()
    
    if existing_vote:
        # Update existing vote
        existing_vote.is_helpful = vote_data.is_helpful
    else:
        # Create new vote
        vote = ReviewVote(
            review_id=review_id,
            customer_id=current_user.id,
            is_helpful=vote_data.is_helpful
        )
        db.add(vote)
    
    # Update helpful count
    result = await db.execute(
        select(func.count(ReviewVote.id)).where(
            ReviewVote.review_id == review_id,
            ReviewVote.is_helpful == True
        )
    )
    helpful_count = result.scalar()
    review.helpful_count = helpful_count
    
    await db.commit()
    
    return {"message": "Vote recorded"}

@router.put("/{review_id}/approve", response_model=ReviewSchema)
async def approve_review(
    review_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve review (admin only)"""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found"
        )
    
    review.is_approved = True
    await db.commit()
    await db.refresh(review)
    
    return review
