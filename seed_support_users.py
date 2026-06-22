import asyncio
import os
from sqlalchemy import select, delete
from core.database import SessionLocal
from models.user import User, UserRole
from models.support_ticket import SupportTicket, TicketMessage
from core.security import get_password_hash

async def seed_users():
    print("Connecting to database...")
    async with SessionLocal() as db:
        print("Deleting all tickets and messages first to avoid foreign key violations...")
        await db.execute(delete(TicketMessage))
        await db.execute(delete(SupportTicket))
        await db.commit()

        print("Deleting existing helpdesk/backoffice users...")
        await db.execute(
            delete(User).where(
                User.email.in_([
                    "helpdesk@myntra.com",
                    "operator@myntra.com",
                    "supervisor@myntra.com",
                    "manager@myntra.com",
                    "backoffice@myntra.com",
                    "logistics@myntra.com",
                    "finance@myntra.com",
                    "catalog@myntra.com",
                    "tech@myntra.com",
                    "support_manager@myntra.com"
                ])
            )
        )
        await db.commit()
        
        print("Creating Helpdesk Operator...")
        operator = User(
            full_name="Helpdesk Operator 1",
            email="operator@myntra.com",
            phone="1112223334",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_HELPDESK_OPERATOR,
            is_active=True
        )
        db.add(operator)
        
        print("Creating Helpdesk Supervisor...")
        supervisor = User(
            full_name="Helpdesk Supervisor 1",
            email="supervisor@myntra.com",
            phone="2223334445",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_HELPDESK_SUPERVISOR,
            is_active=True
        )
        db.add(supervisor)
        
        print("Creating Helpdesk Manager...")
        manager = User(
            full_name="Helpdesk Manager 1",
            email="manager@myntra.com",
            phone="3334445556",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_HELPDESK_MANAGER,
            is_active=True
        )
        db.add(manager)
            
        print("Creating Backoffice User...")
        backoffice_user = User(
            full_name="Backoffice Expert 1",
            email="backoffice@myntra.com",
            phone="5556667778",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_BACKOFFICE,
            is_active=True
        )
        db.add(backoffice_user)

        print("Creating Logistics Specialist...")
        logistics = User(
            full_name="Logistics Specialist 1",
            email="logistics@myntra.com",
            phone="6667778889",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_LOGISTICS_SPECIALIST,
            is_active=True
        )
        db.add(logistics)

        print("Creating Finance Specialist...")
        finance = User(
            full_name="Finance Specialist 1",
            email="finance@myntra.com",
            phone="7778889990",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_FINANCE_SPECIALIST,
            is_active=True
        )
        db.add(finance)

        print("Creating Catalog Manager...")
        catalog = User(
            full_name="Catalog Manager 1",
            email="catalog@myntra.com",
            phone="8889990001",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_CATALOG_MANAGER,
            is_active=True
        )
        db.add(catalog)

        print("Creating Tech Support...")
        tech = User(
            full_name="Tech Support 1",
            email="tech@myntra.com",
            phone="9990001112",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_TECH_SUPPORT,
            is_active=True
        )
        db.add(tech)

        print("Creating Support Manager...")
        support_manager = User(
            full_name="Support Manager 1",
            email="support_manager@myntra.com",
            phone="0001112223",
            password_hash=get_password_hash("password123"),
            role=UserRole.PARTNER_SUPPORT_MANAGER,
            is_active=True
        )
        db.add(support_manager)

        await db.commit()
        print("Seeding complete!")

if __name__ == "__main__":
    asyncio.run(seed_users())
