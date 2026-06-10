"""
Notifications Router - User Notifications, Preferences, Admin Broadcasting
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from datetime import datetime
from typing import List, Optional

from core.database import get_db
from core.permissions import get_current_active_user, require_admin
from models import User, CustomerUser, Notification, NotificationPreference, CustomerNotificationPreference, NotificationType, NotificationChannel
from models.user import UserRole
from schemas.notification import (
    NotificationResponse, NotificationCreate, BroadcastNotificationRequest,
    NotificationPreferenceUpdate, NotificationPreference as NotificationPreferenceSchema,
    NotificationStats
)

router = APIRouter()

# ==================== USER NOTIFICATIONS ====================

@router.get("/notifications", response_model=List[NotificationResponse])
async def get_my_notifications(
    is_read: Optional[bool] = None,
    notification_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's notifications"""
    
    if getattr(current_user, 'is_customer', False):
        query = select(Notification).where(Notification.customer_id == current_user.id)
    else:
        query = select(Notification).where(Notification.user_id == current_user.id)
    
    if is_read is not None:
        query = query.where(Notification.is_read == is_read)
    
    if notification_type:
        try:
            query = query.where(Notification.type == NotificationType(notification_type))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type: {notification_type}"
            )
    
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return notifications

@router.get("/notifications/unread")
async def get_unread_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get unread notification count"""
    
    if getattr(current_user, 'is_customer', False):
        filter_clause = Notification.customer_id == current_user.id
    else:
        filter_clause = Notification.user_id == current_user.id

    result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(
                filter_clause,
                Notification.is_read == False
            )
        )
    )
    count = result.scalar()
    
    return {"unread_count": count}

@router.put("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark notification as read"""
    
    if getattr(current_user, 'is_customer', False):
        filter_clause = Notification.customer_id == current_user.id
    else:
        filter_clause = Notification.user_id == current_user.id

    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                filter_clause
            )
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
    
    return notification

@router.put("/notifications/read-all")
async def mark_all_as_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read"""
    
    if getattr(current_user, 'is_customer', False):
        filter_clause = Notification.customer_id == current_user.id
    else:
        filter_clause = Notification.user_id == current_user.id

    result = await db.execute(
        select(Notification).where(
            and_(
                filter_clause,
                Notification.is_read == False
            )
        )
    )
    notifications = result.scalars().all()
    
    count = 0
    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        count += 1
    
    await db.commit()
    
    return {"message": f"Marked {count} notifications as read"}

@router.delete("/notifications/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete notification"""
    
    if getattr(current_user, 'is_customer', False):
        filter_clause = Notification.customer_id == current_user.id
    else:
        filter_clause = Notification.user_id == current_user.id

    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.id == notification_id,
                filter_clause
            )
        )
    )
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    await db.delete(notification)
    await db.commit()
    
    return {"message": "Notification deleted successfully"}

# ==================== NOTIFICATION PREFERENCES ====================

@router.get("/notifications/preferences", response_model=NotificationPreferenceSchema)
async def get_notification_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's notification preferences"""
    
    is_customer = getattr(current_user, 'is_customer', False)
    pref_model = CustomerNotificationPreference if is_customer else NotificationPreference
    user_id_field = pref_model.customer_id if is_customer else pref_model.user_id

    result = await db.execute(
        select(pref_model).where(user_id_field == current_user.id)
    )
    preferences = result.scalar_one_or_none()
    
    # Create default preferences if not exists
    if not preferences:
        if is_customer:
            preferences = CustomerNotificationPreference(customer_id=current_user.id)
        else:
            preferences = NotificationPreference(user_id=current_user.id)
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)
    
    return preferences

@router.put("/notifications/preferences", response_model=NotificationPreferenceSchema)
async def update_notification_preferences(
    preferences_data: NotificationPreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's notification preferences"""
    
    is_customer = getattr(current_user, 'is_customer', False)
    pref_model = CustomerNotificationPreference if is_customer else NotificationPreference
    user_id_field = pref_model.customer_id if is_customer else pref_model.user_id

    result = await db.execute(
        select(pref_model).where(user_id_field == current_user.id)
    )
    preferences = result.scalar_one_or_none()
    
    # Create if not exists
    if not preferences:
        if is_customer:
            preferences = CustomerNotificationPreference(customer_id=current_user.id)
        else:
            preferences = NotificationPreference(user_id=current_user.id)
        db.add(preferences)
    
    # Update fields
    update_data = preferences_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preferences, field, value)
    
    await db.commit()
    await db.refresh(preferences)
    
    return preferences

# ==================== ADMIN ENDPOINTS ====================

@router.post("/admin/notifications/send", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def send_notification(
    notification_data: NotificationCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send notification to a specific user or customer (admin only)"""
    
    if not notification_data.user_id and not notification_data.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either user_id or customer_id must be provided"
        )
        
    if notification_data.user_id:
        user_result = await db.execute(select(User).where(User.id == notification_data.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
    if notification_data.customer_id:
        cust_result = await db.execute(select(CustomerUser).where(CustomerUser.id == notification_data.customer_id))
        customer = cust_result.scalar_one_or_none()
        if not customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
    # Create notification
    notification = Notification(
        **notification_data.model_dump(),
        is_sent=True,
        sent_at=datetime.utcnow()
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    return notification

@router.post("/admin/notifications/broadcast")
async def broadcast_notification(
    broadcast_data: BroadcastNotificationRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Broadcast notification to users, customers or roles (admin only)"""
    
    notifications_created = 0
    
    # Handle Role-based broadcast
    if broadcast_data.user_role:
        if broadcast_data.user_role == "customer":
            # Broadcast to ALL active customers
            result = await db.execute(select(CustomerUser).where(CustomerUser.is_active == True))
            customers = result.scalars().all()
            for customer in customers:
                notification = Notification(
                    customer_id=customer.id,
                    type=broadcast_data.type,
                    channel=broadcast_data.channel,
                    title=broadcast_data.title,
                    message=broadcast_data.message,
                    is_sent=True,
                    sent_at=datetime.utcnow()
                )
                db.add(notification)
                notifications_created += 1
        else:
            # Broadcast to specific User roles (staff)
            try:
                query = select(User).where(and_(User.is_active == True, User.role == UserRole(broadcast_data.user_role)))
                result = await db.execute(query)
                users = result.scalars().all()
                for user in users:
                    notification = Notification(
                        user_id=user.id,
                        type=broadcast_data.type,
                        channel=broadcast_data.channel,
                        title=broadcast_data.title,
                        message=broadcast_data.message,
                        is_sent=True,
                        sent_at=datetime.utcnow()
                    )
                    db.add(notification)
                    notifications_created += 1
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid user role: {broadcast_data.user_role}"
                )
    else:
        # Broadcast to EVERYONE (Both tables)
        # Users
        u_res = await db.execute(select(User).where(User.is_active == True))
        for user in u_res.scalars().all():
            db.add(Notification(
                user_id=user.id,
                type=broadcast_data.type,
                channel=broadcast_data.channel,
                title=broadcast_data.title,
                message=broadcast_data.message,
                is_sent=True,
                sent_at=datetime.utcnow()
            ))
            notifications_created += 1
        
        # Customers
        c_res = await db.execute(select(CustomerUser).where(CustomerUser.is_active == True))
        for customer in c_res.scalars().all():
            db.add(Notification(
                customer_id=customer.id,
                type=broadcast_data.type,
                channel=broadcast_data.channel,
                title=broadcast_data.title,
                message=broadcast_data.message,
                is_sent=True,
                sent_at=datetime.utcnow()
            ))
            notifications_created += 1
    
    await db.commit()
    
    return {
        "message": f"Broadcast sent to {notifications_created} targets",
        "targets_count": notifications_created
    }

@router.get("/admin/notifications/stats", response_model=NotificationStats)
async def get_notification_stats(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics (admin only)"""
    
    # Total notifications
    total_result = await db.execute(select(func.count(Notification.id)))
    total = total_result.scalar()
    
    # Unread count
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.is_read == False)
    )
    unread = unread_result.scalar()
    
    # Sent count
    sent_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.is_sent == True)
    )
    sent = sent_result.scalar()
    
    # By type
    type_result = await db.execute(
        select(Notification.type, func.count(Notification.id)).group_by(Notification.type)
    )
    by_type = {str(row[0]): row[1] for row in type_result.all()}
    
    # By channel
    channel_result = await db.execute(
        select(Notification.channel, func.count(Notification.id)).group_by(Notification.channel)
    )
    by_channel = {str(row[0]): row[1] for row in channel_result.all()}
    
    return NotificationStats(
        total_notifications=total,
        unread_count=unread,
        sent_count=sent,
        by_type=by_type,
        by_channel=by_channel
    )
