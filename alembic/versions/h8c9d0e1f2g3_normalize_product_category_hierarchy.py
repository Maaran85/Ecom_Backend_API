"""normalize_product_category_hierarchy

Revision ID: h8c9d0e1f2g3
Revises: g7b8c9d0e1f2
Create Date: 2026-10-03 21:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'h8c9d0e1f2g3'
down_revision: Union[str, None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Normalize 'Headphones -Boat' to root category 4 (Electronics) and subcategory 222 (Headphones)
    op.execute("""
        UPDATE products
        SET category_id = 4, subcategory_id = 222
        WHERE id = 'f97557ce-8af8-41b9-9f61-05dd19cfad46'
           OR name ILIKE '%Headphones -Boat%'
           OR name ILIKE '%Headphones - Boat%';
    """)

    # 2. Normalize 'Watch' to root category 4 (Electronics) and subcategory 219 (Smart Watches)
    op.execute("""
        UPDATE products
        SET category_id = 4, subcategory_id = 219
        WHERE id = '8ec1a84a-fec5-4776-b61b-2c6317d663b6'
           OR (name = 'Watch' AND category_id = 4 AND (subcategory_id = 218 OR subcategory_id IS NULL));
    """)

    # 3. Normalize 'Teddy Bear Product F' and test records to root category 317 (Men's Fashion) and subcategory 318 (Top Wear)
    op.execute("""
        UPDATE products
        SET category_id = 317, subcategory_id = 318
        WHERE id IN ('cdd51f51-440d-4611-b247-f7100e2a70f7', 'a2b09ee4-283f-426b-a512-9116f3dce59b')
           OR (category_id = 318 AND subcategory_id IS NULL);
    """)

def downgrade() -> None:
    pass
