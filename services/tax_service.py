from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, or_
from datetime import datetime
from models import TaxCategory, TaxRule, Product, Category, Dealer, Order, OrderItem

class TaxService:
    @staticmethod
    async def get_applicable_tax_rule(db: AsyncSession, product_id: int, product: Optional[Product] = None):
        """
        Finds the applicable tax rule for a product.
        Priority:
        1. Product-specific rule
        2. Category-level rule
        3. Fallback (e.g., Default 18% or configured default)
        """
        if product is None and product_id:
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
        if product.category_id:
             category = await db.get(Category, product.category_id)
             if category and category.parent_id:
                 result = await db.execute(
                     select(TaxRule)
                     .where(and_(TaxRule.category_id == category.parent_id, TaxRule.is_active == True))
                     .order_by(TaxRule.priority.desc())
                     .limit(1)
                 )
                 rule = result.scalar_one_or_none()
                 if rule:
                     return rule

        # 3. Global fallback rule
        result = await db.execute(
            select(TaxRule)
            .where(and_(TaxRule.category_id.is_(None), TaxRule.product_id.is_(None), TaxRule.is_active == True))
            .order_by(TaxRule.priority.desc())
            .limit(1)
        )
        rule = result.scalar_one_or_none()
        if rule:
            return rule

        return None

    @staticmethod
    async def calculate_item_tax(
        db: AsyncSession,
        base_price: float,
        qty: int,
        product_id: int,
        buyer_state: str,
        seller_state: str,
        is_inclusive: bool = True,
        product: Optional[Product] = None,
        tax_category: Optional[TaxCategory] = None
    ):
        """
        Parses pricing into Net Taxable Value and Tax Amounts.
        Supports Inter-state (IGST) vs Intra-state (CGST+SGST).
        If is_inclusive is True, base_price includes tax. If False, base_price excludes tax.
        Accepts pre-loaded product and tax_category to avoid redundant queries during checkout.
        """
        if product is None and product_id:
            product = await db.get(Product, product_id)

        rule = await TaxService.get_applicable_tax_rule(db, product_id, product=product)
        
        # Default if no rule found
        cgst_rate = 0.0
        sgst_rate = 0.0
        igst_rate = 0.0
        tax_category_id = None
        
        if tax_category:
            tax_category_id = tax_category.id
            cgst_rate = tax_category.cgst_rate
            sgst_rate = tax_category.sgst_rate
            igst_rate = tax_category.igst_rate
        elif product and product.tax_category_id:
            tax_category = await db.get(TaxCategory, product.tax_category_id)
            if tax_category:
                tax_category_id = tax_category.id
                cgst_rate = tax_category.cgst_rate
                sgst_rate = tax_category.sgst_rate
                igst_rate = tax_category.igst_rate
        elif rule and rule.tax_category_id:
            tax_category = await db.get(TaxCategory, rule.tax_category_id)
            if tax_category:
                tax_category_id = tax_category.id
                cgst_rate = tax_category.cgst_rate
                sgst_rate = tax_category.sgst_rate
                igst_rate = tax_category.igst_rate
                
        is_inter_state = buyer_state != seller_state if (buyer_state and seller_state) else False
        
        # Determine total applicable rate
        total_rate = igst_rate if is_inter_state else (cgst_rate + sgst_rate)
        
        if is_inclusive:
            # The price passed in is INCLUSIVE of this rate.
            # Math: Net Taxable Value = Inclusive Price / (1 + Rate%)
            gross_value = base_price * qty
            taxable_amount = gross_value / (1 + (total_rate / 100))
            total_tax = gross_value - taxable_amount
        else:
            # The price passed in is EXCLUSIVE of this rate.
            taxable_amount = base_price * qty
            total_tax = taxable_amount * (total_rate / 100)
            gross_value = taxable_amount + total_tax
        
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
        """Generates a strictly sequential unique tax invoice number like TAX-2026-000042"""
        from models.invoice import OrderInvoice
        year = datetime.now().year
        prefix = f"TAX-{year}-"
        
        # Efficiently fetch the maximum existing invoice number using index
        result = await db.execute(
            select(func.max(OrderInvoice.invoice_number))
            .where(OrderInvoice.invoice_number.like(f"{prefix}%"))
        )
        max_inv = result.scalar_one_or_none()
        
        max_seq = 0
        if max_inv:
            try:
                seq_part = str(max_inv).replace(prefix, "").strip()
                max_seq = int(seq_part)
            except (ValueError, TypeError):
                max_seq = 0
                
        next_seq = max_seq + 1
        generated_number = f"{prefix}{str(next_seq).zfill(6)}"
        return generated_number

    @staticmethod
    async def create_order_invoice_with_retry(
        db: AsyncSession,
        order_id: int,
        dealer_id,
        total_amount: float,
        tax_amount: float,
        max_retries: int = 5
    ):
        """
        Inserts an OrderInvoice with resilience against concurrent invoice-number uniqueness collisions.
        Uses a transaction savepoint (begin_nested) so that collisions roll back only the savepoint,
        allowing invoice number recalculation without invalidating the parent transaction.
        Only retries when the error is confirmed to be an invoice_number unique constraint violation.
        """
        from models.invoice import OrderInvoice
        from sqlalchemy import insert as sql_insert
        from sqlalchemy.exc import IntegrityError
        
        last_error = None
        for attempt in range(max_retries):
            invoice_num = await TaxService.generate_tax_invoice_number(db)
            try:
                async with db.begin_nested():
                    res = await db.execute(
                        sql_insert(OrderInvoice).values(
                            order_id=order_id,
                            dealer_id=dealer_id,
                            invoice_number=invoice_num,
                            total_amount=total_amount,
                            tax_amount=tax_amount,
                            is_reverse_charge=False
                        ).returning(OrderInvoice.id)
                    )
                    return invoice_num
            except IntegrityError as exc:
                last_error = exc
                # Confirm the failure is specifically an invoice_number uniqueness collision
                err_str = str(exc).lower()
                is_invoice_collision = (
                    "invoice_number" in err_str or
                    "order_invoices_invoice_number_key" in err_str or
                    "unique constraint" in err_str and "invoice" in err_str
                )
                if not is_invoice_collision:
                    raise exc
                # If collision and attempts remain, loop recalculates func.max on the next attempt
                continue

        if last_error:
            raise last_error

