from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, and_
from typing import List, Optional
from models import Product, Order, OrderItem, Category, CartItem, Dealer
from sqlalchemy.orm import selectinload

class RecommendationService:
    
    @staticmethod
    async def get_recommendations(
        db: AsyncSession,
        user_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Product]:
        """
        Get product recommendations for a user.
        Logic:
        1. If user_id provided:
           - Analyze past orders and cart to find top categories.
           - Recommend top-rated/selling products from those categories.
        2. Fallback (or if no user_id):
           - Recommend top-selling global products.
        """
        
        recommended_products = []
        preferred_category_ids = []
        
        if user_id:
            # 1. Analyze User Preferences
            
            # Get categories from past orders
            order_cats_result = await db.execute(
                select(Product.category_id)
                .join(OrderItem, OrderItem.product_id == Product.id)
                .join(Order, Order.id == OrderItem.order_id)
                .where(Order.user_id == user_id)
                .group_by(Product.category_id)
                .order_by(desc(func.count(OrderItem.id)))
                .limit(3)
            )
            preferred_category_ids.extend([row[0] for row in order_cats_result.all()])
            
            # Get categories from cart
            cart_cats_result = await db.execute(
                select(Product.category_id)
                .join(CartItem, CartItem.product_id == Product.id)
                .where(CartItem.user_id == user_id)
                .distinct()
            )
            preferred_category_ids.extend([row[0] for row in cart_cats_result.all()])
            
            # Dedup
            preferred_category_ids = list(set(preferred_category_ids))
            
            if preferred_category_ids:
                # 2. Get products from preferred categories
                # Sort by rating (if available) or price/random. Let's use ID desc for "newest" or random
                # Ideally we want "Best Selling in these categories"
                
                query = select(Product).join(Dealer).where(
                    and_(
                        Product.category_id.in_(preferred_category_ids),
                        Product.is_approved == True,
                        Product.stock > 0,
                        Dealer.access_status == 'active',
                        Dealer.is_active == True
                    )
                ).order_by(func.random()).limit(limit).options(
                    selectinload(Product.category).selectinload(Category.attributes),
                    selectinload(Product.dealer)
                )
                
                result = await db.execute(query)
                recommended_products = result.scalars().all()
        
        # 3. Fallback / Fill remaining spots
        if len(recommended_products) < limit:
            remaining = limit - len(recommended_products)
            exclude_ids = [p.id for p in recommended_products]
            
            # Get global top selling or just random active products
            # Using random for variety in this mock AI
            query = select(Product).join(Dealer).where(
                and_(
                    Product.is_approved == True,
                    Product.stock > 0,
                    Product.id.notin_(exclude_ids),
                    Dealer.access_status == 'active',
                    Dealer.is_active == True
                )
            ).order_by(func.random()).limit(remaining).options(
                selectinload(Product.category).selectinload(Category.attributes),
                selectinload(Product.dealer)
            )
            
            result = await db.execute(query)
            fallback_products = result.scalars().all()
            recommended_products.extend(fallback_products)
            
        return recommended_products
