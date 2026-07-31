import io
import os
from datetime import datetime
from num2words import num2words
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether, PageBreak
)

def generate_invoice_pdf(invoice, dealer, order, order_items, billing_address, shipping_address):
    buffer = io.BytesIO()
    # A4 dimensions: 595.27 x 841.89 pt. Left & right margin = 28 pt -> Available width = 539 pt
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=28
    )
    
    styles = getSampleStyleSheet()
    
    # Custom Paragraph Styles matching Amazon Invoice report typography
    style_logo = ParagraphStyle(
        'AmazonLogo',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=26,
        textColor=colors.black
    )
    style_title_right = ParagraphStyle(
        'TitleRight',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=15,
        alignment=2 # Right
    )
    style_normal = ParagraphStyle(
        'InvNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11
    )
    style_bold = ParagraphStyle(
        'InvBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11
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
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
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
        fontName='Helvetica',
        fontSize=8,
        leading=10
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

    # ==========================================
    # PAGE 1: SELLER PRODUCT INVOICE
    # ==========================================
    dealer_brand = getattr(dealer, 'business_name', None) if dealer else None
    logo_text = str(dealer_brand).upper() if dealer_brand else "ONLINE SHOP"
    
    header_data = [
        [
            Paragraph(logo_text, style_logo),
            Paragraph("Tax Invoice/Bill of Supply/Cash Memo<br/><font size='10' face='Helvetica'>(Original for Recipient)</font>", style_title_right)
        ]
    ]
    t_header = Table(header_data, colWidths=[240, 299])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 6))

    # Addresses Block (Sold By left | Billing & Shipping right)
    dealer_name = getattr(dealer, 'business_name', '') if dealer else 'SELLER'
    dealer_addr = getattr(dealer, 'business_address', '') if dealer else ''
    dealer_city = getattr(dealer, 'city', '') if dealer else ''
    dealer_state_name = dealer.state_rel.name if (dealer and getattr(dealer, 'state_rel', None)) else ''
    dealer_state_code = dealer.state_rel.state_code if (dealer and getattr(dealer, 'state_rel', None) and hasattr(dealer.state_rel, 'state_code')) else '29'
    dealer_pin = getattr(dealer, 'pincode', '') if dealer else ''
    pan_no = getattr(dealer, 'pan_number', '') if dealer else ''
    gst_no = getattr(dealer, 'gst_number', '') if dealer else ''
    cin_no = getattr(dealer, 'cin_number', '') if dealer else ''

    sold_by_html = (
        f"<b>Sold By :</b><br/>"
        f"<b>{str(dealer_name).upper()}</b><br/>"
        f"{dealer_addr}<br/>"
        f"{dealer_city}, {dealer_state_name}, {dealer_pin}<br/>"
        f"IN<br/><br/>"
        f"<b>PAN No:</b> {pan_no}<br/>"
        f"<b>GST Registration No:</b> {gst_no}"
    )
    if cin_no:
        sold_by_html += f"<br/><b>CIN No:</b> {cin_no}"

    # Billing Address
    b_name = billing_address.full_name if billing_address else (shipping_address.full_name if shipping_address else 'Recipient')
    b_addr1 = getattr(billing_address, 'address_line1', '') if billing_address else ''
    b_addr2 = getattr(billing_address, 'address_line2', '') if billing_address else ''
    b_city = getattr(billing_address, 'city', '') if billing_address else ''
    b_pin = getattr(billing_address, 'pincode', '') if billing_address else ''
    b_state_name = billing_address.state_rel.name if (billing_address and getattr(billing_address, 'state_rel', None)) else dealer_state_name
    b_state_code = billing_address.state_rel.state_code if (billing_address and getattr(billing_address, 'state_rel', None) and hasattr(billing_address.state_rel, 'state_code')) else dealer_state_code

    b_lines = [b_addr1, b_addr2, f"{b_city or ''}, {b_state_name or ''}, {b_pin or ''}", "IN"]
    b_html = f"<b>Billing Address :</b><br/>{b_name}<br/>" + "<br/>".join([str(l).strip() for l in b_lines if l and str(l).strip()])
    b_html += f"<br/><b>State/UT Code:</b> {b_state_code}"

    # Shipping Address
    s_name = shipping_address.full_name if shipping_address else b_name
    s_addr1 = getattr(shipping_address, 'address_line1', '') if shipping_address else b_addr1
    s_addr2 = getattr(shipping_address, 'address_line2', '') if shipping_address else b_addr2
    s_city = getattr(shipping_address, 'city', '') if shipping_address else b_city
    s_pin = getattr(shipping_address, 'pincode', '') if shipping_address else b_pin
    s_state_name = shipping_address.state_rel.name if (shipping_address and getattr(shipping_address, 'state_rel', None)) else b_state_name
    s_state_code = shipping_address.state_rel.state_code if (shipping_address and getattr(shipping_address, 'state_rel', None) and hasattr(shipping_address.state_rel, 'state_code')) else b_state_code

    s_lines = [s_addr1, s_addr2, f"{s_city or ''}, {s_state_name or ''}, {s_pin or ''}", "IN"]
    s_html = f"<b>Shipping Address :</b><br/>{s_name}<br/>" + "<br/>".join([str(l).strip() for l in s_lines if l and str(l).strip()])
    s_html += (
        f"<br/><b>State/UT Code:</b> {s_state_code}<br/>"
        f"<b>Place of supply:</b> {s_state_name.upper() if s_state_name else 'KARNATAKA'}<br/>"
        f"<b>Place of delivery:</b> {s_state_name.upper() if s_state_name else 'KARNATAKA'}"
    )

    right_col_html = f"{b_html}<br/><br/>{s_html}"

    addr_data = [
        [
            Paragraph(sold_by_html, style_normal),
            Paragraph(right_col_html, style_normal_right)
        ]
    ]
    t_addr = Table(addr_data, colWidths=[260, 279])
    t_addr.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_addr)
    story.append(Spacer(1, 6))

    # Order & Invoice Meta Bar
    order_num = getattr(order, 'order_number', '') or str(getattr(order, 'id', ''))
    order_dt = order.created_at.strftime('%d.%m.%Y') if getattr(order, 'created_at', None) else datetime.now().strftime('%d.%m.%Y')
    inv_num = getattr(invoice, 'invoice_number', '')
    inv_dt = invoice.invoice_date.strftime('%d.%m.%Y') if getattr(invoice, 'invoice_date', None) else datetime.now().strftime('%d.%m.%Y')
    inv_details = f"KA-{inv_num}-{order_num[-4:] if len(order_num)>=4 else order_num}"

    meta_left = f"<b>Order Number:</b> {order_num}<br/><b>Order Date:</b> {order_dt}"
    meta_right = (
        f"<b>Invoice Number :</b> {inv_num}<br/>"
        f"<b>Invoice Details :</b> {inv_details}<br/>"
        f"<b>Invoice Date :</b> {inv_dt}"
    )

    t_meta = Table([
        [
            Paragraph(meta_left, style_normal),
            Paragraph(meta_right, style_normal_right)
        ]
    ], colWidths=[260, 279])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 4))

    # Product Items Table matching exact Amazon layout
    col_widths = [24, 185, 52, 24, 56, 36, 36, 54, 72]
    table_data = [
        [
            Paragraph("Sl.<br/>No", style_th_center),
            Paragraph("Description", style_th),
            Paragraph("Unit<br/>Price", style_th_center),
            Paragraph("Qty", style_th_center),
            Paragraph("Net<br/>Amount", style_th_center),
            Paragraph("Tax<br/>Rate", style_th_center),
            Paragraph("Tax<br/>Type", style_th_center),
            Paragraph("Tax<br/>Amount", style_th_center),
            Paragraph("Total<br/>Amount", style_th_center)
        ]
    ]

    total_tax = 0.0
    total_net = 0.0
    total_gross = 0.0

    for idx, item in enumerate(order_items):
        desc_name = item.product.name if getattr(item, 'product', None) else "Product Item"
        hsn = getattr(item, 'hsn_code', '') or getattr(item.product, 'hsn_code', '') if getattr(item, 'product', None) else ''
        desc_html = f"<b>{desc_name}</b>"
        if hsn:
            desc_html += f"<br/><font color='#444444'>HSN:{hsn}</font>"

        # Tax calculations
        cgst_rate = getattr(item, 'cgst_rate', 0) or 0
        sgst_rate = getattr(item, 'sgst_rate', 0) or 0
        igst_rate = getattr(item, 'igst_rate', 0) or 0
        cgst_amt = getattr(item, 'cgst_amount', 0.0) or 0.0
        sgst_amt = getattr(item, 'sgst_amount', 0.0) or 0.0
        igst_amt = getattr(item, 'igst_amount', 0.0) or 0.0

        item_qty = getattr(item, 'quantity', 1) or 1
        item_price = getattr(item, 'price', 0.0) or 0.0
        item_total = item_price * item_qty

        if cgst_rate > 0 or sgst_rate > 0:
            total_rate = cgst_rate + sgst_rate
        elif igst_rate > 0:
            total_rate = igst_rate
        else:
            total_rate = 0
        unit_price_excl = item_price / (1 + (total_rate / 100)) if total_rate else item_price
        net_amt = unit_price_excl * item_qty
        item_tax_amt = cgst_amt + sgst_amt + igst_amt
        if not item_tax_amt and total_rate:
            item_tax_amt = item_total - net_amt

        if cgst_rate > 0 or sgst_rate > 0:
            tax_rates_html = f"{cgst_rate:.0f}%<br/>{sgst_rate:.0f}%"
            tax_types_html = "CGST<br/>SGST"
            tax_amts_html = f"₹{cgst_amt:.2f}<br/>₹{sgst_amt:.2f}"
        elif igst_rate > 0:
            tax_rates_html = f"{igst_rate:.0f}%"
            tax_types_html = "IGST"
            tax_amts_html = f"₹{igst_amt:.2f}"
        else:
            tax_rates_html = "0%"
            tax_types_html = "GST"
            tax_amts_html = "₹0.00"

        row = [
            Paragraph(str(idx + 1), style_td_center),
            Paragraph(desc_html, style_td),
            Paragraph(f"₹{unit_price_excl:.2f}", style_td_right),
            Paragraph(str(item_qty), style_td_center),
            Paragraph(f"₹{net_amt:.2f}", style_td_right),
            Paragraph(tax_rates_html, style_td_center),
            Paragraph(tax_types_html, style_td_center),
            Paragraph(tax_amts_html, style_td_right),
            Paragraph(f"₹{item_total:.2f}", style_td_right)
        ]
        table_data.append(row)

        total_net += net_amt
        total_tax += item_tax_amt
        total_gross += item_total

    if getattr(invoice, 'total_amount', 0.0) > 0:
        total_gross = invoice.total_amount

    # TOTAL row
    total_row = [
        Paragraph("<b>TOTAL:</b>", style_bold),
        "", "", "", "", "", "",
        Paragraph(f"<b>₹{total_tax:.2f}</b>", style_bold_right),
        Paragraph(f"<b>₹{total_gross:.2f}</b>", style_bold_right)
    ]
    table_data.append(total_row)

    t_items = Table(table_data, colWidths=col_widths, repeatRows=1)
    t_items.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F4F4F4')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (6, -1)),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_items)

    # Amount in Words & Signature Box (Bordered Box below table)
    try:
        amt_words = num2words(total_gross, lang='en_IN').capitalize() + " only"
    except Exception:
        amt_words = f"Rupees {total_gross:.2f} only"

    sig_url = getattr(dealer, 'signature_image_url', None) if dealer else None
    sig_cell_elements = [
        Paragraph(f"<b>For {str(dealer_name).upper()}:</b>", style_bold_right),
        Spacer(1, 15)
    ]
    if sig_url and os.path.exists(sig_url):
        try:
            sig_cell_elements.append(Image(sig_url, width=1.2*inch, height=0.45*inch))
        except Exception:
            sig_cell_elements.append(Spacer(1, 10))
    else:
        sig_cell_elements.append(Spacer(1, 15))
    sig_cell_elements.append(Paragraph("<b>Authorized Signatory</b>", style_bold_right))

    box_left = [
        Paragraph("<b>Amount in Words:</b>", style_bold),
        Paragraph(f"<b>{amt_words}</b>", style_bold)
    ]

    t_sigbox = Table([[box_left, sig_cell_elements]], colWidths=[280, 259])
    t_sigbox.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (0, 0), 6),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 6),
    ]))
    story.append(t_sigbox)
    story.append(Spacer(1, 4))

    # Reverse charge note
    story.append(Paragraph("Whether tax is payable under reverse charge - No", style_normal))
    story.append(Spacer(1, 12))

    # Payment Transaction Bar
    pay_method = getattr(order, 'payment_method', 'Credit Card') or 'Credit Card'
    tx_id = getattr(order, 'tracking_number', '') or f"TXN{order_num}"
    tx_time = order.created_at.strftime('%d/%m/%Y, %H:%M:%S hrs') if getattr(order, 'created_at', None) else datetime.now().strftime('%d/%m/%Y, %H:%M:%S hrs')

    bar_data = [
        [
            Paragraph(f"<b>Payment Transaction ID:</b> {tx_id}", style_td),
            Paragraph(f"<b>Date & Time:</b> {tx_time}", style_td),
            Paragraph(f"<b>Invoice Value:</b> {total_gross:.2f}", style_td),
            Paragraph(f"<b>Mode of Payment:</b> {pay_method}", style_td)
        ]
    ]
    t_bar = Table(bar_data, colWidths=[150, 150, 110, 129])
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
    story.append(Spacer(1, 15))

    footer_p1 = (
        "Customers desirous of availing input GST credit are requested to provide their GSTIN details at checkout<br/>"
        "Please note that this invoice is not a demand for payment"
    )
    story.append(Paragraph(footer_p1, style_footer_small))


    # ==========================================
    # PAGE 2: MARKETPLACE / PLATFORM SERVICES INVOICE
    # ==========================================
    story.append(PageBreak())

    # Page 2 Header
    story.append(t_header)
    story.append(Spacer(1, 6))

    # Page 2 Sold By: Platform Marketplace Services
    p2_sold_by_html = (
        f"<b>Sold By :</b><br/>"
        f"<b>Online Shop Marketplace Services Private Limited</b><br/>"
        f"Brigade Tech Park, Whitefield Main Road<br/>"
        f"Bangalore, Karnataka – 560066<br/>"
        f"IN<br/><br/>"
        f"<b>PAN No:</b> AAICA3918J<br/>"
        f"<b>GST Registration No:</b> 29AAICA3918J1ZE<br/>"
        f"<b>CIN No:</b> U51900KA2010PTC053234"
    )

    t_addr_p2 = Table([
        [
            Paragraph(p2_sold_by_html, style_normal),
            Paragraph(right_col_html, style_normal_right)
        ]
    ], colWidths=[260, 279])
    t_addr_p2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_addr_p2)
    story.append(Spacer(1, 6))

    # Page 2 Meta Bar (Marketplace Invoice Number)
    mkt_inv_num = f"MKT-{order_num[-6:] if len(order_num)>=6 else order_num}"
    p2_meta_right = (
        f"<b>Invoice Number :</b> {mkt_inv_num}<br/>"
        f"<b>Invoice Details :</b> KA-BLR7-1044-{order_num[-4:] if len(order_num)>=4 else '2526'}<br/>"
        f"<b>Invoice Date :</b> {inv_dt}"
    )

    t_meta_p2 = Table([
        [
            Paragraph(meta_left, style_normal),
            Paragraph(p2_meta_right, style_normal_right)
        ]
    ], colWidths=[260, 279])
    t_meta_p2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_meta_p2)
    story.append(Spacer(1, 4))

    # Calculate Marketplace fee amount (Platform fee as Marketplace fees)
    plat_fee = getattr(order, 'platform_fee_amount', 0.0) or 0.0
    del_charge = getattr(order, 'delivery_charge', 0.0) or 0.0
    mkt_total = plat_fee if plat_fee > 0 else (del_charge if del_charge > 0 else 3.00)

    # 18% GST (9% CGST + 9% SGST)
    mkt_net = mkt_total / 1.18
    mkt_cgst = mkt_net * 0.09
    mkt_sgst = mkt_net * 0.09
    mkt_total_tax = mkt_cgst + mkt_sgst

    p2_table_data = [
        [
            Paragraph("Sl.<br/>No", style_th_center),
            Paragraph("Description", style_th),
            Paragraph("Unit<br/>Price", style_th_center),
            Paragraph("Qty", style_th_center),
            Paragraph("Net<br/>Amount", style_th_center),
            Paragraph("Tax<br/>Rate", style_th_center),
            Paragraph("Tax<br/>Type", style_th_center),
            Paragraph("Tax<br/>Amount", style_th_center),
            Paragraph("Total<br/>Amount", style_th_center)
        ],
        [
            Paragraph("1", style_td_center),
            Paragraph("<b>Marketplace Fees</b>", style_td),
            Paragraph(f"₹{mkt_net:.2f}", style_td_right),
            Paragraph("1", style_td_center),
            Paragraph(f"₹{mkt_net:.2f}", style_td_right),
            Paragraph("9%<br/>9%", style_td_center),
            Paragraph("CGST<br/>SGST", style_td_center),
            Paragraph(f"₹{mkt_cgst:.2f}<br/>₹{mkt_sgst:.2f}", style_td_right),
            Paragraph(f"₹{mkt_total:.2f}", style_td_right)
        ],
        [
            Paragraph("<b>TOTAL:</b>", style_bold),
            "", "", "", "", "", "",
            Paragraph(f"<b>₹{mkt_total_tax:.2f}</b>", style_bold_right),
            Paragraph(f"<b>₹{mkt_total:.2f}</b>", style_bold_right)
        ]
    ]

    t_mkt_items = Table(p2_table_data, colWidths=col_widths, repeatRows=1)
    t_mkt_items.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('INNERGRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CCCCCC')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F4F4F4')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('SPAN', (0, -1), (6, -1)),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_mkt_items)

    # Page 2 Amount in Words & Authorized Signatory Box
    try:
        p2_words = num2words(mkt_total, lang='en_IN').capitalize() + " only"
    except Exception:
        p2_words = f"Rupees {mkt_total:.2f} only"

    p2_sig_cell = [
        Paragraph("<b>For Online Shop Marketplace Services Private Limited:</b>", style_bold_right),
        Spacer(1, 25),
        Paragraph("<b>Authorized Signatory</b>", style_bold_right)
    ]

    p2_box_left = [
        Paragraph("<b>Amount in Words:</b>", style_bold),
        Paragraph(f"<b>{p2_words}</b>", style_bold),
        Spacer(1, 10),
        Paragraph("<font color='#666666' size='7'>(1) Service Accounting Code: 998319</font>", style_normal)
    ]

    t_sigbox_p2 = Table([[p2_box_left, p2_sig_cell]], colWidths=[280, 259])
    t_sigbox_p2.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (0, 0), 6),
        ('RIGHTPADDING', (-1, -1), (-1, -1), 6),
    ]))
    story.append(t_sigbox_p2)
    story.append(Spacer(1, 4))

    # Reverse charge note Page 2
    story.append(Paragraph("Whether tax is payable under reverse charge - No", style_normal))
    story.append(Spacer(1, 12))

    # Page 2 Payment Transaction Bar
    p2_bar_data = [
        [
            Paragraph(f"<b>Payment Transaction ID:</b> {tx_id}", style_td),
            Paragraph(f"<b>Date & Time:</b> {tx_time}", style_td),
            Paragraph(f"<b>Invoice Value:</b> {mkt_total:.2f}", style_td),
            Paragraph(f"<b>Mode of Payment:</b> {pay_method}", style_td)
        ]
    ]
    t_bar_p2 = Table(p2_bar_data, colWidths=[150, 150, 110, 129])
    t_bar_p2.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.75, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_bar_p2)
    story.append(Spacer(1, 15))

    footer_p2 = (
        "Please note that this invoice is not a demand for payment<br/>"
        "Regd Office: Online Shop Marketplace Services Private Limited<br/>"
        "Brigade Tech Park, Whitefield Main Road, Bangalore, Karnataka – 560066<br/>"
        "Email: support@onlineshop.com"
    )
    story.append(Paragraph(footer_p2, style_footer_small))

    doc.build(story)
    buffer.seek(0)
    return buffer
