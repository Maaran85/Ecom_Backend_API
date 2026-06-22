import asyncio
import json
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # Assuming admin user login
        res = await client.post("http://127.0.0.1:8000/auth/login", data={"username": "superadmin@example.com", "password": "password123"})
        if res.status_code != 200:
            print("Login failed", res.text)
            return
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get dealers
        res = await client.get("http://127.0.0.1:8000/admin/dealers", headers=headers)
        dealers = res.json()
        if not dealers:
            print("No dealers found")
            return
            
        dealer = dealers[0]
        print("Dealer ID:", dealer["id"], "Current Partner ID:", dealer.get("partner_id"))
        
        # Update dealer
        payload = {"partner_id": 1} # Assuming partner 1 exists
        res = await client.patch(f"http://127.0.0.1:8000/admin/dealers/{dealer['id']}", json=payload, headers=headers)
        print("Update response:", res.status_code, res.text)
        
        # Fetch again
        res = await client.get("http://127.0.0.1:8000/admin/dealers", headers=headers)
        dealers = res.json()
        updated_dealer = next((d for d in dealers if d["id"] == dealer["id"]), None)
        print("After update Partner ID:", updated_dealer.get("partner_id"))

if __name__ == "__main__":
    asyncio.run(main())
