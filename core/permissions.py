"""
Permission and authorization utilities
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.config import settings
from core.database import get_db
from models.user import User, UserRole
from models.customer_user import CustomerUser

DEALER_ROLES = [
    UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY,
    UserRole.DEALER_ORDERS, UserRole.DEALER_FINANCE
]

HUB_ROLES = [
    UserRole.HUB, UserRole.HUB_MANAGER, UserRole.HUB_STAFF, 
    UserRole.HUB_DISPATCHER, UserRole.HUB_RETURNS
]

LOGISTICS_ROLES = [
    UserRole.LOGISTICS_ADMIN, UserRole.LOGISTICS_MANAGER
]

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        identifier: str = payload.get("sub")
        is_customer: bool = payload.get("is_customer", False)
        if identifier is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from appropriate database table
    if is_customer:
        result = await db.execute(
            select(CustomerUser).where(
                (CustomerUser.email == identifier) | (CustomerUser.phone == identifier)
            )
        )
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(User).where(
                (User.email == identifier) | (User.phone == identifier)
            )
        )
        user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    
    return user

async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> User | None:
    """Get current authenticated user (optional)"""
    if not credentials:
        return None
        
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        identifier: str = payload.get("sub")
        is_customer: bool = payload.get("is_customer", False)
        if identifier is None:
            return None
    except JWTError:
        return None
    
    # Get user from database
    if is_customer:
        result = await db.execute(
            select(CustomerUser).where(
                (CustomerUser.email == identifier) | (CustomerUser.phone == identifier)
            )
        )
    else:
        result = await db.execute(
            select(User).where(
                (User.email == identifier) | (User.phone == identifier)
            )
        )
    
    user = result.scalar_one_or_none()
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def require_role(
    required_roles: list[UserRole],
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Require user to have one of the specified roles"""
    if current_user.role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required roles: {[r.value for r in required_roles]}"
        )
    return current_user

# Convenience functions for specific roles
async def require_super_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require super admin role"""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return current_user

async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin or super admin role"""
    if current_user.role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

async def require_dealer(current_user: User = Depends(get_current_active_user)) -> User:
    """Require any dealer-related role"""
    if current_user.role not in DEALER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dealer access required"
        )
    return current_user

async def require_dealer_manager(current_user: User = Depends(get_current_active_user)) -> User:
    """Require primary dealer or dealer manager role"""
    if current_user.role not in [UserRole.DEALER, UserRole.DEALER_MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dealer manager access required"
        )
    return current_user

async def require_inventory_access(current_user: User = Depends(get_current_active_user)) -> User:
    """Require inventory or manager access"""
    if current_user.role not in [UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_INVENTORY]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inventory management access required"
        )
    return current_user

async def require_order_access(current_user: User = Depends(get_current_active_user)) -> User:
    """Require order processing or manager access"""
    if current_user.role not in [UserRole.DEALER, UserRole.DEALER_MANAGER, UserRole.DEALER_ORDERS]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Order processing access required"
        )
    return current_user

async def require_hub(current_user: User = Depends(get_current_active_user)) -> User:
    """Require any hub-related role"""
    if current_user.role not in HUB_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hub access required"
        )
    return current_user

async def require_logistics(current_user: User = Depends(get_current_active_user)) -> User:
    """Require any logistics-related role"""
    if current_user.role not in LOGISTICS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Logistics access required"
        )
    return current_user

async def require_logistics_or_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require logistics or admin access"""
    if current_user.role not in LOGISTICS_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Logistics or Admin access required"
        )
    return current_user

async def require_dealer_or_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require dealer or admin access"""
    if current_user.role not in DEALER_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN, UserRole.DEALER]:
        # UserRole.DEALER is usually in DEALER_ROLES but being explicit is safer
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dealer or Admin access required"
        )
    return current_user

def check_dealer_or_admin(user: User) -> bool:
    """Check if user is dealer or admin"""
    return user.role in DEALER_ROLES + [UserRole.ADMIN, UserRole.SUPER_ADMIN]

def is_online_payment_method(payment_method: str) -> bool:
    """Check if payment method is an online/prepaid method (not COD)"""
    if not payment_method:
        return False
    # Standardize and check against COD variations
    pm = payment_method.lower().strip()
    return pm not in ("cod", "cash_on_delivery", "cash")
