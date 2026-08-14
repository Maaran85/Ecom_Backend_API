import os, sys, asyncio
backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)
from dotenv import load_dotenv
load_dotenv()

import httpx
from main import app
from core.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import User
from models.user import UserRole
from models.tds_configuration import TDSConfiguration
from core.security import create_access_token

TestSession = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def test_rbac():
    async with TestSession() as db:
        # Find or create super_admin and admin users for testing
        res_super = await db.execute(select(User).where(User.role == UserRole.SUPER_ADMIN))
        super_admin_user = res_super.scalars().first()
        
        res_admin = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        admin_user = res_admin.scalars().first()

        res_tds = await db.execute(select(TDSConfiguration).limit(1))
        tds_config = res_tds.scalars().first()

    if not super_admin_user:
        print("Creating mock super_admin user object for token generation")
        super_email = "super_admin_test@myntra.com"
    else:
        super_email = super_admin_user.email

    if not admin_user:
        print("Creating mock admin user object for token generation")
        admin_email = "admin_test@myntra.com"
    else:
        admin_email = admin_user.email

    super_token = create_access_token({"sub": super_email, "role": UserRole.SUPER_ADMIN.value})
    admin_token = create_access_token({"sub": admin_email, "role": UserRole.ADMIN.value})

    print(f"Testing with TDS Config ID: {tds_config.id if tds_config else 1}")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Test 1: Unauthenticated
        r_unauth_get = await client.get("/api/v1/admin/tds-configurations")
        r_unauth_put = await client.put(f"/api/v1/admin/tds-configurations/{tds_config.id if tds_config else 1}", json={"tds_rate_with_pan": 0.01})
        print(f"Unauthenticated GET: status={r_unauth_get.status_code} (Expected: 401)")
        print(f"Unauthenticated PUT: status={r_unauth_put.status_code} (Expected: 401)")
        assert r_unauth_get.status_code == 401
        assert r_unauth_put.status_code == 401

        # Test 2: Admin
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        r_admin_get = await client.get("/api/v1/admin/tds-configurations", headers=headers_admin)
        r_admin_put = await client.put(f"/api/v1/admin/tds-configurations/{tds_config.id if tds_config else 1}", json={"tds_rate_with_pan": 0.01}, headers=headers_admin)
        print(f"Admin GET: status={r_admin_get.status_code} (Expected: 200)")
        print(f"Admin PUT: status={r_admin_put.status_code}, detail={r_admin_put.json() if r_admin_put.status_code != 200 else ''} (Expected: 403)")
        assert r_admin_get.status_code == 200
        assert r_admin_put.status_code == 403

        # Test 3: Super Admin
        headers_super = {"Authorization": f"Bearer {super_token}"}
        r_super_get = await client.get("/api/v1/admin/tds-configurations", headers=headers_super)
        
        # Save original rate to restore after test
        original_rate = tds_config.tds_rate_with_pan if tds_config else 0.01
        r_super_put = await client.put(f"/api/v1/admin/tds-configurations/{tds_config.id if tds_config else 1}", json={"tds_rate_with_pan": original_rate}, headers=headers_super)
        print(f"Super Admin GET: status={r_super_get.status_code} (Expected: 200)")
        print(f"Super Admin PUT: status={r_super_put.status_code} (Expected: 200)")
        assert r_super_get.status_code == 200
        assert r_super_put.status_code == 200

        print("\nALL VERIFICATION TESTS PASSED 100%!")

if __name__ == "__main__":
    asyncio.run(test_rbac())
