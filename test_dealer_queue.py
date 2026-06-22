import asyncio
import httpx

async def test_dealer():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Login
        res = await client.post("/api/v1/auth/login", json={
            "identifier": "dealer@myntra.com",
            "password": "dealer123"
        })
        if res.status_code != 200:
            print("Login failed:", res.text)
            return
            
        token = res.json()["access_token"]
        
        # Fetch queue
        res2 = await client.get("/api/v1/support-tickets/dealer/my-queue", headers={"Authorization": f"Bearer {token}"})
        print(f"Status: {res2.status_code}")
        print("Response:", res2.text)

asyncio.run(test_dealer())
