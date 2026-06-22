import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import SessionLocal
from core.security import get_password_hash
from models.user import User, UserRole
from models.dealer import Dealer
from models.customer_user import CustomerUser
from models.support_ticket import SupportTicket, TicketStatus, TicketType, TicketStage, TicketSource, TicketSLAStatus

async def run_auto_assign_example():
    async with SessionLocal() as db:
        print("Fetching or creating 10 helpdesk users...")
        
        helpdesk_users = []
        for i in range(1, 11):
            email = f"agent{i}@helpdesk.com"
            res = await db.execute(select(User).where(User.email == email))
            user = res.scalar_one_or_none()
            
            if not user:
                user = User(
                    email=email,
                    password_hash=get_password_hash("password123"),
                    full_name=f"Helpdesk Agent {i}",
                    role=UserRole.PARTNER_HELPDESK,
                    is_active=True
                )
                db.add(user)
                helpdesk_users.append(user)
            else:
                helpdesk_users.append(user)
        
        await db.commit()
        for user in helpdesk_users:
            await db.refresh(user)
            
        print(f"Verified {len(helpdesk_users)} helpdesk users.")
        
        print("Fetching customer and dealer context...")
        cust_res = await db.execute(select(CustomerUser).limit(1))
        customer = cust_res.scalar_one_or_none()
        
        dealer_res = await db.execute(select(Dealer).limit(1))
        dealer = dealer_res.scalar_one_or_none()
        
        if not customer or not dealer:
            print("Error: Could not find a Customer or Dealer to attach tickets to.")
            return
            
        partner_id = dealer.partner_id if dealer.partner_id else 1
        
        print("Generating 100 tickets and splitting them among the 10 agents (round-robin)...")
        now = datetime.utcnow()
        new_tickets = []
        
        for i in range(1, 101):
            # Round-robin assignment (0 to 9)
            assigned_agent = helpdesk_users[i % 10]
            
            ticket = SupportTicket(
                ticket_number=f"TKT-AUTO-{1000 + i}",
                customer_id=customer.id,
                dealer_id=dealer.id,
                partner_id=partner_id,
                subject=f"Automated Support Request #{i}",
                description=f"This is an automatically generated ticket to demonstrate round-robin assignment. Assigned to {assigned_agent.full_name}.",
                ticket_type=TicketType.PRODUCT_INQUIRIES,
                source=TicketSource.WEBSITE,
                ticket_stage=TicketStage.HELPDESK,
                sla_status=TicketSLAStatus.ON_TRACK,
                status=TicketStatus.OPEN,
                escalation_deadline=now + timedelta(hours=24),
                assigned_user_id=assigned_agent.id, # AUTOMATIC ASSIGNMENT
                created_at=now,
                updated_at=now
            )
            db.add(ticket)
            new_tickets.append(ticket)
            
        await db.commit()
        
        print(f"Successfully generated {len(new_tickets)} tickets!")
        print(f"Each of the {len(helpdesk_users)} agents received exactly 10 tickets.")
        
        # Verify
        for agent in helpdesk_users:
            res = await db.execute(select(SupportTicket).where(SupportTicket.assigned_user_id == agent.id, SupportTicket.ticket_number.like('TKT-AUTO-%')))
            agent_tickets = res.scalars().all()
            print(f"{agent.full_name} ({agent.email}) is assigned to {len(agent_tickets)} tickets.")

if __name__ == "__main__":
    asyncio.run(run_auto_assign_example())
