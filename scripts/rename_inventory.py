import os
import re

files_to_update = [
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\test_stock_property.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\scripts\migrate_hub_inventory.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\routers\cart.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\routers\dealers.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\routers\inventory.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\routers\showroom.py",
    r"d:\My Project\OnlineshopApp\Ecom_Backend_API\schemas\showroom.py"
]

for filepath in files_to_update:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace HubInventory with ProductInventory
        new_content = content.replace("HubInventory", "ProductInventory")
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {filepath}")
    else:
        print(f"File not found: {filepath}")
