from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.config import settings
from models import Notification, NotificationType, NotificationChannel, User

# Configure logging
logger = logging.getLogger(__name__)

# Email Configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.SENDER_EMAIL or "user",
    MAIL_PASSWORD=settings.SENDER_PASSWORD or "password",
    MAIL_FROM=settings.SENDER_EMAIL or "noreply@onlineshop.com",
    MAIL_PORT=settings.SMTP_PORT or 587,
    MAIL_SERVER=settings.SMTP_SERVER or "smtp.gmail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

class EmailService:
    @staticmethod
    async def send_order_confirmation(to_email: EmailStr, order_data: Dict[str, Any]):
        """
        Send order confirmation email.
        In a real app, this would use a Jinja2 template.
        For now, we send a simple text/html message.
        """
        try:
            # Check if SMTP is configured (mock if not)
            if not settings.SMTP_SERVER:
                logger.info(f"MOCK EMAIL to {to_email}: Order #{order_data.get('id')} confirmed. Total: ${order_data.get('total')}")
                return

            html = f"""
            <h1>Order Confirmation</h1>
            <p>Thank you for your order!</p>
            <p><strong>Order ID:</strong> {order_data.get('id')}</p>
            <p><strong>Total Amount:</strong> ${order_data.get('total')}</p>
            <p>We are processing your order and will notify you when it ships.</p>
            """

            message = MessageSchema(
                subject=f"Order Confirmation #{order_data.get('id')}",
                recipients=[to_email],
                body=html,
                subtype=MessageType.html
            )

            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"Order confirmation sent to {to_email}")
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

    @staticmethod
    async def send_low_stock_alert(to_email: EmailStr, products: List[Dict[str, Any]]):
        """
        Send low stock alert email.
        """
        try:
            # Check if SMTP is configured (mock if not)
            if not settings.SMTP_SERVER:
                logger.info(f"MOCK EMAIL to {to_email}: Low Stock Alert for {len(products)} products.")
                for p in products:
                    logger.info(f" - {p['name']}: {p['stock']} left (Threshold: {p['threshold']})")
                return

            items_html = ""
            for p in products:
                items_html += f"<li><strong>{p['name']}</strong>: {p['stock']} remaining (Threshold: {p['threshold']})</li>"

            html = f"""
            <h1>Low Stock Alert</h1>
            <p>The following products are running low on stock:</p>
            <ul>
                {items_html}
            </ul>
            <p>Please restock soon to avoid running out.</p>
            """

            message = MessageSchema(
                subject=f"Low Stock Alert - {len(products)} Items",
                recipients=[to_email],
                body=html,
                subtype=MessageType.html
            )

            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"Low stock alert sent to {to_email}")
            
        except Exception as e:
            logger.error(f"Failed to send low stock email: {str(e)}")
    @staticmethod
    async def send_otp(to_email: EmailStr, otp: str):
        """
        Send OTP for dealer registration.
        """
        try:
            # Check if SMTP is configured (mock if not)
            if not settings.SMTP_SERVER:
                logger.info(f"MOCK OTP EMAIL to {to_email}: OTP is {otp}")
                return

            html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 12px; background-color: #ffffff;">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #6c5ce7; margin: 0;">Online Shop</h1>
                    <p style="color: #6B7280; font-size: 14px;">Partner Portal Verification</p>
                </div>
                
                <h2 style="color: #111827; margin-bottom: 20px;">Email Verification</h2>
                <p style="color: #4B5563; line-height: 24px;">Hello,</p>
                <p style="color: #4B5563; line-height: 24px;">Thank you for registering as a dealer. Please use the following One-Time Password (OTP) to verify your email address:</p>
                
                <div style="background-color: #F9FAFB; padding: 20px; text-align: center; border-radius: 8px; margin: 30px 0;">
                    <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #6c5ce7;">{otp}</span>
                </div>
                
                <p style="color: #4B5563; line-height: 24px; font-size: 14px;">This OTP is valid for 10 minutes. If you did not request this, please ignore this email.</p>
                
                <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                
                <p style="color: #9CA3AF; font-size: 12px; text-align: center;">By Mani</p>
            </div>
            """

            message = MessageSchema(
                subject="Verify Your Dealer Registration - Online Shop",
                recipients=[to_email],
                body=html,
                subtype=MessageType.html
            )

            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"OTP sent to {to_email}")
            
        except Exception as e:
            logger.error(f"Failed to send OTP email: {str(e)}")

    @staticmethod
    async def send_dealer_status_notification(to_email: EmailStr, business_name: str, approved: bool, reason: Optional[str] = None):
        """
        Send notification email when a dealer application status changes (approved/rejected).
        """
        try:
            # Check if SMTP is configured (mock if not)
            if not settings.SMTP_SERVER:
                status_str = "approved" if approved else f"rejected (Reason: {reason})"
                logger.info(f"MOCK EMAIL to {to_email}: Dealer '{business_name}' status update: {status_str}")
                return

            if approved:
                subject = "Your Dealer Application has been Approved! - Online Shop"
                html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 12px; background-color: #ffffff;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #6c5ce7; margin: 0;">Online Shop</h1>
                        <p style="color: #6B7280; font-size: 14px;">Partner Portal Approval</p>
                    </div>
                    
                    <h2 style="color: #111827; margin-bottom: 20px;">Congratulations!</h2>
                    <p style="color: #4B5563; line-height: 24px;">Hello,</p>
                    <p style="color: #4B5563; line-height: 24px;">We are pleased to inform you that your dealer application for <strong>{business_name}</strong> has been <strong>approved</strong> by our administration team!</p>
                    <p style="color: #4B5563; line-height: 24px;">You can now log in to the Dealer Portal, complete your profile details, and start listing your products for sale.</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="#" style="background-color: #6c5ce7; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Log In to Dealer Portal</a>
                    </div>
                    
                    <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                    <p style="color: #9CA3AF; font-size: 12px; text-align: center;">By Mani</p>
                </div>
                """
            else:
                subject = "Update on your Dealer Application - Online Shop"
                reason_html = f"<p style='color: #b91c1c; font-weight: bold; margin-top: 10px;'>Reason: {reason}</p>" if reason else ""
                html = f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 12px; background-color: #ffffff;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #b91c1c; margin: 0;">Online Shop</h1>
                        <p style="color: #6B7280; font-size: 14px;">Partner Portal Application Update</p>
                    </div>
                    
                    <h2 style="color: #111827; margin-bottom: 20px;">Application Status Update</h2>
                    <p style="color: #4B5563; line-height: 24px;">Hello,</p>
                    <p style="color: #4B5563; line-height: 24px;">Thank you for your interest in partnering with us. We have reviewed your dealer application for <strong>{business_name}</strong>.</p>
                    <p style="color: #4B5563; line-height: 24px;">Unfortunately, your application could not be approved at this time.</p>
                    {reason_html}
                    <p style="color: #4B5563; line-height: 24px; margin-top: 20px;">If you have any questions, please contact our support team.</p>
                    
                    <hr style="border: 0; border-top: 1px solid #e5e7eb; margin: 30px 0;">
                    <p style="color: #9CA3AF; font-size: 12px; text-align: center;">By Mani</p>
                </div>
                """

            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html,
                subtype=MessageType.html
            )

            fm = FastMail(conf)
            await fm.send_message(message)
            logger.info(f"Dealer status email sent to {to_email}")
            
        except Exception as e:
            logger.error(f"Failed to send dealer status email: {str(e)}")

class SmsService:
    @staticmethod
    async def send_otp(phone: str, otp: str):
        """
        Send OTP via SMS.
        Mock implementation for now.
        """
        try:
            # In a real app, you would integrate with Twilio, AWS SNS, etc.
            logger.info(f"MOCK SMS to {phone}: Your Online Shop OTP is {otp}")
            return True
        except Exception as e:
            logger.error(f"Failed to send OTP SMS: {str(e)}")
            return False

class AppNotificationService:
    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        type: NotificationType = NotificationType.PROMOTIONAL,
        title: str = "",
        message: str = "",
        data: Dict[str, Any] = None
    ):
        """Create an in-app notification for a specific user. Uses savepoint to avoid poisoning main transaction."""
        try:
            async with db.begin_nested():
                notification = Notification(
                    user_id=user_id,
                    customer_id=customer_id,
                    type=type,
                    channel=NotificationChannel.IN_APP,
                    title=title,
                    message=message,
                    data=data,
                    is_sent=True,
                    sent_at=datetime.now(timezone.utc)
                )
                db.add(notification)
                await db.flush()
            return notification
        except Exception as e:
            logger.error(f"Error creating in-app notification: {e}")
            return None

    @staticmethod
    async def notify_order_status(db: AsyncSession, user_id: Optional[int] = None, customer_id: Optional[int] = None, order_number: str = "", status: str = "", data: Dict[str, Any] = None):
        """Standard order status update generator"""
        status_map = {
            "confirmed": (NotificationType.ORDER_CONFIRMED, "Order Confirmed", f"Your order #{order_number} has been confirmed!"),
            "packaging": (NotificationType.ORDER_PACKING, "Preparing Your Order", f"We've started preparing your order #{order_number}. It will be packed soon!"),
            "packed": (NotificationType.ORDER_PACKED, "Order Packed", f"Order #{order_number} is packed and ready for dispatch."),
            "shipped": (NotificationType.ORDER_SHIPPED, "Order Shipped", f"Excellent news! Your order #{order_number} has been shipped."),
            "out_for_delivery": (NotificationType.ORDER_OUT_FOR_DELIVERY, "Out for Delivery", f"Your package for order #{order_number} is out for delivery!"),
            "delivered": (NotificationType.ORDER_DELIVERED, "Delivered Successfully", f"Order #{order_number} has been delivered. We hope you love it!"),
            "cancelled": (NotificationType.ORDER_CANCELLED, "Order Cancelled", f"Your order #{order_number} has been cancelled."),
            "undelivered": (NotificationType.ORDER_FAILED, "Delivery Attempt Failed", f"We couldn't deliver order #{order_number}. Our partner will try again or contact you."),
            "failed": (NotificationType.ORDER_FAILED, "Delivery Failed", f"Delivery of order #{order_number} has failed.")
        }
        
        if status.lower() in status_map:
            type, title, message = status_map[status.lower()]
            return await AppNotificationService.create_notification(db, user_id=user_id, customer_id=customer_id, type=type, title=title, message=message, data=data)
        return None

    @staticmethod
    async def notify_return_status(db: AsyncSession, user_id: Optional[int] = None, customer_id: Optional[int] = None, order_number: str = "", status: str = "", data: Dict[str, Any] = None):
        """Standard return status update generator"""
        status_map = {
            "requested": (NotificationType.RETURN_REQUESTED, "Return Requested", f"Your return request for order #{order_number} has been received."),
            "approved": (NotificationType.RETURN_APPROVED, "Return Approved", f"Good news! Your return request for order #{order_number} has been approved. A rider will pick it up soon."),
            "rejected": (NotificationType.RETURN_REJECTED, "Return Rejected", f"Your return request for order #{order_number} has been reviewed and rejected."),
            "out_for_pickup": (NotificationType.RETURN_APPROVED, "Rider Assigned", f"A rider is on their way to pick up your return from order #{order_number}."),
            "picked_up": (NotificationType.RETURN_APPROVED, "IN LOGISTICS", f"Our partner has picked up your return from order #{order_number} and it is now in logistics."),
            "in_transit_to_hub": (NotificationType.RETURN_APPROVED, "IN HUB", f"Your return for order #{order_number} has been received at our local hub."),
            "in_transit_to_store": (NotificationType.RETURN_APPROVED, "IN DELIVERY STORE", f"Your return for order #{order_number} has been received at the vendor store."),
            "completed": (NotificationType.RETURN_APPROVED, "IN ADMIN", f"Your return for order #{order_number} is being verified by the admin team. Refund will follow soon."),
            "pickup_failed": (NotificationType.ORDER_FAILED, "Pickup Attempt Failed", f"Our partner was unable to collect your return for order #{order_number}. They will try again soon."),
        }
        
        if status.lower() in status_map:
            type, title, message = status_map[status.lower()]
            return await AppNotificationService.create_notification(db, user_id=user_id, customer_id=customer_id, type=type, title=title, message=message, data=data)
        return None

    @staticmethod
    async def notify_rider_status(db: AsyncSession, user_id: int, status: str, data: Dict[str, Any] = None):
        """Standard rider application status updates"""
        status_map = {
            "approved": (NotificationType.RIDER_APPROVED, "Welcome Partner!", "Congratulations! Your delivery partner application has been approved. You can now start accepting tasks."),
            "rejected": (NotificationType.RIDER_REJECTED, "Application Update", "Your delivery partner application was not approved at this time. Please contact support for more details."),
        }
        
        if status.lower() in status_map:
            type, title, message = status_map[status.lower()]
            return await AppNotificationService.create_notification(db, user_id, type, title, message, data)
        return None

    @staticmethod
    async def notify_stock_alert(db: AsyncSession, dealer_user_id: int, product_name: str, stock: int, threshold: int):
        """Notify dealer about low stock"""
        title = "Low Stock Alert"
        message = f"Your product '{product_name}' is running low on stock ({stock} remaining). Threshold: {threshold}."
        
        notif = await AppNotificationService.create_notification(
            db, dealer_user_id, NotificationType.LOW_STOCK_ALERT, title, message, 
            {"product_name": product_name, "stock": stock, "threshold": threshold}
        )
        
        # Also send email
        user_res = await db.execute(select(User.email).where(User.id == dealer_user_id))
        user_email = user_res.scalar()
        if user_email:
            await EmailService.send_low_stock_alert(user_email, [{
                "name": product_name,
                "stock": stock,
                "threshold": threshold
            }])
        return notif
