import logging

gst_logger = logging.getLogger("gst")

def log_gst_resolution(product_id, tax_category_id, tax_rule_id, tax_category, resolution_path, status):
    cat_name = tax_category.name if tax_category else "N/A"
    rate = f"{tax_category.igst_rate or (tax_category.cgst_rate + tax_category.sgst_rate)}%" if tax_category else "N/A"
    gst_logger.info(
        "\n[GST] Tax Resolution\n"
        f"Product ID: {product_id}\n"
        f"Resolution Path: {resolution_path}\n"
        f"Using tax_category_id: {tax_category_id or 'NULL'}\n"
        f"GST Slab Found: {rate}\n"
        f"Product Tax Rule: {'Not Used' if not tax_rule_id else f'ID {tax_rule_id}'}\n"
        f"Status: {status}"
    )


