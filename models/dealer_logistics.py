from sqlalchemy import Column, Integer, Boolean, ForeignKey, Table
from core.database import Base

dealer_logistics_mapping = Table(
    'dealer_logistics_mapping',
    Base.metadata,
    Column('dealer_id', Integer, ForeignKey('dealers.id', ondelete="CASCADE"), primary_key=True),
    Column('logistics_partner_id', Integer, ForeignKey('logistics_partners.id', ondelete="CASCADE"), primary_key=True),
    Column('is_default', Boolean, default=False)
)
