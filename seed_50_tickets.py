import asyncio
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy.future import select
from core.database import SessionLocal
from models.user import User, UserRole
from models.support_ticket import SupportTicket, TicketType, TicketStatus, TicketPriority, TicketSource, TicketStage, TicketSLAStatus
from core.security import get_password_hash

async def seed_data():
    async with SessionLocal() as db:
        try:
            print("Creating 5 helpdesk operators...")
            operators = []
            for i in range(1, 6):
                email = f"operator{i}@myntra.com"
                
                result = await db.execute(select(User).where(User.email == email))
                existing_user = result.scalars().first()
                
                if not existing_user:
                    new_op = User(
                        email=email,
                        password_hash=get_password_hash("password123"),
                        full_name=f"Helpdesk Operator {i}",
                        phone=f"12300045{i}",
                        role=UserRole.PARTNER_HELPDESK_OPERATOR,
                        is_active=True
                    )
                    db.add(new_op)
                    operators.append(new_op)
                else:
                    operators.append(existing_user)
                    
            # Do not commit yet to avoid expiring objects
            print("Operators seeded.")

            # Fetch customer to assign tickets
            result = await db.execute(select(User).where(User.role == UserRole.CUSTOMER))
            customer = result.scalars().first()
            if not customer:
                # create a dummy customer if missing
                customer = User(
                    email="dummy_customer_for_tickets@test.com",
                    password_hash=get_password_hash("password"),
                    full_name="Dummy Customer",
                    phone="9999999999",
                    role=UserRole.CUSTOMER,
                    is_active=True
                )
                db.add(customer)
                await db.flush()

            print("Creating 50 support tickets...")
            ticket_types = list(TicketType)
            statuses = list(TicketStatus)
            priorities = list(TicketPriority)

            for i in range(1, 51):
                assigned_op = random.choice(operators)
                created_date = datetime.utcnow() - timedelta(days=random.randint(0, 30))
                
                status = random.choice(statuses)
                priority = random.choice(priorities)
                ticket_type = random.choice(ticket_types)
                
                new_ticket = SupportTicket(
                    ticket_number=f"TKT-100{i:03d}",
                    customer_id=customer.id,
                    ticket_type=ticket_type,
                    status=status,
                    priority=priority,
                    source=TicketSource.WEBSITE,
                    ticket_stage=TicketStage.HELPDESK,
                    subject=f"Sample Ticket {i} - {ticket_type.value}",
                    description=f"This is an auto-generated sample ticket for testing the helpdesk dashboard. Description {i}.",
                    assigned_user_id=assigned_op.id,
                    sla_status=TicketSLAStatus.ON_TRACK if status in [TicketStatus.RESOLVED, TicketStatus.CLOSED] else random.choice(list(TicketSLAStatus)),
                    created_at=created_date,
                    updated_at=created_date,
                )
                db.add(new_ticket)
            
            await db.commit()
            print("Successfully seeded 50 tickets assigned randomly among 5 operators.")

        except Exception as e:
            print("Error occurred:", e)
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(seed_data())
