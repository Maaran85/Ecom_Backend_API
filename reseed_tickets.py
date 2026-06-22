import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from core.database import SessionLocal
from models.user import User
from models.dealer import Dealer
from models.customer_user import CustomerUser
from models.support_ticket import SupportTicket, TicketMessage, TicketStatus, TicketType, TicketStage, TicketSource, TicketSLAStatus

async def run_seed():
    async with SessionLocal() as db:
        print("Deleting existing tickets and messages...")
        await db.execute(delete(TicketMessage))
        await db.execute(delete(SupportTicket))
        await db.commit()

        print("Fetching existing users and dealers...")
        
        # Get customer by phone
        cust_res = await db.execute(select(CustomerUser).where(CustomerUser.phone == "9876543211").limit(1))
        customer = cust_res.scalar_one_or_none()
        
        if not customer:
            print("Error: Customer with phone 9876543211 not found in CustomerUser.")
            return
            
        # Get dealer by email
        dealer_res = await db.execute(
            select(Dealer)
            .join(User, Dealer.user_id == User.id)
            .where(User.email == "dealer@myntra.com")
            .limit(1)
        )
        dealer = dealer_res.scalar_one_or_none()
        
        if not dealer:
            print("Error: Dealer with email dealer@myntra.com not found.")
            return
            
        partner_id = dealer.partner_id if dealer.partner_id else 1
        
        # Get operator
        operator_res = await db.execute(select(User).where(User.email == "operator@myntra.com").limit(1))
        operator = operator_res.scalar_one_or_none()
        
        print("Seeding new tickets...")
        now = datetime.utcnow()
        
        # Ticket 1: Open, unhandled, SLA expiring soon (HELPDESK)
        ticket1 = SupportTicket(
            ticket_number="TKT-OPEN1",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            assigned_user_id=operator.id if operator else None,
            subject="Where is my order?",
            description="I ordered this 3 days ago and the status hasn't changed.",
            ticket_type=TicketType.ORDER_MANAGEMENT,
            source=TicketSource.WEBSITE,
            ticket_stage=TicketStage.HELPDESK,
            sla_status=TicketSLAStatus.AT_RISK,
            status=TicketStatus.OPEN,
            escalation_deadline=now + timedelta(minutes=15),
            created_at=now,
            updated_at=now
        )
        db.add(ticket1)
        
        # Ticket 2: Handled by agent (in progress)
        ticket2 = SupportTicket(
            ticket_number="TKT-PROG1",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            assigned_user_id=operator.id if operator else None,
            subject="Does this fit a size L?",
            description="Checking if the dimensions run small.",
            ticket_type=TicketType.PRODUCT_INQUIRIES,
            source=TicketSource.LIVE_CHAT,
            ticket_stage=TicketStage.HELPDESK,
            sla_status=TicketSLAStatus.ON_TRACK,
            status=TicketStatus.IN_PROGRESS,
            escalation_deadline=now + timedelta(hours=1),
            created_at=now,
            updated_at=now
        )
        db.add(ticket2)
        
        # Ticket 3: Escalated to BACKOFFICE (breached SLA)
        ticket3 = SupportTicket(
            ticket_number="TKT-ESCALATED",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            subject="Received broken item!",
            description="The package arrived damaged and nobody has replied to me.",
            ticket_type=TicketType.RETURNS_EXCHANGES,
            source=TicketSource.EMAIL,
            ticket_stage=TicketStage.BACKOFFICE,
            sla_status=TicketSLAStatus.BREACHED,
            status=TicketStatus.OPEN,
            escalation_deadline=now - timedelta(hours=2), # 2 hours overdue
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2)
        )
        db.add(ticket3)
        
        dealer_user_id = dealer.user_id
        
        await db.commit()
        await db.refresh(ticket2)
        await db.refresh(ticket3)
        
        # Add some messages
        msg1 = TicketMessage(
            ticket_id=ticket2.id,
            sender_id=dealer_user_id,
            message="Yes, our items fit true to size. You can confidently order a Large.",
            is_internal_note=False,
            created_at=now
        )
        
        msg2 = TicketMessage(
            ticket_id=ticket3.id,
            sender_id=dealer_user_id,
            message="We received this damaged package report but lack the inventory to replace it right now.",
            is_internal_note=True, # Hidden from customer
            created_at=now
        )
        
        db.add(msg1)
        db.add(msg2)
        await db.commit()
        
        print("Successfully seeded 3 sample support tickets!")

if __name__ == "__main__":
    asyncio.run(run_seed())
