from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from datetime import datetime
from models import TaxCategory, TaxRule, Product, Category, Dealer, Order, OrderItem

class TaxService:
    @staticmethod
    async def get_applicable_tax_rule(db: AsyncSession, product_id: int):
        """
        Finds the applicable tax rule for a product.
        Priority:
        1. Product-specific rule
        2. Category-level rule
        3. Fallback (e.g., Default 18% or configured default)
        """
        product = await db.get(Product, product_id)
        if not product:
            return None

        # 1. Product-specific rule
        if product.tax_rule_id:
            rule = await db.get(TaxRule, product.tax_rule_id)
            if rule and rule.is_active:
                return rule
                
        # 2. Category-level rule
        # Search for rules matching the category
        result = await db.execute(
            select(TaxRule)
            .where(and_(TaxRule.category_id == product.category_id, TaxRule.is_active == True))
            .order_by(TaxRule.priority.desc())
            .limit(1)
        )
        rule = result.scalar_one_or_none()
        if rule:
            return rule
            
        # Optional: check parent category if no rule on direct category
        if product.category and product.category.parent_id:
             result = await db.execute(
                 select(TaxRule)
                 .where(and_(TaxRule.category_id == product.category.parent_id, TaxRule.is_active == True))
                 .order_by(TaxRule.priority.desc())
                 .limit(1)
             )
             rule = result.scalar_one_or_none()
             if rule:
                 return rule

        return None

    @staticmethod
    async def calculate_item_tax(db: AsyncSession, inclusive_price: float, qty: int, product_id: int, buyer_state: str, seller_state: str):
        """
        Parses B2C tax-inclusive pricing into Net Taxable Value and Tax Amounts.
        Supports Inter-state (IGST) vs Intra-state (CGST+SGST).
        """
        rule = await TaxService.get_applicable_tax_rule(db, product_id)
        
        # Default if no rule found
        cgst_rate = 0.0
        sgst_rate = 0.0
        igst_rate = 0.0
        tax_category_id = None
        
        if rule:
            tax_category = await db.get(TaxCategory, rule.tax_category_id)
            if tax_category:
                tax_category_id = tax_category.id
                cgst_rate = tax_category.cgst_rate
                sgst_rate = tax_category.sgst_rate
                igst_rate = tax_category.igst_rate
                
        is_inter_state = buyer_state != seller_state if (buyer_state and seller_state) else False
        
        # Determine total applicable rate
        total_rate = igst_rate if is_inter_state else (cgst_rate + sgst_rate)
        
        # The price passed in is INCLUSIVE of this rate.
        # Math: Net Taxable Value = Inclusive Price / (1 + Rate%)
        gross_value = inclusive_price * qty
        taxable_amount = gross_value / (1 + (total_rate / 100))
        total_tax = gross_value - taxable_amount
        
        # Split GST components
        cgst_amount = 0.0
        sgst_amount = 0.0
        igst_amount = 0.0
        
        if is_inter_state:
            igst_amount = total_tax
        else:
            # Assuming CGST and SGST are equal splits of the total, which they usually are in India
            cgst_amount = total_tax / 2
            sgst_amount = total_tax / 2
            
        return {
            "tax_category_id": tax_category_id,
            "taxable_amount": round(taxable_amount, 2),
            "cgst_rate": cgst_rate,
            "sgst_rate": sgst_rate,
            "igst_rate": igst_rate,
            "cgst_amount": round(cgst_amount, 2),
            "sgst_amount": round(sgst_amount, 2),
            "igst_amount": round(igst_amount, 2),
            "total_tax": round(total_tax, 2),
            "is_inter_state": is_inter_state
        }
    
    @staticmethod
    async def generate_tax_invoice_number(db: AsyncSession) -> str:
        """Generates a sequential tax invoice number like TAX-2026-000042"""
        year = datetime.now().year
        
        # Get count of orders this year with tax invoices
        result = await db.execute(
            select(func.count(Order.id))
            .where(
                and_(
                    Order.tax_invoice_no.isnot(None),
                    func.extract('year', Order.created_at) == year
                )
            )
        )
        count = result.scalar() or 0
        
        sequence_number = str(count + 1).zfill(6)
        return f"TAX-{year}-{sequence_number}"
