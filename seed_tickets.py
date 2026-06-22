import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import SessionLocal
from models.user import User, UserRole
from models.dealer import Dealer
from models.partner import Partner
from models.support_ticket import SupportTicket, TicketMessage, TicketLevel, TicketStatus, TicketType

async def seed_tickets():
    async with SessionLocal() as db:
        print("Fetching existing users and dealers...")
        
        from models.customer_user import CustomerUser
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
            
        partner_id = 1
        
        print("Seeding tickets...")
        now = datetime.utcnow()
        
        # Ticket 1: Open, unhandled, SLA expiring soon (assigned to dealer)
        ticket1 = SupportTicket(
            ticket_number="TKT-OPEN1",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            subject="Where is my order?",
            description="I ordered this 3 days ago and the status hasn't changed.",
            current_level=TicketLevel.DEALER,
            status=TicketStatus.OPEN,
            is_handled_by_dealer=False,
            escalation_deadline=now + timedelta(minutes=15),
            created_at=now,
            updated_at=now
        )
        db.add(ticket1)
        
        # Ticket 2: Handled by dealer (in progress)
        ticket2 = SupportTicket(
            ticket_number="TKT-PROG1",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            subject="Does this fit a size L?",
            description="Checking if the dimensions run small.",
            current_level=TicketLevel.DEALER,
            status=TicketStatus.IN_PROGRESS,
            is_handled_by_dealer=True,
            escalation_deadline=now + timedelta(hours=1),
            created_at=now,
            updated_at=now
        )
        db.add(ticket2)
        
        # Ticket 3: Escalated to partner (breached SLA)
        ticket3 = SupportTicket(
            ticket_number="TKT-ESCALATED",
            customer_id=customer.id,
            dealer_id=dealer.id,
            partner_id=partner_id,
            subject="Received broken item!",
            description="The package arrived damaged and nobody has replied to me.",
            current_level=TicketLevel.PARTNER,
            status=TicketStatus.OPEN,
            is_handled_by_dealer=False,
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
    asyncio.run(seed_tickets())
