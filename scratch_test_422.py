import os, sys, traceback
backend_dir = r'C:\Users\vidhy\OneDrive\Documents\project\freelance\Ecom_Backend_API'
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)
from dotenv import load_dotenv
load_dotenv()
from fastapi.testclient import TestClient
from main import app
from core.security import create_access_token
import asyncio
from core.database import engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import User, Dealer
from models.settlement import Settlement

TestSession = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def test_endpoint():
    async with TestSession() as db:
        res_s3 = await db.execute(select(Settlement).where(Settlement.id == 3))
        s3 = res_s3.scalars().first()
        res_dealer = await db.execute(select(Dealer).where(Dealer.id == s3.dealer_id))
        dealer = res_dealer.scalars().first()
        res_user = await db.execute(select(User).where(User.id == dealer.user_id))
        user = res_user.scalars().first()

        token = create_access_token({"sub": user.email, "role": user.role})
        print("User email:", user.email, "Role:", user.role, "Dealer ID:", user.dealer_id)

    client = TestClient(app)

    # Test 1: GET /dealers/settlements?limit=100
    headers = {"Authorization": f"Bearer {token}"}
    r1 = client.get("/dealers/settlements?limit=100", headers=headers)
    print("\n=== GET /dealers/settlements?limit=100 ===")
    print("Status Code:", r1.status_code)
    print("Response JSON:", r1.json() if r1.status_code != 500 else r1.text)

    # Test 2: GET /api/v1/dealers/settlements?limit=100
    r2 = client.get("/api/v1/dealers/settlements?limit=100", headers=headers)
    print("\n=== GET /api/v1/dealers/settlements?limit=100 ===")
    print("Status Code:", r2.status_code)
    print("Response JSON:", r2.json() if r2.status_code != 500 else r2.text)

    # Test 3: What if financial_year or another parameter is passed as invalid?
    r3 = client.get("/dealers/settlements?limit=s", headers=headers)
    print("\n=== GET /dealers/settlements?limit=s ===")
    print("Status Code:", r3.status_code)
    print("Response JSON:", r3.json())

    # Test 4: What if financial_year=something or status=something?
    r4 = client.get("/dealers/settlements?financial_year=s", headers=headers)
    print("\n=== GET /dealers/settlements?financial_year=s ===")
    print("Status Code:", r4.status_code)
    print("Response JSON:", r4.json())

if __name__ == '__main__':
    asyncio.run(test_endpoint())
