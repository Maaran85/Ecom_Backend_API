"""
Development & Test Account Seeding Script
=========================================
Safely, idempotently provisions missing development and test accounts in the PostgreSQL database.
Strictly adheres to:
1. Environment isolation: Refuses to run if ENVIRONMENT == 'production'.
2. Zero plaintext passwords in code: Credentials must be loaded from environment variables.
3. Cryptographic security: All passwords are securely hashed using Argon2 via core.security.
4. Idempotency: Existing accounts, IDs, roles, and credentials are never overwritten or duplicated.
5. Role & Profile Integrity: Appropriately provisions dealer profiles for dealer accounts in the 'dealers' table.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv(dotenv_path=str(PROJECT_ROOT / ".env"), override=False)

from sqlalchemy import select, text
from core.database import SessionLocal, engine
from core.security import get_password_hash, verify_password
from models.user import User, UserRole
from models.dealer import Dealer
from models.customer_user import CustomerUser
import uuid


# Inventory definition without plaintext passwords (referencing environment variable names)
DEV_ACCOUNT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "canonical_id": 103,
        "name": "Finance Specialist 1",
        "email": "finance@myntra.com",
        "phone": "7778889990",
        "role": UserRole.PARTNER_FINANCE_SPECIALIST,
        "env_pwd_var": "DEV_PWD_FINANCE"
    },
    {
        "canonical_id": 102,
        "name": "Logistics Specialist 1",
        "email": "logistics@myntra.com",
        "phone": "6667778889",
        "role": UserRole.PARTNER_LOGISTICS_SPECIALIST,
        "env_pwd_var": "DEV_PWD_LOGISTICS"
    },
    {
        "canonical_id": 105,
        "name": "Tech Support 1",
        "email": "tech@myntra.com",
        "phone": "9990001112",
        "role": UserRole.PARTNER_TECH_SUPPORT,
        "env_pwd_var": "DEV_PWD_TECH"
    },
    {
        "canonical_id": 101,
        "name": "Backoffice Expert 1",
        "email": "backoffice@myntra.com",
        "phone": "5556667778",
        "role": UserRole.PARTNER_BACKOFFICE,
        "env_pwd_var": "DEV_PWD_BACKOFFICE"
    },
    {
        "canonical_id": 106,
        "name": "Support Manager 1",
        "email": "support_manager@myntra.com",
        "phone": "0001112223",
        "role": UserRole.PARTNER_SUPPORT_MANAGER,
        "env_pwd_var": "DEV_PWD_SUPPORT_MANAGER"
    },
    {
        "canonical_id": 10,
        "name": "Demo Dealer",
        "email": "dealer@myntra.com",
        "phone": "9999900002",
        "role": UserRole.DEALER,
        "business_name": "Demo Electronics Store",
        "env_pwd_var": "DEV_PWD_DEALER"
    },
    {
        "canonical_id": 38,
        "name": "MAARAN",
        "email": "manitrick@gmail.com",
        "phone": "8888888888",
        "role": UserRole.DEALER,
        "business_name": "CST Dealer",
        "env_pwd_var": "DEV_PWD_MANITRICK"
    },
    {
        "canonical_id": 98,
        "name": "Helpdesk Operator 1",
        "email": "operator@myntra.com",
        "phone": "1112223334",
        "role": UserRole.PARTNER_HELPDESK_OPERATOR,
        "env_pwd_var": "DEV_PWD_OPERATOR"
    },
    {
        "canonical_id": 93,
        "name": "Helpdesk Operator 1",
        "email": "operator1@myntra.com",
        "phone": "9876543221",
        "role": UserRole.PARTNER_HELPDESK_OPERATOR,
        "env_pwd_var": "DEV_PWD_OPERATOR1"
    },
    {
        "canonical_id": 79,
        "name": "Helpdesk Agent 1",
        "email": "agent1@helpdesk.com",
        "phone": None,
        "role": UserRole.PARTNER_HELPDESK_OPERATOR,
        "env_pwd_var": "DEV_PWD_AGENT1"
    },
    {
        "canonical_id": 99,
        "name": "Helpdesk Supervisor 1",
        "email": "supervisor@myntra.com",
        "phone": "2223334445",
        "role": UserRole.PARTNER_HELPDESK_SUPERVISOR,
        "env_pwd_var": "DEV_PWD_SUPERVISOR"
    },
    {
        "canonical_id": 3,
        "name": "Admin User",
        "email": "admin@myntra.com",
        "phone": "9876543212",
        "role": UserRole.ADMIN,
        "env_pwd_var": "DEV_PWD_ADMIN_MYNTRA"
    },
    {
        "canonical_id": 5,
        "name": "Admin User",
        "email": "admin@example.com",
        "phone": "9876544222",
        "role": UserRole.ADMIN,
        "env_pwd_var": "DEV_PWD_ADMIN_EXAMPLE"
    },
    {
        "canonical_id": 9,
        "name": "Super Admin",
        "email": "superadmin@myntra.com",
        "phone": "9999900000",
        "role": UserRole.SUPER_ADMIN,
        "env_pwd_var": "DEV_PWD_SUPERADMIN"
    },
]


async def seed_development_accounts(dry_run: bool = False):
    """
    Idempotently seeds development accounts into the PostgreSQL database.
    """
    env_name = os.getenv("ENVIRONMENT", "development").lower()
    if env_name == "production":
        raise RuntimeError("CRITICAL SAFETY BLOCK: Refusing to seed development accounts in production environment.")

    print(f"============================================================")
    print(f"--- DEVELOPMENT ACCOUNT SEEDING (DryRun={dry_run}) ---")
    print(f"Target Database: {engine.url.render_as_string(hide_password=True)}")
    print(f"Environment: {env_name}")
    print(f"============================================================")

    created_accounts = []
    preserved_accounts = []
    verification_results = []

    async with SessionLocal() as db:
        # Check existing user IDs to avoid conflict with canonical IDs
        existing_ids_res = await db.execute(select(User.id))
        occupied_ids = set(existing_ids_res.scalars().all())

        for defn in DEV_ACCOUNT_DEFINITIONS:
            email = defn["email"].strip().lower()
            canonical_id = defn["canonical_id"]
            role = defn["role"]
            name = defn["name"]
            phone = defn["phone"]
            env_var = defn["env_pwd_var"]
            secret_pwd = os.getenv(env_var)

            # Query existing user by email
            res = await db.execute(select(User).where(User.email.ilike(email)))
            existing_user = res.scalar_one_or_none()

            # Fallback query by phone if applicable
            if not existing_user and phone:
                res_p = await db.execute(select(User).where(User.phone == phone))
                existing_user = res_p.scalar_one_or_none()

            if existing_user:
                # Account already exists: strictly preserve credentials, ID, and role
                role_val = existing_user.role.value if hasattr(existing_user.role, 'value') else str(existing_user.role)
                pwd_ok = False
                if secret_pwd and existing_user.password_hash:
                    pwd_ok = verify_password(secret_pwd, existing_user.password_hash)

                preserved_accounts.append({
                    "id": existing_user.id,
                    "email": existing_user.email,
                    "role": role_val,
                    "phone": existing_user.phone,
                    "verified": pwd_ok
                })
                print(f"[PRESERVED] ID={existing_user.id} | Email='{existing_user.email}' | Role='{role_val}' | PasswordVerified={pwd_ok}")

                # Ensure Dealer profile exists if role is DEALER
                if role == UserRole.DEALER and not dry_run:
                    d_res = await db.execute(select(Dealer).where(Dealer.user_id == existing_user.id))
                    if not d_res.scalar_one_or_none():
                        new_dealer = Dealer(
                            id=uuid.uuid4(),
                            user_id=existing_user.id,
                            business_name=defn.get("business_name", "Demo Dealer Store"),
                            is_approved=True,
                            is_active=True,
                            access_status="active",
                            profile_status="completed"
                        )
                        db.add(new_dealer)
                        await db.flush()
                        print(f"  -> Linked missing Dealer profile for user ID {existing_user.id}")

            else:
                # Account is missing: report and seed securely
                if not secret_pwd:
                    raise ValueError(f"Missing environment variable {env_var} required to seed {email}")

                hashed_pwd = get_password_hash(secret_pwd)

                # Determine ID: use canonical ID if unoccupied, else allow DB sequence
                use_id = canonical_id if canonical_id not in occupied_ids else None

                print(f"[SEEDING MISSING ACCOUNT] Email='{email}' | Role='{role.value}' | PlannedID={use_id or 'auto'} | Phone='{phone or 'None'}'")

                if not dry_run:
                    user_kwargs = {
                        "email": email,
                        "full_name": name,
                        "phone": phone,
                        "role": role,
                        "password_hash": hashed_pwd,
                        "is_active": True
                    }
                    if use_id:
                        user_kwargs["id"] = use_id

                    new_user = User(**user_kwargs)
                    db.add(new_user)
                    await db.flush()
                    occupied_ids.add(new_user.id)

                    # If Dealer role, create linked approved Dealer profile
                    if role == UserRole.DEALER:
                        dealer_profile = Dealer(
                            id=uuid.uuid4(),
                            user_id=new_user.id,
                            business_name=defn.get("business_name", f"{name} Store"),
                            is_approved=True,
                            is_active=True,
                            access_status="active",
                            profile_status="completed"
                        )
                        db.add(dealer_profile)
                        await db.flush()

                    created_accounts.append({
                        "id": new_user.id,
                        "email": new_user.email,
                        "role": new_user.role.value if hasattr(new_user.role, 'value') else str(new_user.role),
                        "phone": new_user.phone
                    })

        if not dry_run:
            # Synchronize PostgreSQL users_id_seq to prevent sequence collision
            await db.execute(text("SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 1) FROM users));"))
            await db.commit()
            print("\nDatabase transaction committed and users_id_seq synchronized.")

    print(f"\nSummary: {len(preserved_accounts)} accounts preserved, {len(created_accounts)} accounts created.")
    return {
        "preserved": preserved_accounts,
        "created": created_accounts
    }


if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    asyncio.run(seed_development_accounts(dry_run=is_dry))
