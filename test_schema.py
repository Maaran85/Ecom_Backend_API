import asyncio
import sys
import os

# Add Ecom_Backend_API to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from routers.admin import DealerAdminUpdate

print("DealerAdminUpdate Schema Fields:")
for name, field in DealerAdminUpdate.model_fields.items():
    print(f"- {name}: {field.annotation}")

data = {"partner_id": 1, "business_name": "Test Dealer"}
model = DealerAdminUpdate(**data)
print("Parsed Model:", model.model_dump(exclude_unset=True))
