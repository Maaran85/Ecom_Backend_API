from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from models.notification import NotificationType, NotificationChannel

# Notification
class NotificationResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    type: NotificationType
    channel: NotificationChannel
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    is_read: bool
    is_sent: bool
    sent_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class NotificationCreate(BaseModel):
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    type: NotificationType
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    channel: NotificationChannel = NotificationChannel.IN_APP

class BroadcastNotificationRequest(BaseModel):
    title: str
    message: str
    type: NotificationType = NotificationType.PROMOTIONAL
    channel: NotificationChannel = NotificationChannel.IN_APP
    user_role: Optional[str] = None  # "customer", "dealer", "admin", or None for all

# Notification Preferences
class NotificationPreferenceUpdate(BaseModel):
    email_order_updates: Optional[bool] = None
    email_promotions: Optional[bool] = None
    email_newsletters: Optional[bool] = None
    sms_order_updates: Optional[bool] = None
    sms_promotions: Optional[bool] = None
    in_app_order_updates: Optional[bool] = None
    in_app_promotions: Optional[bool] = None

class NotificationPreference(BaseModel):
    id: int
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    email_order_updates: bool
    email_promotions: bool
    email_newsletters: bool
    sms_order_updates: bool
    sms_promotions: bool
    in_app_order_updates: bool
    in_app_promotions: bool
    
    class Config:
        from_attributes = True

class NotificationStats(BaseModel):
    total_notifications: int
    unread_count: int
    sent_count: int
    by_type: Dict[str, int]
    by_channel: Dict[str, int]
