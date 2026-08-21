from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from core.database import Base


class BillingSlab(Base):
    """
    Price-slab based billing configuration for platform charges:
      - Marketplace Charges (dealer % + customer %)
      - Marketing Commission (dealer %)
      - Logistics Charges (dealer % or customer %)

    The slab is selected using the final net selling price after discount:
      min_price <= gross_sale AND (max_price IS NULL OR gross_sale <= max_price)
    """
    __tablename__ = "billing_slabs"

    id = Column(Integer, primary_key=True, index=True)

    # Category key: 'marketplace', 'marketing', 'logistics'
    category_key = Column(String, nullable=False, index=True)

    min_price = Column(Float, nullable=False, default=0.0)
    max_price = Column(Float, nullable=True)  # NULL = open-ended range (e.g. > 1000)

    dealer_percentage = Column(Float, nullable=True)     # e.g. 0.02 for 2%
    customer_percentage = Column(Float, nullable=True)   # e.g. 0.005 for 0.5% (nullable if N/A)

    dealer_amount = Column(Float, nullable=True)         # e.g. 100.0 for Referral Dealer Amount
    customer_amount = Column(Float, nullable=True)       # e.g. 5.0 for Spin & Win ₹5 or Referral Customer Amount

    gst_type = Column(String, nullable=True)             # e.g. "STANDARD_18", "INTRA_STATE", "EXEMPT"
    sac_hsn_code = Column(String, nullable=True)         # e.g. "998314"
    calculation_basis = Column(String, nullable=True)    # e.g. "Net Selling Price"
    notes = Column(String, nullable=True)                # e.g. "Payment to be made after 3 transactions"

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        max_str = f"₹{self.max_price}" if self.max_price is not None else "∞"
        return f"<BillingSlab category={self.category_key} range=₹{self.min_price}-{max_str} dealer={self.dealer_percentage*100}% customer={self.customer_percentage*100 if self.customer_percentage else 0}%>"
