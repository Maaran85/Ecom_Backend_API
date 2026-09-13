import io
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
try:
    from num2words import num2words
except ImportError:
    def num2words(num, **kwargs):
        return str(num)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether, PageBreak
)

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def _register_unicode_font():
    """
    Registers a Unicode-compatible font (DejaVuSans or system font) for ReportLab
    so that the Indian Rupee symbol (₹ / U+20B9) renders cleanly without missing-glyph black squares.
    """
    font_name = "DejaVuSans"
    bold_font_name = "DejaVuSans-Bold"

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    asset_font = os.path.join(base_dir, "assets", "fonts", "DejaVuSans.ttf")
    asset_font_bold = os.path.join(base_dir, "assets", "fonts", "DejaVuSans-Bold.ttf")

    candidate_pairs = [
        (asset_font, asset_font_bold),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ]

    for norm_path, bold_path in candidate_pairs:
        if os.path.exists(norm_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, norm_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(bold_font_name, bold_path))
                else:
                    pdfmetrics.registerFont(TTFont(bold_font_name, norm_path))
                return font_name, bold_font_name
            except Exception:
                continue

    return "Helvetica", "Helvetica-Bold"

FONT_NORMAL, FONT_BOLD = _register_unicode_font()

def round_curr(val: float) -> float:
    """Standard half-up currency rounding to 2 decimal places using Decimal exact arithmetic"""
    if val is None:
        return 0.0
    d = Decimal(str(round(val, 6)))
    return float(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def calc_gst_pct(basic_amt: float, rate_pct: float) -> float:
    """Exact decimal GST percentage calculation with half-up rounding"""
    if not basic_amt or not rate_pct:
        return 0.0
    d_basic = Decimal(str(round(basic_amt, 4)))
    d_rate = Decimal(str(rate_pct)) / Decimal('100')
    return float((d_basic * d_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def _resolve_image_local_path(url_or_path) -> getattr:
    if not url_or_path:
        return None

    str_path = str(url_or_path).strip()
    if os.path.exists(str_path) and os.path.isfile(str_path):
        return str_path

    cleaned = str_path
    if "/uploads/" in cleaned:
        cleaned = cleaned.split("/uploads/", 1)[1]
    elif cleaned.startswith("/"):
        cleaned = cleaned.lstrip("/")

    candidates = [
        cleaned,
        os.path.join("uploads", cleaned),
        os.path.join(os.getcwd(), cleaned),
        os.path.join(os.getcwd(), "uploads", cleaned),
    ]

    for candidate in candidates:
        if os.path.exists(candidate) and os.path.isfile(candidate):
            return candidate

    return None


def generate_invoice_pdf(invoice, dealer, order, order_items, billing_address, shipping_address, marketplace_sac="998314", marketing_sac="998314", logistics_sac="996812"):
    """
    Generates Customer Invoice PDF following exact multi-section format (STANDARDIZED GST-EXCLUSIVE ROUNDING MODEL):
    
    Rounding Policy:
    1. Calculate GST from unrounded taxable/basic amount.
    2. Round each individual GST component (CGST, SGST, IGST) to 2 decimal places using HALF_UP exact decimal arithmetic.
    3. Add rounded GST components: Tax Amount = CGST + SGST (or IGST).
    4. Calculate component Total = Basic Amount + Tax Amount (rounded to 2 decimals).
    5. Grand Total = sum of the already-rounded section totals (rounded to 2 decimals).
    
    Guarantees 100% mathematical reconciliation with zero 1-paise discrepancies between displayed components and totals!
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24
    )
    
    styles = getSampleStyleSheet()
    
    style_logo = ParagraphStyle(
        'HeaderLogo',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=20,
        leading=22,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_title_center = ParagraphStyle(
        'TitleCenter',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=12,
        leading=14.5,
        alignment=1,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_title_right = ParagraphStyle(
        'TitleRight',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=12,
        leading=14,
        alignment=2
    )
    style_normal = ParagraphStyle(
        'InvNormal',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=8,
        leading=10.5
    )
    style_bold = ParagraphStyle(
        'InvBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5
    )
    style_normal_right = ParagraphStyle(
        'InvNormalRight',
        parent=style_normal,
        alignment=2
    )
    style_bold_right = ParagraphStyle(
        'InvBoldRight',
        parent=style_bold,
        alignment=2
    )
    style_th = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7.5,
        leading=9,
        alignment=0
    )
    style_th_center = ParagraphStyle(
        'TableHeaderCenter',
        parent=style_th,
        alignment=1
    )
    style_td = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=7.5,
        leading=9.5
    )
    style_td_center = ParagraphStyle(
        'TableCellCenter',
        parent=style_td,
        alignment=1
    )
    style_td_right = ParagraphStyle(
        'TableCellRight',
        parent=style_td,
        alignment=2
    )
    style_section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_footer_small = ParagraphStyle(
        'FooterSmall',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.5,
        leading=8,
        textColor=colors.HexColor('#555555'),
        alignment=1
    )

    story = []

    dealer_brand = getattr(dealer, 'business_name', None) if dealer else None
    logo_text = str(dealer_brand).upper() if dealer_brand else "ONLINE SHOP"
    
    # 1. Top Centered Invoice Title Block
    t_title = Table([
        [
            Paragraph("<b>Tax Invoice / Bill of Supply / Cash Memo</b><br/><font size='8.5' face='Helvetica' color='#444'>(Original for Recipient)</font>", style_title_center)
        ]
    ], colWidths=[547])
    t_title.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_title)
    story.append(Spacer(1, 2))

    # 2. Store / Seller Header Block
    t_header = Table([[Paragraph(f"<b>{logo_text}</b>", style_logo)]], colWidths=[547])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 4))

    dealer_name = getattr(dealer, 'business_name', '') if dealer else 'SELLER'
    dealer_addr = getattr(dealer, 'business_address', '') if dealer else ''
    dealer_city = getattr(dealer, 'city', '') if dealer else ''
    def _get_state_info(obj):
        try:
            rel = obj.__dict__.get('state_rel') if obj else None
            if rel:
                return str(getattr(rel, 'name', '') or ''), str(getattr(rel, 'state_code', '29') or '29')
        except Exception:
            pass
        return '', '29'

    dealer_state_name, dealer_state_code = _get_state_info(dealer)
    dealer_pin = getattr(dealer, 'pincode', '') if dealer else ''
    pan_no = getattr(dealer, 'pan_number', '') if dealer else ''
    gst_no = getattr(dealer, 'gst_number', '') if dealer else ''

    sold_by_html = (
        f"<b>Sold By :</b><br/>"
        f"<b>{str(dealer_name).upper()}</b><br/>"
        f"{dealer_addr}<br/>"
        f"{dealer_city}, {dealer_state_name}, {dealer_pin}<br/>"
        f"IN<br/>"
        f"<b>PAN No:</b> {pan_no}<br/>"
        f"<b>GSTIN:</b> {gst_no}"
    )

    b_name = billing_address.full_name if billing_address else (shipping_address.full_name if shipping_address else 'Recipient')
    b_addr1 = getattr(billing_address, 'address_line1', '') if billing_address else ''
    b_addr2 = getattr(billing_address, 'address_line2', '') if billing_address else ''
    b_city = getattr(billing_address, 'city', '') if billing_address else ''
    b_pin = getattr(billing_address, 'pincode', '') if billing_address else ''
    b_state_name, b_state_code = _get_state_info(billing_address)
    if not b_state_name: b_state_name = dealer_state_name
    if not b_state_code: b_state_code = dealer_state_code

    b_lines = [b_addr1, b_addr2, f"{b_city or ''}, {b_state_name or ''}, {b_pin or ''}", "IN"]
    b_html = f"<b>Billing Address :</b><br/><b>{b_name}</b><br/>" + "<br/>".join([str(l).strip() for l in b_lines if l and str(l).strip()])
    b_html += f"<br/><b>State Code:</b> {b_state_code}"

    s_name = shipping_address.full_name if shipping_address else b_name
    s_addr1 = getattr(shipping_address, 'address_line1', '') if shipping_address else b_addr1
    s_addr2 = getattr(shipping_address, 'address_line2', '') if shipping_address else b_addr2
    s_city = getattr(shipping_address, 'city', '') if shipping_address else b_city
    s_pin = getattr(shipping_address, 'pincode', '') if shipping_address else b_pin
    s_state_name, s_state_code = _get_state_info(shipping_address)
    if not s_state_name: s_state_name = b_state_name
    if not s_state_code: s_state_code = b_state_code

    s_lines = [s_addr1, s_addr2, f"{s_city or ''}, {s_state_name or ''}, {s_pin or ''}", "IN"]
    s_html = f"<b>Shipping Address :</b><br/><b>{s_name}</b><br/>" + "<br/>".join([str(l).strip() for l in s_lines if l and str(l).strip()])
    s_html += (
        f"<br/><b>State Code:</b> {s_state_code}<br/>"
        f"<b>Place of Supply:</b> {s_state_name.upper() if s_state_name else 'INTRA-STATE'}"
    )

    right_col_html = f"{b_html}<br/><br/>{s_html}"

    addr_data = [
        [
            Paragraph(sold_by_html, style_normal),
            Paragraph(right_col_html, style_normal_right)
        ]
    ]
    t_addr = Table(addr_data, colWidths=[260, 287])
    t_addr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_addr)
    story.append(Spacer(1, 4))

    order_num = getattr(order, 'order_number', '') or str(getattr(order, 'id', ''))
    order_dt = order.created_at.strftime('%d.%m.%Y') if getattr(order, 'created_at', None) else datetime.now().strftime('%d.%m.%Y')
    inv_num = getattr(invoice, 'invoice_number', '')
    inv_dt = invoice.invoice_date.strftime('%d.%m.%Y') if getattr(invoice, 'invoice_date', None) else datetime.now().strftime('%d.%m.%Y')

    meta_left = f"<b>Order Number:</b> {order_num}<br/><b>Order Date:</b> {order_dt}"
    meta_right = (
        f"<b>Invoice Number:</b> {inv_num}<br/>"
        f"<b>Invoice Date:</b> {inv_dt}"
    )

    t_meta = Table([
        [
            Paragraph(meta_left, style_normal),
            Paragraph(meta_right, style_normal_right)
        ]
    ], colWidths=[260, 287])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 6))

    col_widths = [20, 50, 147, 43, 20, 43, 48, 38, 38, 48, 52]

    def make_table_header():
        return [
            Paragraph("slno", style_th_center),
            Paragraph("Product ID", style_th_center),
            Paragraph("Description", style_th),
            Paragraph("Unit<br/>price", style_th_center),
            Paragraph("Qty", style_th_center),
            Paragraph("Discount", style_th_center),
            Paragraph("Net<br/>Amount", style_th_center),
            Paragraph("Tax<br/>Rate", style_th_center),
            Paragraph("GST<br/>type", style_th_center),
            Paragraph("Tax<br/>Amount", style_th_center),
            Paragraph("Total<br/>Amount", style_th_center)
        ]

    is_inter_state_order = getattr(order, 'is_inter_state', False) if order else False

    # SECTION 1: PRODUCT
    story.append(Paragraph("<b>1. PRODUCT</b>", style_section_title))
    story.append(Spacer(1, 4))
    prod_table_data = [make_table_header()]

    prod_ids = []
    total_prod_net = 0.0
    total_prod_tax = 0.0
    total_prod_gross = 0.0

    for idx, item in enumerate(order_items):
        prod_id_str = str(getattr(item, 'product_id', ''))[:8] if getattr(item, 'product_id', None) else f"PRD-{idx+1}"
        if prod_id_str not in prod_ids:
            prod_ids.append(prod_id_str)
        desc_name = item.product.name if getattr(item, 'product', None) else "Product Item"
        prod_desc = getattr(item.product, 'description', '') if getattr(item, 'product', None) else ''
        hsn = getattr(item, 'hsn_code', '') or getattr(item.product, 'hsn_code', '') if getattr(item, 'product', None) else ''
        
        desc_html = f"<b>{desc_name}</b>"
        if prod_desc:
            desc_html += f"<br/><font color='#555555' size='6.5'>{prod_desc[:40]}</font>"
        if hsn:
            desc_html += f"<br/><font color='#333333'><b>HSN:</b> {hsn}</font>"

        item_qty = getattr(item, 'quantity', 1) or 1
        unit_price_excl = round_curr(getattr(item, 'price', 0.0) or 0.0)
        item_discount = round_curr(getattr(item, 'discount_amount', 0.0) or 0.0)

        gross_net = unit_price_excl * item_qty
        net_amt = round_curr(max(0.0, gross_net - item_discount))

        cgst_rate = getattr(item, 'cgst_rate', 0.0) or 0.0
        sgst_rate = getattr(item, 'sgst_rate', 0.0) or 0.0
        igst_rate = getattr(item, 'igst_rate', 0.0) or 0.0

        if (is_inter_state_order and (igst_rate > 0 or getattr(item, 'igst_amount', 0) > 0)) or igst_rate > 0:
            display_rate = igst_rate if igst_rate > 0 else (cgst_rate + sgst_rate if (cgst_rate + sgst_rate) > 0 else 18.0)
            igst_amt = calc_gst_pct(net_amt, display_rate)
            cgst_amt = 0.0
            sgst_amt = 0.0
            item_tax_amt = igst_amt
            tax_rate_html = f"{display_rate:.0f}%"
            tax_type_html = "IGST"
            tax_amt_html = f"₹{igst_amt:.2f}"
        else:
            c_rate = cgst_rate if cgst_rate > 0 else 9.0
            s_rate = sgst_rate if sgst_rate > 0 else 9.0
            cgst_amt = calc_gst_pct(net_amt, c_rate)
            sgst_amt = calc_gst_pct(net_amt, s_rate)
            igst_amt = 0.0
            item_tax_amt = round_curr(cgst_amt + sgst_amt)
            tax_rate_html = f"{c_rate:.0f}%<br/>{s_rate:.0f}%"
            tax_type_html = "CGST<br/>SGST"
            tax_amt_html = f"₹{cgst_amt:.2f}<br/>₹{sgst_amt:.2f}"

        item_total = round_curr(net_amt + item_tax_amt)

        prod_table_data.append([
            Paragraph(str(idx + 1), style_td_center),
            Paragraph(prod_id_str, style_td_center),
            Paragraph(desc_html, style_td),
            Paragraph(f"₹{unit_price_excl:.2f}", style_td_right),
            Paragraph(str(item_qty), style_td_center),
            Paragraph(f"₹{item_discount:.2f}", style_td_right),
            Paragraph(f"₹{net_amt:.2f}", style_td_right),
            Paragraph(tax_rate_html, style_td_center),
            Paragraph(tax_type_html, style_td_center),
            Paragraph(tax_amt_html, style_td_right),
            Paragraph(f"₹{item_total:.2f}", style_td_right)
        ])

        total_prod_net = round_curr(total_prod_net + net_amt)
        total_prod_tax = round_curr(total_prod_tax + item_tax_amt)
        total_prod_gross = round_curr(total_prod_gross + item_total)

    display_prod_id = ", ".join(prod_ids) if prod_ids else (str(getattr(order, 'id', ''))[:8] or "PRD-1")

    prod_table_data.append([
        Paragraph("<b>PRODUCT TOTAL:</b>", style_bold),
        "", "", "", "", "",
        Paragraph(f"<b>₹{total_prod_net:.2f}</b>", style_bold_right),
        "", "",
        Paragraph(f"<b>₹{total_prod_tax:.2f}</b>", style_bold_right),
        Paragraph(f"<b>₹{total_prod_gross:.2f}</b>", style_bold_right)
    ])

    t_prod = Table(prod_table_data, colWidths=col_widths, repeatRows=1)
    t_prod.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEF2FF')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (5, -1)),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_prod)
    story.append(Spacer(1, 10))

    # SECTION 2: MARKETPLACE FEES
    story.append(Paragraph("<b>2. MARKETPLACE FEES</b>", style_section_title))
    story.append(Spacer(1, 4))
    mkt_table_data = [make_table_header()]
    mkt_cust_charge = sum(getattr(item, 'marketplace_customer_charge', 0.0) or 0.0 for item in order_items) if order_items else 0.0
    if not mkt_cust_charge:
        plat_fee = getattr(order, 'platform_fee_amount', 0.0) or 0.0
        mkt_cust_charge = plat_fee if plat_fee > 0 else 2.38

    mkt_sac_code = marketplace_sac or "998314"
    mkt_desc_html = f"<b>Marketplace Platform Services</b><br/><font color='#333333'><b>SAC:</b> {mkt_sac_code}</font>"
    mkt_net_amt = round_curr(mkt_cust_charge)

    if is_inter_state_order:
        mkt_igst_amt = calc_gst_pct(mkt_net_amt, 18.0)
        mkt_tax_amt = mkt_igst_amt
        mkt_rate_html = "18%"
        mkt_type_html = "IGST"
        mkt_tax_amt_html = f"₹{mkt_igst_amt:.2f}"
    else:
        mkt_cgst_amt = calc_gst_pct(mkt_net_amt, 9.0)
        mkt_sgst_amt = calc_gst_pct(mkt_net_amt, 9.0)
        mkt_tax_amt = round_curr(mkt_cgst_amt + mkt_sgst_amt)
        mkt_rate_html = "9%<br/>9%"
        mkt_type_html = "CGST<br/>SGST"
        mkt_tax_amt_html = f"₹{mkt_cgst_amt:.2f}<br/>₹{mkt_sgst_amt:.2f}"

    mkt_total_amt = round_curr(mkt_net_amt + mkt_tax_amt)
    mkt_table_data.append([
        Paragraph("1", style_td_center),
        Paragraph(display_prod_id, style_td_center),
        Paragraph(mkt_desc_html, style_td),
        Paragraph(f"₹{mkt_net_amt:.2f}", style_td_right),
        Paragraph("1", style_td_center),
        Paragraph("₹0.00", style_td_right),
        Paragraph(f"₹{mkt_net_amt:.2f}", style_td_right),
        Paragraph(mkt_rate_html, style_td_center),
        Paragraph(mkt_type_html, style_td_center),
        Paragraph(mkt_tax_amt_html, style_td_right),
        Paragraph(f"₹{mkt_total_amt:.2f}", style_td_right)
    ])
    mkt_table_data.append([
        Paragraph("<b>MARKETPLACE FEES TOTAL:</b>", style_bold),
        "", "", "", "", "",
        Paragraph(f"<b>₹{mkt_net_amt:.2f}</b>", style_bold_right),
        "", "",
        Paragraph(f"<b>₹{mkt_tax_amt:.2f}</b>", style_bold_right),
        Paragraph(f"<b>₹{mkt_total_amt:.2f}</b>", style_bold_right)
    ])

    t_mkt = Table(mkt_table_data, colWidths=col_widths, repeatRows=1)
    t_mkt.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0FDF4')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (5, -1)),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_mkt)
    story.append(Spacer(1, 10))

    # SECTION 3: SHIPPING SERVICES
    story.append(Paragraph("<b>3. SHIPPING SERVICES</b>", style_section_title))
    story.append(Spacer(1, 4))
    ship_table_data = [make_table_header()]
    ship_cust_charge = sum(getattr(item, 'logistics_customer_charge', 0.0) or 0.0 for item in order_items) if order_items else 0.0
    if not ship_cust_charge:
        del_charge = getattr(order, 'delivery_charge', 0.0) or 0.0
        ship_cust_charge = del_charge if del_charge > 0 else 42.75

    ship_sac_code = logistics_sac or "996812"
    ship_desc_html = f"<b>Logistics & Shipping Services</b><br/><font color='#333333'><b>SAC:</b> {ship_sac_code}</font>"
    ship_net_amt = round_curr(ship_cust_charge)

    if is_inter_state_order:
        ship_igst_amt = calc_gst_pct(ship_net_amt, 18.0)
        ship_tax_amt = ship_igst_amt
        ship_rate_html = "18%"
        ship_type_html = "IGST"
        ship_tax_amt_html = f"₹{ship_igst_amt:.2f}"
    else:
        ship_cgst_amt = calc_gst_pct(ship_net_amt, 9.0)
        ship_sgst_amt = calc_gst_pct(ship_net_amt, 9.0)
        ship_tax_amt = round_curr(ship_cgst_amt + ship_sgst_amt)
        ship_rate_html = "9%<br/>9%"
        ship_type_html = "CGST<br/>SGST"
        ship_tax_amt_html = f"₹{ship_cgst_amt:.2f}<br/>₹{ship_sgst_amt:.2f}"

    ship_total_amt = round_curr(ship_net_amt + ship_tax_amt)
    ship_table_data.append([
        Paragraph("1", style_td_center),
        Paragraph(display_prod_id, style_td_center),
        Paragraph(ship_desc_html, style_td),
        Paragraph(f"₹{ship_net_amt:.2f}", style_td_right),
        Paragraph("1", style_td_center),
        Paragraph("₹0.00", style_td_right),
        Paragraph(f"₹{ship_net_amt:.2f}", style_td_right),
        Paragraph(ship_rate_html, style_td_center),
        Paragraph(ship_type_html, style_td_center),
        Paragraph(ship_tax_amt_html, style_td_right),
        Paragraph(f"₹{ship_total_amt:.2f}", style_td_right)
    ])
    ship_table_data.append([
        Paragraph("<b>SHIPPING SERVICES TOTAL:</b>", style_bold),
        "", "", "", "", "",
        Paragraph(f"<b>₹{ship_net_amt:.2f}</b>", style_bold_right),
        "", "",
        Paragraph(f"<b>₹{ship_tax_amt:.2f}</b>", style_bold_right),
        Paragraph(f"<b>₹{ship_total_amt:.2f}</b>", style_bold_right)
    ])

    t_ship = Table(ship_table_data, colWidths=col_widths, repeatRows=1)
    t_ship.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FFFBEB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (5, -1)),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ship)
    story.append(Spacer(1, 10))

    # SECTION 4: MARKETING SERVICES (rendered when marketing_customer_charge > 0)
    mktg_cust_charge = sum(getattr(item, 'marketing_customer_charge', 0.0) or 0.0 for item in order_items) if order_items else 0.0
    mktg_net_amt = round_curr(mktg_cust_charge)
    mktg_tax_amt = 0.0
    mktg_total_amt = 0.0

    if mktg_net_amt > 0:
        story.append(Paragraph("<b>4. MARKETING SERVICES</b>", style_section_title))
        story.append(Spacer(1, 4))
        mktg_table_data = [make_table_header()]
        mktg_sac_code = marketing_sac or "998314"
        mktg_desc_html = f"<b>Marketing Platform Services</b><br/><font color='#333333'><b>SAC:</b> {mktg_sac_code}</font>"

        if is_inter_state_order:
            mktg_igst_amt = calc_gst_pct(mktg_net_amt, 18.0)
            mktg_tax_amt = mktg_igst_amt
            mktg_rate_html = "18%"
            mktg_type_html = "IGST"
            mktg_tax_amt_html = f"₹{mktg_igst_amt:.2f}"
        else:
            mktg_cgst_amt = calc_gst_pct(mktg_net_amt, 9.0)
            mktg_sgst_amt = calc_gst_pct(mktg_net_amt, 9.0)
            mktg_tax_amt = round_curr(mktg_cgst_amt + mktg_sgst_amt)
            mktg_rate_html = "9%<br/>9%"
            mktg_type_html = "CGST<br/>SGST"
            mktg_tax_amt_html = f"₹{mktg_cgst_amt:.2f}<br/>₹{mktg_sgst_amt:.2f}"

        mktg_total_amt = round_curr(mktg_net_amt + mktg_tax_amt)
        mktg_table_data.append([
            Paragraph("1", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(mktg_desc_html, style_td),
            Paragraph(f"₹{mktg_net_amt:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph(f"₹{mktg_net_amt:.2f}", style_td_right),
            Paragraph(mktg_rate_html, style_td_center),
            Paragraph(mktg_type_html, style_td_center),
            Paragraph(mktg_tax_amt_html, style_td_right),
            Paragraph(f"₹{mktg_total_amt:.2f}", style_td_right)
        ])
        mktg_table_data.append([
            Paragraph("<b>MARKETING SERVICES TOTAL:</b>", style_bold),
            "", "", "", "", "",
            Paragraph(f"<b>₹{mktg_net_amt:.2f}</b>", style_bold_right),
            "", "",
            Paragraph(f"<b>₹{mktg_tax_amt:.2f}</b>", style_bold_right),
            Paragraph(f"<b>₹{mktg_total_amt:.2f}</b>", style_bold_right)
        ])

        t_mktg = Table(mktg_table_data, colWidths=col_widths, repeatRows=1)
        t_mktg.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
            ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FAF5FF')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (0, -1), (5, -1)),
            ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_mktg)
        story.append(Spacer(1, 10))

    grand_net = round_curr(total_prod_net + mkt_net_amt + ship_net_amt + mktg_net_amt)
    grand_tax = round_curr(total_prod_tax + mkt_tax_amt + ship_tax_amt + mktg_tax_amt)
    grand_total = round_curr(grand_net + grand_tax)

    first_prod_label = order_items[0].product.name[:25] if order_items and getattr(order_items[0], 'product', None) else "Items"
    summary_bullets = [
        f"• Product ({first_prod_label}): ₹{total_prod_gross:.2f} (Basic: ₹{total_prod_net:.2f} + GST: ₹{total_prod_tax:.2f})",
        f"• Marketplace Fees: ₹{mkt_total_amt:.2f} (Basic: ₹{mkt_net_amt:.2f} + GST: ₹{mkt_tax_amt:.2f})",
        f"• Shipping Services: ₹{ship_total_amt:.2f} (Basic: ₹{ship_net_amt:.2f} + GST: ₹{ship_tax_amt:.2f})",
    ]
    if mktg_total_amt > 0:
        summary_bullets.append(f"• Marketing Services: ₹{mktg_total_amt:.2f} (Basic: ₹{mktg_net_amt:.2f} + GST: ₹{mktg_tax_amt:.2f})")

    summary_left_html = "<b>GST-Exclusive Component Summary Breakdown:</b><br/>" + "<br/>".join(summary_bullets)

    summary_right_html = (
        f"<b>Total Basic Amount:</b> ₹{grand_net:.2f}<br/>"
        f"<b>Total Tax Amount:</b> ₹{grand_tax:.2f}<br/>"
        f"<font size='10.5' color='#1E1B4B'><b>INVOICE GRAND TOTAL: ₹{grand_total:.2f}</b></font>"
    )

    t_summary = Table([
        [
            Paragraph(summary_left_html, style_normal),
            Paragraph(summary_right_html, style_bold_right)
        ]
    ], colWidths=[310, 237])
    t_summary.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1E1B4B')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 8))

    try:
        amt_words = num2words(grand_total, lang='en_IN').capitalize() + " only"
    except Exception:
        amt_words = f"Rupees {grand_total:.2f} only"

    sig_url = getattr(dealer, 'signature_image_url', None) if dealer else None
    local_sig_path = _resolve_image_local_path(sig_url)
    sig_cell_elements = [
        Paragraph(f"<b>For {str(dealer_name).upper()}:</b>", style_bold_right),
        Spacer(1, 4)
    ]
    if local_sig_path:
        try:
            sig_img = Image(local_sig_path, width=1.2*inch, height=0.4*inch)
            sig_img.hAlign = 'RIGHT'
            sig_table = Table([[sig_img]], colWidths=[255])
            sig_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            sig_cell_elements.append(sig_table)
        except Exception:
            sig_cell_elements.append(Spacer(1, 10))
    else:
        sig_cell_elements.append(Spacer(1, 10))
    sig_cell_elements.append(Spacer(1, 4))
    sig_cell_elements.append(Paragraph("<b>Authorized Signatory</b>", style_bold_right))

    box_left = [
        Paragraph("<b>Amount in Words:</b>", style_bold),
        Paragraph(f"<b>{amt_words}</b>", style_bold)
    ]

    t_sigbox = Table([[box_left, sig_cell_elements]], colWidths=[280, 267])
    t_sigbox.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (0, 0), 6),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 6),
    ]))
    story.append(t_sigbox)
    story.append(Spacer(1, 4))

    story.append(Paragraph("Whether tax is payable under reverse charge - No", style_normal))
    story.append(Spacer(1, 8))

    pay_method = getattr(order, 'payment_method', 'COD') or 'COD'
    tx_id = getattr(order, 'tracking_number', '') or f"TXN{order_num}"
    tx_time = order.created_at.strftime('%d/%m/%Y, %H:%M:%S hrs') if getattr(order, 'created_at', None) else datetime.now().strftime('%d/%m/%Y, %H:%M:%S hrs')

    bar_data = [
        [
            Paragraph(f"<b>Payment Txn ID:</b> {tx_id}", style_td),
            Paragraph(f"<b>Date & Time:</b> {tx_time}", style_td),
            Paragraph(f"<b>Invoice Value:</b> ₹{grand_total:.2f}", style_td),
            Paragraph(f"<b>Payment Mode:</b> {pay_method}", style_td)
        ]
    ]
    t_bar = Table(bar_data, colWidths=[150, 150, 110, 137])
    t_bar.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_bar)
    story.append(Spacer(1, 10))

    footer_p1 = (
        "Customers desirous of availing input GST credit are requested to provide their GSTIN details at checkout.<br/>"
        "Please note that this customer tax invoice is generated based on GST-exclusive pricing and confirmed Super Admin billing configuration."
    )
    story.append(Paragraph(footer_p1, style_footer_small))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_dealer_settlement_pdf(settlement, dealer, items, marketplace_sac="998314", logistics_sac="996812"):
    """
    Generates Official Dealer Invoice / Settlement Statement PDF using the exact 11-column structure required by the Business Excel:
    Columns: slno | Product ID | Description | Unit price | Qty | Discount | Net Amount | Tax Rate | GST type | Tax Amount | Total Amount
    
    Line Item Rows:
    - Line 14: Net Selling Price (Unit price, Qty, Discount, Net Amount, Tax Rate, GST type, Tax Amount, Total Amount)
    - Line 15: Marketing Commission (Basic, Qty 1, Discount 0, Net Amount, Tax Rate 18%, GST type, Tax Amount, Total Amount)
    - Line 16: Market Place Fee (Basic, Qty 1, Discount 0, Net Amount, Tax Rate 18%, GST type, Tax Amount, Total Amount)
    - Line 17 / Line 7: Partner Logistics / Customer Shipment (Basic, Qty 1, Discount 0, Net Amount, Tax Rate 18%, GST type, Tax Amount, Total Amount)
    - Line 18: TDS (Total Amount)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24
    )
    
    styles = getSampleStyleSheet()
    
    style_logo = ParagraphStyle(
        'HeaderLogo',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=18,
        leading=20,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_title_right = ParagraphStyle(
        'TitleRight',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=11,
        leading=13,
        alignment=2
    )
    style_normal = ParagraphStyle(
        'InvNormal',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=8,
        leading=10.5
    )
    style_bold = ParagraphStyle(
        'InvBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5
    )
    style_normal_right = ParagraphStyle(
        'InvNormalRight',
        parent=style_normal,
        alignment=2
    )
    style_bold_right = ParagraphStyle(
        'InvBoldRight',
        parent=style_bold,
        alignment=2
    )
    style_th_center = ParagraphStyle(
        'TableHeaderCenter',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7,
        leading=8.5,
        alignment=1
    )
    style_th = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7,
        leading=8.5,
        alignment=0
    )
    style_td = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=7.5,
        leading=9.5
    )
    style_td_center = ParagraphStyle(
        'TableCellCenter',
        parent=style_td,
        alignment=1
    )
    style_td_right = ParagraphStyle(
        'TableCellRight',
        parent=style_td,
        alignment=2
    )
    style_section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#1E1B4B')
    )

    story = []

    # 1. HEADER BAR
    header_data = [
        [
            Paragraph("<b>E-COMMERCE PLATFORM OPERATOR</b>", style_logo),
            Paragraph(f"<b>DEALER SETTLEMENT STATEMENT / INVOICE</b><br/><font size='8' face='{FONT_NORMAL}' color='#444'>(Official Tax Statement)</font>", style_title_right)
        ]
    ]
    t_header = Table(header_data, colWidths=[240, 307])
    t_header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.append(t_header)
    story.append(Spacer(1, 4))

    # 2. DEALER & SETTLEMENT META
    dealer_name = getattr(dealer, 'business_name', '') if dealer else 'DEALER'
    dealer_addr = getattr(dealer, 'business_address', '') if dealer else ''
    dealer_city = getattr(dealer, 'city', '') if dealer else ''
    dealer_pin = getattr(dealer, 'pincode', '') if dealer else ''
    pan_no = getattr(dealer, 'pan_number', '') if dealer else 'NOT AVAILABLE'
    gst_no = getattr(dealer, 'gst_number', '') if dealer else 'UNREGISTERED'

    dealer_html = (
        f"<b>Dealer (Payee Details):</b><br/>"
        f"<b>{str(dealer_name).upper()}</b><br/>"
        f"{dealer_addr}<br/>"
        f"{dealer_city}, {dealer_pin}<br/>"
        f"<b>PAN:</b> {pan_no} | <b>GSTIN:</b> {gst_no}"
    )

    stl_num = getattr(settlement, 'settlement_number', '') or f"STL-{getattr(settlement, 'id', '')}"
    
    def _safe_fmt_date(v):
        if not v:
            return datetime.now().strftime('%d.%m.%Y')
        if hasattr(v, 'strftime'):
            return v.strftime('%d.%m.%Y')
        return str(v)[:10]

    stl_dt = _safe_fmt_date(getattr(settlement, 'created_at', None))
    fy_str = getattr(settlement, 'financial_year', '2026-2027')
    p_start = _safe_fmt_date(getattr(settlement, 'period_start', None))
    p_end = _safe_fmt_date(getattr(settlement, 'period_end', None))

    meta_html = (
        f"<b>Settlement Number:</b> {stl_num}<br/>"
        f"<b>Statement Date:</b> {stl_dt}<br/>"
        f"<b>Financial Year:</b> {fy_str}<br/>"
        f"<b>Period Covered:</b> {p_start} to {p_end}"
    )

    t_meta = Table([[Paragraph(dealer_html, style_normal), Paragraph(meta_html, style_normal_right)]], colWidths=[260, 287])
    t_meta.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
    story.append(t_meta)
    story.append(Spacer(1, 6))

    # 3. 11-COLUMN DEALER INVOICE TABLE
    col_widths = [24, 48, 135, 46, 18, 40, 48, 38, 42, 48, 60]
    
    header_row = [
        Paragraph("slno", style_th_center),
        Paragraph("Product ID", style_th_center),
        Paragraph("Description", style_th),
        Paragraph("Unit<br/>price", style_th_center),
        Paragraph("Qty", style_th_center),
        Paragraph("Discount", style_th_center),
        Paragraph("Net<br/>Amount", style_th_center),
        Paragraph("Tax<br/>Rate", style_th_center),
        Paragraph("GST<br/>type", style_th_center),
        Paragraph("Tax<br/>Amount", style_th_center),
        Paragraph("Total<br/>Amount", style_th_center)
    ]

    for item in items:
        order_num = getattr(item, 'order_number', '') or str(getattr(item, 'order_id', ''))
        delivery_type = (getattr(item, 'delivery_type', '') or '').lower()
        is_self_log = getattr(item, 'shipping_received', 0.0) > 0 or 'self' in delivery_type
        
        story.append(Paragraph(f"<b>ORDER #{order_num}</b> — {_safe_fmt_date(getattr(item, 'order_date', None))} ({'DEALER SELF LOGISTICS' if is_self_log else 'PARTNER LOGISTICS'})", style_section_title))
        story.append(Spacer(1, 3))

        table_data = [header_row]

        # Line 14: Net Selling Price
        gross_sale = round_curr(getattr(item, 'gross_sale_amount', 0.0))
        item_qty = getattr(item, 'quantity', 1) or 1
        item_price = round_curr(getattr(item, 'item_price', gross_sale))
        discount_val = 0.0
        net_amt_14 = round_curr(gross_sale / 1.18)
        tax_amt_14 = round_curr(gross_sale - net_amt_14)

        table_data.append([
            Paragraph("14", style_td_center),
            Paragraph(str(getattr(item, 'order_item_id', ''))[:8] or "1020001", style_td_center),
            Paragraph("<b>Net Selling Price / Product</b>", style_td),
            Paragraph(f"₹{net_amt_14:.2f}", style_td_right),
            Paragraph(str(item_qty), style_td_center),
            Paragraph(f"₹{discount_val:.2f}", style_td_right),
            Paragraph(f"₹{net_amt_14:.2f}", style_td_right),
            Paragraph("9%<br/>9%", style_td_center),
            Paragraph("CGST<br/>SGST", style_td_center),
            Paragraph(f"₹{tax_amt_14:.2f}", style_td_right),
            Paragraph(f"₹{gross_sale:.2f}", style_td_right)
        ])

        # Line 15: Marketing
        mkt_fee = round_curr(getattr(item, 'marketing_fee', 0.0))
        mkt_net = round_curr(mkt_fee / 1.18)
        mkt_tax = round_curr(mkt_fee - mkt_net)
        table_data.append([
            Paragraph("15", style_td_center),
            Paragraph("—", style_td_center),
            Paragraph("<b>Marketing Commission</b>", style_td),
            Paragraph(f"₹{mkt_net:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph(f"₹{mkt_net:.2f}", style_td_right),
            Paragraph("9%<br/>9%", style_td_center),
            Paragraph("CGST<br/>SGST", style_td_center),
            Paragraph(f"₹{mkt_tax:.2f}", style_td_right),
            Paragraph(f"−₹{mkt_fee:.2f}", style_td_right)
        ])

        # Line 16: Marketplace
        mp_fee = round_curr(getattr(item, 'marketplace_fee', 0.0))
        mp_net = round_curr(mp_fee / 1.18)
        mp_tax = round_curr(mp_fee - mp_net)
        table_data.append([
            Paragraph("16", style_td_center),
            Paragraph(marketplace_sac, style_td_center),
            Paragraph(f"<b>Market Place Fee (SAC: {marketplace_sac})</b>", style_td),
            Paragraph(f"₹{mp_net:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph(f"₹{mp_net:.2f}", style_td_right),
            Paragraph("9%<br/>9%", style_td_center),
            Paragraph("CGST<br/>SGST", style_td_center),
            Paragraph(f"₹{mp_tax:.2f}", style_td_right),
            Paragraph(f"−₹{mp_fee:.2f}", style_td_right)
        ])

        # Line 17 / Line 7: Logistics
        if is_self_log:
            ship_fee = round_curr(getattr(item, 'shipping_received', 0.0))
            ship_net = round_curr(ship_fee / 1.18)
            ship_tax = round_curr(ship_fee - ship_net)
            table_data.append([
                Paragraph("7", style_td_center),
                Paragraph(logistics_sac, style_td_center),
                Paragraph(f"<b>Customer Shipment (SAC: {logistics_sac})</b>", style_td),
                Paragraph(f"₹{ship_net:.2f}", style_td_right),
                Paragraph("1", style_td_center),
                Paragraph("₹0.00", style_td_right),
                Paragraph(f"₹{ship_net:.2f}", style_td_right),
                Paragraph("9%<br/>9%", style_td_center),
                Paragraph("CGST<br/>SGST", style_td_center),
                Paragraph(f"₹{ship_tax:.2f}", style_td_right),
                Paragraph(f"+₹{ship_fee:.2f}", style_td_right)
            ])
        else:
            log_fee = round_curr(getattr(item, 'logistics_charge', 0.0))
            log_net = round_curr(log_fee / 1.18)
            log_tax = round_curr(log_fee - log_net)
            table_data.append([
                Paragraph("17", style_td_center),
                Paragraph(logistics_sac, style_td_center),
                Paragraph(f"<b>Shipment / Partner Logistics (SAC: {logistics_sac})</b>", style_td),
                Paragraph(f"₹{log_net:.2f}", style_td_right),
                Paragraph("1", style_td_center),
                Paragraph("₹0.00", style_td_right),
                Paragraph(f"₹{log_net:.2f}", style_td_right),
                Paragraph("9%<br/>9%", style_td_center),
                Paragraph("CGST<br/>SGST", style_td_center),
                Paragraph(f"₹{log_tax:.2f}", style_td_right),
                Paragraph(f"−₹{log_fee:.2f}", style_td_right)
            ])

        # Line 18: TDS
        tds_val = round_curr(getattr(item, 'tds_amount', 0.0))
        tds_pct = round_curr(getattr(item, 'tds_rate', 0.001) * 100)
        
        if tds_val > 0:
            tds_desc = f"<b>TDS @ {tds_pct:.1f}%</b>"
            tds_rate_html = f"{tds_pct:.1f}%"
            tds_type_html = "TDS"
            tds_tax_html = f"₹{tds_val:.2f}"
            tds_total_html = f"−₹{tds_val:.2f}"
        else:
            tds_desc = f"<b>TDS @ 0% (NIL - Below Limit)</b>"
            tds_rate_html = "0%"
            tds_type_html = "NIL"
            tds_tax_html = "NIL"
            tds_total_html = "₹0.00"

        table_data.append([
            Paragraph("18", style_td_center),
            Paragraph("—", style_td_center),
            Paragraph(tds_desc, style_td),
            Paragraph("—", style_td_center),
            Paragraph("1", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph(f"₹{gross_sale:.2f}", style_td_right),
            Paragraph(tds_rate_html, style_td_center),
            Paragraph(tds_type_html, style_td_center),
            Paragraph(tds_tax_html, style_td_right),
            Paragraph(tds_total_html, style_td_right)
        ])

        # Final Line Net Payable
        net_line_item = round_curr(getattr(item, 'net_payable', 0.0))
        table_data.append([
            Paragraph("<b>ITEM PAYABLE:</b>", style_bold),
            "", "", "", "", "", "", "", "", "",
            Paragraph(f"<b>₹{net_line_item:.2f}</b>", style_bold_right)
        ])

        t_item = Table(table_data, colWidths=col_widths, repeatRows=1)
        t_item.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
            ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEF2FF')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('SPAN', (0, -1), (9, -1)),
            ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_item)
        story.append(Spacer(1, 8))

    # 4. FINAL GRAND SUMMARY BAR
    tot_payable = round_curr(getattr(settlement, 'net_payable', 0.0))
    summary_html = (
        f"<font size='11' color='#1E1B4B'><b>FINAL DEALER PAYABLE: ₹{tot_payable:.2f}</b></font><br/>"
        f"<font size='7.5' color='#555'>Formulas Applied: Self Logistics (14 - 15 - 16 + 7 - 18) / Partner Logistics (14 - 15 - 16 - 17 - 18)</font>"
    )

    t_grand = Table([[Paragraph(summary_html, style_bold_right)]], colWidths=[547])
    t_grand.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1E1B4B')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_grand)

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_dealer_fee_invoice_pdf(
    order,
    dealer,
    items,
    partner=None,
    marketplace_sac="996111",
    logistics_sac="996812"
):
    """
    Generates Official Platform Service Tax Invoice (Admin to Dealer) for an Order
    following the exact 11-column dual-table pattern:
    slno | Product ID | Description | Unit price | Qty | Discount | Net Amount | Tax Rate | GST type | Tax Amount | Total Amount

    Table 1: Marketplace Fees (SAC 996111)
    Table 2: Shipping Services (SAC 996812)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24
    )

    styles = getSampleStyleSheet()

    style_logo = ParagraphStyle(
        'FeeLogo',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=16,
        leading=18,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_title_center = ParagraphStyle(
        'FeeTitleCenter',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=12,
        leading=14.5,
        alignment=1,
        textColor=colors.HexColor('#1E1B4B')
    )
    style_title_right = ParagraphStyle(
        'FeeTitleRight',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=11,
        leading=13,
        alignment=2
    )
    style_normal = ParagraphStyle(
        'FeeNormal',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=8,
        leading=10.5
    )
    style_bold = ParagraphStyle(
        'FeeBold',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10.5
    )
    style_normal_right = ParagraphStyle(
        'FeeNormalRight',
        parent=style_normal,
        alignment=2
    )
    style_bold_right = ParagraphStyle(
        'FeeBoldRight',
        parent=style_bold,
        alignment=2
    )
    style_th = ParagraphStyle(
        'FeeTh',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=7,
        leading=8.5,
        alignment=0
    )
    style_th_center = ParagraphStyle(
        'FeeThCenter',
        parent=style_th,
        alignment=1
    )
    style_td = ParagraphStyle(
        'FeeTd',
        parent=styles['Normal'],
        fontName=FONT_NORMAL,
        fontSize=7.5,
        leading=9.5
    )
    style_td_center = ParagraphStyle(
        'FeeTdCenter',
        parent=style_td,
        alignment=1
    )
    style_td_right = ParagraphStyle(
        'FeeTdRight',
        parent=style_td,
        alignment=2
    )
    style_table_title = ParagraphStyle(
        'FeeTableTitle',
        parent=styles['Normal'],
        fontName=FONT_BOLD,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#1E1B4B')
    )

    story = []

    # 1. PLATFORM OPERATOR & DEALER METADATA
    p_name = getattr(partner, 'partner_name', None) or "MULTIKART CORP"
    p_addr = getattr(partner, 'address', None) or "123 Fashion Street, Tech Park"
    p_city = getattr(partner, 'city', None) or "Bangalore"
    p_pin = getattr(partner, 'pincode', None) or "560025"
    p_state = getattr(partner, 'state', None) or "KARNATAKA"
    p_gst = getattr(partner, 'tax_id', None) or "GSTIN123456789"
    p_phone = getattr(partner, 'support_phone', None) or "+91-1234567890"
    p_email = getattr(partner, 'support_email', None) or "support@multikart.com"

    d_name = getattr(dealer, 'business_name', '') or "DEALER"
    d_addr = getattr(dealer, 'business_address', '') or ""
    d_city = getattr(dealer, 'city', '') or ""
    d_pin = getattr(dealer, 'pincode', '') or ""
    
    # State resolution (safely access without triggering async lazy loading)
    d_state = ""
    try:
        d_state = getattr(dealer, 'state_name', '') or getattr(dealer, 'state', '') or ''
        if not d_state and 'state_rel' in getattr(dealer, '__dict__', {}):
            state_obj = dealer.__dict__.get('state_rel')
            if state_obj:
                d_state = getattr(state_obj, 'name', '') or ''
    except Exception:
        pass
    if not d_state:
        d_state = "KARNATAKA"
    
    d_gst = getattr(dealer, 'gst_number', '') or "UNREGISTERED"
    d_pan = getattr(dealer, 'pan_number', '') or "NOT AVAILABLE"

    order_num = getattr(order, 'order_number', '') or f"ORD-{getattr(order, 'id', '')}"
    
    def _fmt_dt(val):
        if not val:
            return datetime.now().strftime('%d.%m.%Y')
        if hasattr(val, 'strftime'):
            return val.strftime('%d.%m.%Y')
        return str(val)[:10]

    order_dt = _fmt_dt(getattr(order, 'created_at', None))
    inv_num = f"ADM-INV-{order_num}"
    inv_dt = datetime.now().strftime('%d.%m.%Y')

    # Intra-state vs Inter-state
    is_inter_state = False
    if hasattr(order, 'is_inter_state') and order.is_inter_state is not None:
        is_inter_state = bool(order.is_inter_state)
    else:
        is_inter_state = bool(d_state.strip().upper() != p_state.strip().upper())

    # 1. Top Centered Invoice Title
    t_title = Table([
        [
            Paragraph(f"<b>TAX INVOICE</b><br/><font size='8.5' face='{FONT_NORMAL}' color='#444'>(Platform Commission & Logistics Fee)</font><br/><font size='7' color='#555'>Original for Recipient</font>", style_title_center)
        ]
    ], colWidths=[547])
    t_title.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_title)
    story.append(Spacer(1, 2))

    # 2. Platform Company Details Bar
    t_platform = Table([
        [
            Paragraph(f"<b>{p_name.upper()}</b><br/><font size='7.5' color='#555'>{p_addr}, {p_city}, {p_state} - {p_pin}<br/>GSTIN: <b>{p_gst}</b> | Phone: {p_phone} | Email: {p_email}</font>", style_logo)
        ]
    ], colWidths=[547])
    t_platform.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_platform)
    story.append(Spacer(1, 4))

    # Meta Parties Block
    dealer_box = (
        f"<b>Billed To (Dealer / Recipient):</b><br/>"
        f"<b>{d_name.upper()}</b><br/>"
        f"{d_addr}<br/>"
        f"{d_city} {d_pin} ({d_state})<br/>"
        f"<b>GSTIN:</b> {d_gst} | <b>PAN:</b> {d_pan}"
    )
    inv_box = (
        f"<b>Invoice Number:</b> {inv_num}<br/>"
        f"<b>Invoice Date:</b> {inv_dt}<br/>"
        f"<b>Order Reference:</b> #{order_num}<br/>"
        f"<b>Order Date:</b> {order_dt}<br/>"
        f"<b>Place of Supply:</b> {d_state} ({'INTER-STATE' if is_inter_state else 'INTRA-STATE'})"
    )

    t_meta = Table([[Paragraph(dealer_box, style_normal), Paragraph(inv_box, style_normal_right)]], colWidths=[270, 277])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 8))

    # Compute Fees from Items
    # 1. Marketplace Fee
    mp_basic = sum((getattr(it, 'marketplace_dealer_fee', 0.0) or 0.0) for it in items)
    if mp_basic <= 0:
        mp_basic = float(getattr(order, 'platform_fee_amount', 0.0) or 0.0)
    if mp_basic <= 0:
        mp_basic = 5.00  # standard baseline

    mp_basic = round_curr(mp_basic)

    # 2. Shipping Services Fee
    is_partner_logistics = False
    log_basic = 0.0
    for it in items:
        dt = (getattr(it, 'delivery_type', '') or '').strip().lower()
        if getattr(it, 'logistics_partner_id', None) is not None or dt == 'logistics' or 'partner' in dt:
            is_partner_logistics = True
        log_basic += float(getattr(it, 'logistics_charge_amount', 0.0) or 0.0)

    if log_basic <= 0 and is_partner_logistics:
        log_basic = float(getattr(order, 'delivery_charge', 0.0) or 0.0)
    if log_basic <= 0 and is_partner_logistics:
        log_basic = 10.00  # standard baseline

    log_basic = round_curr(log_basic)

    # 11-column widths (sum = 547pt for A4)
    # slno | Product ID | Description | Unit price | Qty | Discount | Net Amount | Tax Rate | GST type | Tax Amount | Total Amount
    col_widths = [24, 56, 136, 44, 22, 36, 48, 40, 42, 45, 54]

    # Resolve product IDs and names for the order items
    prod_ids = []
    prod_names = []
    for it in items:
        p_id = ""
        if getattr(it, 'product_id', None):
            p_id = str(it.product_id)[:8]
        elif getattr(it, 'product', None) and getattr(it.product, 'id', None):
            p_id = str(it.product.id)[:8]
        
        if p_id and p_id not in prod_ids:
            prod_ids.append(p_id)
            
        p_name_val = ""
        if getattr(it, 'product', None) and getattr(it.product, 'title', None):
            p_name_val = it.product.title
        elif getattr(it, 'product', None) and getattr(it.product, 'name', None):
            p_name_val = it.product.name
        elif getattr(it, 'product_name', None):
            p_name_val = it.product_name
            
        if p_name_val and p_name_val not in prod_names:
            prod_names.append(p_name_val)

    display_prod_id = ", ".join(prod_ids) if prod_ids else (str(getattr(order, 'id', ''))[:8] or "N/A")
    display_prod_name = ", ".join(prod_names) if prod_names else "General Merchandise"

    def _make_table_header():
        return [
            Paragraph("slno", style_th_center),
            Paragraph("Product ID", style_th_center),
            Paragraph("Description", style_th),
            Paragraph("Unit price", style_th_center),
            Paragraph("Qty", style_th_center),
            Paragraph("Discount", style_th_center),
            Paragraph("Net Amount", style_th_center),
            Paragraph("Tax Rate", style_th_center),
            Paragraph("GST type", style_th_center),
            Paragraph("Tax Amount", style_th_center),
            Paragraph("Total Amount", style_th_center)
        ]

    # --- TABLE 1: MARKETPLACE FEES ---
    story.append(Paragraph("<b>1. MARKETPLACE FEES</b>", style_table_title))
    story.append(Spacer(1, 3))

    t1_data = [_make_table_header()]
    mp_desc = f"<b>Marketplace Platform Services</b><br/><font size='7' color='#555'>Product: {display_prod_name}<br/>Order Ref: #{order_num} • SAC: {marketplace_sac}</font>"

    if is_inter_state:
        # 18% IGST
        mp_tax = round_curr(mp_basic * 0.18)
        mp_total = round_curr(mp_basic + mp_tax)
        t1_data.append([
            Paragraph("1", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(mp_desc, style_td),
            Paragraph(f"₹{mp_basic:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("0", style_td_center),
            Paragraph(f"₹{mp_basic:.2f}", style_td_right),
            Paragraph("18%", style_td_center),
            Paragraph("IGST", style_td_center),
            Paragraph(f"₹{mp_tax:.2f}", style_td_right),
            Paragraph(f"₹{mp_total:.2f}", style_td_right)
        ])
    else:
        # 9% CGST + 9% SGST
        mp_cgst = round_curr(mp_basic * 0.09)
        mp_sgst = round_curr(mp_basic * 0.09)
        mp_tax = round_curr(mp_cgst + mp_sgst)
        mp_total = round_curr(mp_basic + mp_tax)

        t1_data.append([
            Paragraph("1", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(mp_desc, style_td),
            Paragraph(f"₹{mp_basic:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("0", style_td_center),
            Paragraph(f"₹{mp_basic:.2f}", style_td_right),
            Paragraph("9%", style_td_center),
            Paragraph("Cgst", style_td_center),
            Paragraph(f"₹{mp_cgst:.2f}", style_td_right),
            Paragraph(f"₹{mp_total:.2f}", style_td_right)
        ])
        t1_data.append([
            "", "", "", "", "", "", "",
            Paragraph("9%", style_td_center),
            Paragraph("Sgst", style_td_center),
            Paragraph(f"₹{mp_sgst:.2f}", style_td_right),
            ""
        ])

    # Table 1 Total Row
    t1_data.append([
        "", "",
        Paragraph("<b>Total</b>", style_bold),
        "", "", "", "", "", "",
        Paragraph(f"<b>₹{mp_tax:.2f}</b>", style_bold_right),
        Paragraph(f"<b>₹{mp_total:.2f}</b>", style_bold_right)
    ])

    t1 = Table(t1_data, colWidths=col_widths)
    t1_style = [
        ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEF2FF')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.HexColor('#1E1B4B')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
    ]
    t1.setStyle(TableStyle(t1_style))
    story.append(t1)
    story.append(Spacer(1, 10))

    # --- TABLE 2: SHIPPING SERVICES ---
    story.append(Paragraph("<b>2. SHIPPING SERVICES</b>", style_table_title))
    story.append(Spacer(1, 3))

    t2_data = [_make_table_header()]
    log_desc = f"<b>Logistics & Shipping Services</b><br/><font size='7' color='#555'>Product: {display_prod_name}<br/>Order Ref: #{order_num} • SAC: {logistics_sac}</font>"

    if log_basic > 0:
        if is_inter_state:
            log_tax = round_curr(log_basic * 0.18)
            log_total = round_curr(log_basic + log_tax)
            t2_data.append([
                Paragraph("2", style_td_center),
                Paragraph(display_prod_id, style_td_center),
                Paragraph(log_desc, style_td),
                Paragraph(f"₹{log_basic:.2f}", style_td_right),
                Paragraph("1", style_td_center),
                Paragraph("0", style_td_center),
                Paragraph(f"₹{log_basic:.2f}", style_td_right),
                Paragraph("18%", style_td_center),
                Paragraph("IGST", style_td_center),
                Paragraph(f"₹{log_tax:.2f}", style_td_right),
                Paragraph(f"₹{log_total:.2f}", style_td_right)
            ])
        else:
            log_cgst = round_curr(log_basic * 0.09)
            log_sgst = round_curr(log_basic * 0.09)
            log_tax = round_curr(log_cgst + log_sgst)
            log_total = round_curr(log_basic + log_tax)
            t2_data.append([
                Paragraph("2", style_td_center),
                Paragraph(display_prod_id, style_td_center),
                Paragraph(log_desc, style_td),
                Paragraph(f"₹{log_basic:.2f}", style_td_right),
                Paragraph("1", style_td_center),
                Paragraph("0", style_td_center),
                Paragraph(f"₹{log_basic:.2f}", style_td_right),
                Paragraph("9%", style_td_center),
                Paragraph("Cgst", style_td_center),
                Paragraph(f"₹{log_cgst:.2f}", style_td_right),
                Paragraph(f"₹{log_total:.2f}", style_td_right)
            ])
            t2_data.append([
                "", "", "", "", "", "", "",
                Paragraph("9%", style_td_center),
                Paragraph("Sgst", style_td_center),
                Paragraph(f"₹{log_sgst:.2f}", style_td_right),
                ""
            ])

        t2_data.append([
            "", "",
            Paragraph("<b>Total</b>", style_bold),
            "", "", "", "", "", "",
            Paragraph(f"<b>₹{log_tax:.2f}</b>", style_bold_right),
            Paragraph(f"<b>₹{log_total:.2f}</b>", style_bold_right)
        ])
    else:
        # Dealer self logistics - No shipping charges billed to dealer
        log_tax = 0.0
        log_total = 0.0
        log_self_desc = f"<b>Shipping Services (Dealer Self Logistics)</b><br/><font size='7' color='#555'>Product: {display_prod_name}<br/>Order Ref: #{order_num} • SAC: {logistics_sac}</font>"
        t2_data.append([
            Paragraph("2", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(log_self_desc, style_td),
            Paragraph("₹0.00", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("0", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph("0%", style_td_center),
            Paragraph("Exempt", style_td_center),
            Paragraph("₹0.00", style_td_right),
            Paragraph("₹0.00", style_td_right)
        ])
        t2_data.append([
            "", "",
            Paragraph("<b>Total</b>", style_bold),
            "", "", "", "", "", "",
            Paragraph("<b>₹0.00</b>", style_bold_right),
            Paragraph("<b>₹0.00</b>", style_bold_right)
        ])

    t2 = Table(t2_data, colWidths=col_widths)
    t2.setStyle(TableStyle(t1_style))
    story.append(t2)
    story.append(Spacer(1, 10))

    # --- TABLE 3: TAX DEDUCTED AT SOURCE (TDS u/s 194-O) ---
    story.append(Paragraph("<b>3. TAX DEDUCTED AT SOURCE (TDS u/s 194-O)</b>", style_table_title))
    story.append(Spacer(1, 3))

    t3_data = [_make_table_header()]
    gross_sales_sum = sum(float(getattr(it, 'price', 0.0) or 0.0) * int(getattr(it, 'quantity', 1) or 1) for it in items)
    tds_sum = sum(float(getattr(it, 'tds_amount', 0.0) or 0.0) for it in items)
    has_pan = bool(getattr(dealer, 'pan_number', None))
    tds_rate_pct = 0.1 if has_pan else 5.0

    if tds_sum > 0:
        tds_desc = f"<b>TDS Withheld u/s 194-O</b><br/><font size='7' color='#555'>Product: {display_prod_name}<br/>PAN: {d_pan} • Section: 194-O ({tds_rate_pct:.1f}% Direct Tax)</font>"
        t3_data.append([
            Paragraph("3", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(tds_desc, style_td),
            Paragraph(f"₹{gross_sales_sum:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("0", style_td_center),
            Paragraph(f"₹{gross_sales_sum:.2f}", style_td_right),
            Paragraph(f"{tds_rate_pct:.1f}%", style_td_center),
            Paragraph("TDS", style_td_center),
            Paragraph(f"₹{tds_sum:.2f}", style_td_right),
            Paragraph(f"−₹{tds_sum:.2f}", style_td_right)
        ])
        t3_data.append([
            "", "",
            Paragraph("<b>Total TDS</b>", style_bold),
            "", "", "", "", "", "",
            Paragraph(f"<b>₹{tds_sum:.2f}</b>", style_bold_right),
            Paragraph(f"<b>−₹{tds_sum:.2f}</b>", style_bold_right)
        ])
    else:
        tds_nil_desc = f"<b>TDS u/s 194-O (NIL - Below Exemption Threshold)</b><br/><font size='7' color='#555'>Product: {display_prod_name}<br/>PAN: {d_pan} • Section: 194-O (Threshold: ₹5,00,000)</font>"
        t3_data.append([
            Paragraph("3", style_td_center),
            Paragraph(display_prod_id, style_td_center),
            Paragraph(tds_nil_desc, style_td),
            Paragraph(f"₹{gross_sales_sum:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph("0", style_td_center),
            Paragraph(f"₹{gross_sales_sum:.2f}", style_td_right),
            Paragraph("0%", style_td_center),
            Paragraph("NIL", style_td_center),
            Paragraph("NIL", style_td_center),
            Paragraph("₹0.00", style_td_right)
        ])
        t3_data.append([
            "", "",
            Paragraph("<b>Total TDS</b>", style_bold),
            "", "", "", "", "", "",
            Paragraph("<b>NIL</b>", style_bold_right),
            Paragraph("<b>₹0.00</b>", style_bold_right)
        ])

    t3 = Table(t3_data, colWidths=col_widths)
    t3.setStyle(TableStyle(t1_style))
    story.append(t3)
    story.append(Spacer(1, 10))

    # --- GRAND SUMMARY CARD ---
    grand_net = round_curr(mp_basic + log_basic)
    grand_tax = round_curr(mp_tax + log_tax)
    grand_total = round_curr(mp_total + log_total)

    words = ""
    try:
        words = num2words(grand_total, lang='en_IN').title() + " Rupees Only"
    except Exception:
        words = f"Rupees {grand_total:.2f} Only"

    tds_summary_line = f"<b>TDS Withheld u/s 194-O:</b> ₹{tds_sum:.2f}<br/>" if tds_sum > 0 else "<b>TDS u/s 194-O:</b> NIL (Under ₹5L Limit)<br/>"

    summary_rows = [
        [
            Paragraph(f"<b>Total Taxable Value (Net Amount):</b> ₹{grand_net:.2f}<br/>"
                      f"<b>Total Tax Amount (GST):</b> ₹{grand_tax:.2f}<br/>"
                      f"<font size='9' color='#1E1B4B'><b>INVOICE TOTAL: ₹{grand_total:.2f}</b></font><br/>"
                      f"{tds_summary_line}"
                      f"<font size='7' color='#555'>Amount in Words: {words}</font><br/>"
                      f"<font size='7' color='#666'>Whether tax is payable on Reverse Charge basis: <b>NO</b></font>", style_normal),
            Paragraph(f"<br/><br/><br/><b>For {p_name.upper()}</b><br/><font size='7' color='#555'>Authorized Signatory</font>", style_normal_right)
        ]
    ]
    t_summary = Table(summary_rows, colWidths=[360, 187])
    t_summary.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#1E1B4B')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_summary)

    doc.build(story)
    buffer.seek(0)
    return buffer

