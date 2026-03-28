"""
PDF generation service for buyer estimates
"""
import os
from datetime import datetime
from typing import Dict, List, Any
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

# Logo path
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'BLF-Logo.png')

def add_page_footer(canvas, doc):
    """Add footer with page numbers and continuation notice"""
    canvas.saveState()
    page_num = canvas.getPageNumber()
    total_pages = getattr(doc, 'total_pages', 0)
    
    # Add company footer
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(colors.grey)
    footer_line1 = "Blue Lotus Foods LLC | 2552 W Walton St. | Chicago | Illinois | 60622 | U.S.A"
    footer_line2 = "sales@thebluelotusfoods.com | P: +1 312 684 5912"
    
    # Center the footer text
    canvas.drawCentredString(4.25*inch, 0.5*inch, footer_line1)
    canvas.drawCentredString(4.25*inch, 0.35*inch, footer_line2)
    
    # Add page number on the left
    text = f"Page {page_num}"
    canvas.setFont('Helvetica', 9)
    canvas.drawString(0.5*inch, 0.3*inch, text)
    
    # Add "Continued on next page →" if not the last page
    if total_pages > 0 and page_num < total_pages:
        canvas.setFont('Helvetica-Bold', 10)
        canvas.setFillColor(colors.HexColor('#0A3D5C'))
        canvas.drawRightString(7.5*inch, 0.3*inch, "Continued on next page →")
    
    canvas.restoreState()

def format_currency(value) -> str:
    """Format a value as currency"""
    if value is None:
        return "$0.00"
    if isinstance(value, Decimal):
        value = float(value)
    return f"${value:,.2f}"

def format_date(date_str) -> str:
    """Format a date string"""
    if not date_str:
        return "N/A"
    try:
        if isinstance(date_str, str):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = date_str
        return dt.strftime("%B %d, %Y")
    except:
        return str(date_str)

def group_items_by_fish_cut_grade_port(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by fish species, cut, grade, size, and port"""
    grouped = {}
    for item in items:
        fish_size = item.get('fish_size') or 'no-size'
        key = f"{item['fish_species_id']}-{item['cut_id']}-{item['grade_id']}-{fish_size}-{item['port_code']}"
        if key not in grouped:
            grouped[key] = {
                'common_name': item['common_name'],
                'scientific_name': item.get('scientific_name', ''),
                'cut_name': item['cut_name'],
                'grade_name': item['grade_name'],
                'fish_size': item.get('fish_size'),
                'port_code': item['port_code'],
                'items': []
            }
        grouped[key]['items'].append(item)
    return grouped

def format_fish_size(size: str) -> str:
    """Format fish size with lbs+ suffix"""
    if not size:
        return ''
    # If size has a range (contains "-"), add "lbs+" to both numbers
    if '-' in size:
        parts = size.split('-')
        return f"{parts[0]}lbs+ - {parts[1]}lbs+"
    # If size already has a plus, replace it with "lbs+"
    elif '+' in size:
        return f"{size.replace('+', '')}lbs+"
    # Otherwise just add "lbs+"
    else:
        return f"{size}lbs+"

def generate_estimate_pdf(estimate_data: Dict[str, Any], items: List[Dict[str, Any]]) -> bytes:
    """
    Generate a PDF for a buyer estimate using ReportLab
    
    Args:
        estimate_data: Estimate details (estimate_number, company_name, buyer_names, etc.)
        items: List of estimate items with pricing details
    
    Returns:
        bytes: PDF content as bytes
    """
    import io
    
    # Create PDF document in memory
    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter,
                         rightMargin=0.5*inch, leftMargin=0.5*inch,
                         topMargin=0.5*inch, bottomMargin=0.9*inch)
    
    # Create frame and page template
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template = PageTemplate(id='main', frames=frame, onPage=add_page_footer)
    doc.addPageTemplates([template])
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Create header banner with logo, company name, and title
    if os.path.exists(LOGO_PATH):
        # Create a table for the header banner
        logo_img = Image(LOGO_PATH, width=0.8*inch, height=0.8*inch)
        
        header_data = [[
            logo_img,
            Paragraph("<b>Blue Lotus Foods LLC</b>", ParagraphStyle(
                'BannerCenter',
                fontSize=18,
                textColor=colors.white,
                alignment=TA_CENTER,
            )),
            Paragraph("<b>Product Pricing</b>", ParagraphStyle(
                'BannerRight',
                fontSize=14,
                textColor=colors.white,
                alignment=TA_RIGHT,
            ))
        ]]
        
        header_table = Table(header_data, colWidths=[1.5*inch, 4*inch, 2*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0A3D5C')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
            ('RIGHTPADDING', (-1, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 0.15*inch))
    
    # Define styles
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.white,
        backColor=colors.HexColor('#0A3D5C'),
        spaceAfter=6,
        spaceBefore=12,
    )
    
    # Add estimate information
    info_data = [
        ['Estimate #:', estimate_data.get('estimate_number', 'N/A'), 'Date:', format_date(estimate_data.get('estimate_date'))],
        ['Company:', estimate_data.get('company_name', 'N/A'), 'Delivery:', f"{format_date(estimate_data.get('delivery_date_from'))} - {format_date(estimate_data.get('delivery_date_to'))}"],
        ['Buyers:', estimate_data.get('buyer_names', 'N/A'), '', ''],
    ]
    
    info_table = Table(info_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0A3D5C')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#0A3D5C')),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # Add introductory text
    intro_style = ParagraphStyle(
        'IntroText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        spaceAfter=4,
        alignment=TA_LEFT,
        leading=14,
    )
    
    intro_text = """We are delighted to furnish you with the pricing information and pertinent details for the product 
    mentioned below. We kindly request your prompt confirmation of the order today, enabling us to 
    arrange delivery on the specified date mentioned above."""
    
    note_style = ParagraphStyle(
        'NoteText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#4a5568'),
        spaceAfter=8,
        alignment=TA_LEFT,
        leading=12,
    )
    
    note_text = """<b>Note:</b> The prices provided are estimates only. Tariff and clearing charges may vary depending on the 
    catch, and freight charges are subject to change based on route and market demand."""
    
    elements.append(Paragraph(intro_text, intro_style))
    elements.append(Spacer(1, 0.05*inch))
    elements.append(Paragraph(note_text, note_style))
    elements.append(Spacer(1, 0.15*inch))
    
    # Group items
    grouped_items = group_items_by_fish_cut_grade_port(items)
    
    # Add grouped items tables
    for group_key, group_data in sorted(grouped_items.items()):
        # Create info table with fish details
        fish_info_data = [
            ['Common Name:', group_data['common_name'], 'Scientific Name:', group_data.get('scientific_name', 'N/A'), 'Port:', group_data['port_code']],
            ['Grade/Cut:', f"{group_data['grade_name']} / {group_data['cut_name']}", 'Size:', format_fish_size(group_data.get('fish_size')) if group_data.get('fish_size') else 'N/A', '', '']
        ]
        
        fish_info_table = Table(fish_info_data, colWidths=[1.2*inch, 1.8*inch, 1.3*inch, 1.8*inch, 0.7*inch, 0.7*inch])
        fish_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0A3D5C')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('FONTNAME', (4, 0), (4, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(fish_info_table)
        elements.append(Spacer(1, 0.1*inch))
        
        # Remove the separate port text since it's now in the table
        
        # Table header
        table_data = [
            ['Weight (LBS)', 'Fish Price (incl. Tariff)', 'Freight', 'Clearing', 'Total Price']
        ]
        
        # Add items
        for item in group_data['items']:
            # Calculate fish price including tariff (hide margin from buyer)
            fish_price = float(item.get('fish_price', 0))
            margin = float(item.get('margin', 0))
            tariff_percent = float(item.get('tariff_percent', 0))
            
            markup_fish_price = fish_price + margin
            tariff_amount = (markup_fish_price * tariff_percent) / 100
            fish_price_with_tariff = markup_fish_price + tariff_amount
            
            table_data.append([
                f"{item.get('offer_quantity', 0):,.0f}",
                format_currency(fish_price_with_tariff),
                format_currency(item.get('freight_price', 0)),
                format_currency(item.get('clearing_charges', 0)),
                format_currency(item.get('total_price', 0))
            ])
        
        # Create table
        item_table = Table(table_data, colWidths=[1.5*inch, 1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch])
        item_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ]))
        elements.append(item_table)
        elements.append(Spacer(1, 0.15*inch))
    
    # Build PDF twice: first to get page count, second to add continuation markers
    # First build to get total pages
    doc.build(elements)
    
    # Get PDF bytes from buffer
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

def get_pdf_filename(estimate_number: str) -> str:
    """
    Get the PDF filename for an estimate
    
    Args:
        estimate_number: The estimate number
    
    Returns:
        str: The PDF filename
    """
    date_str = datetime.now().strftime('%Y-%m-%d')
    return f"{date_str}-BLF-Pricing-{estimate_number}.pdf"


def generate_vendor_quote_pdf(quote_data: dict) -> bytes:
    """
    Generate PDF for vendor quote confirmation
    
    Args:
        quote_data: Dictionary containing vendor quote details
        
    Returns:
        bytes: PDF content as bytes
    """
    import io
    from reportlab.platypus import PageBreak
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.5*inch, bottomMargin=0.9*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Header with logo
    if os.path.exists(LOGO_PATH):
        logo_img = Image(LOGO_PATH, width=0.8*inch, height=0.8*inch)
        header_data = [[
            logo_img,
            Paragraph("<b>Blue Lotus Foods LLC</b>", ParagraphStyle(
                'BannerCenter',
                fontSize=18,
                textColor=colors.white,
                alignment=TA_CENTER,
            )),
            Paragraph("<b>Quote Confirmation</b>", ParagraphStyle(
                'BannerRight',
                fontSize=14,
                textColor=colors.white,
                alignment=TA_RIGHT,
            ))
        ]]
        
        header_table = Table(header_data, colWidths=[1.5*inch, 4*inch, 2*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0A3D5C')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
            ('RIGHTPADDING', (-1, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 0.15*inch))
    
    # Quote Information
    info_data = [
        ['Quote ID:', str(quote_data['quote_id']), 'Vendor:', quote_data['vendor_name']],
        ['Fish Type:', quote_data['fish_type'], 'Country:', quote_data['country_of_origin']],
        ['Valid Until:', format_date(quote_data['quote_valid_till']), 'Vendor Code:', quote_data['vendor_code']],
    ]
    
    info_table = Table(info_data, colWidths=[1*inch, 2.5*inch, 1*inch, 2.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0A3D5C')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#0A3D5C')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Destinations
    if quote_data.get('destinations'):
        elements.append(Paragraph("<b>DESTINATIONS & LOGISTICS</b>", ParagraphStyle(
            'SectionHeader',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#0A3D5C'),
            spaceBefore=6,
            spaceAfter=6,
        )))
        
        dest_header = ['Destination', 'Airfreight/Kg', 'Arrival Date', 'Min Weight (kg)', 'Max Weight (kg)']
        dest_data = [dest_header]
        
        for dest in quote_data['destinations']:
            dest_data.append([
                dest['destination'],
                f"${dest['airfreight_per_kg']}",
                dest['arrival_date'],
                str(dest['min_weight']),
                str(dest['max_weight'])
            ])
        
        dest_table = Table(dest_data, colWidths=[2.2*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch], repeatRows=1)
        dest_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A3D5C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        elements.append(dest_table)
        elements.append(Spacer(1, 0.2*inch))
    
    # Products
    if quote_data.get('sizes'):
        elements.append(Paragraph("<b>PRODUCTS & PRICING</b>", ParagraphStyle(
            'SectionHeader',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#0A3D5C'),
            spaceBefore=6,
            spaceAfter=6,
        )))
        
        # Use Paragraph style for wrapping cells
        cell_style = ParagraphStyle('CellWrap', fontSize=9, leading=11)
        cell_style_center = ParagraphStyle('CellWrapCenter', fontSize=9, leading=11, alignment=TA_CENTER)
        
        prod_header = ['Fish Type', 'Cut', 'Grade', 'Weight Range', 'Price/Kg', 'Quantity']
        prod_data = [prod_header]
        
        for size in quote_data['sizes']:
            prod_data.append([
                Paragraph(str(size['fish_type']), cell_style),
                Paragraph(str(size['cut_name']), cell_style_center),
                Paragraph(str(size['grade_name']), cell_style_center),
                Paragraph(str(size['weight_range']), cell_style_center),
                Paragraph(f"${size['price_per_kg']}", cell_style_center),
                Paragraph(str(size['quantity']), cell_style_center)
            ])
        
        prod_table = Table(prod_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch, 1*inch], repeatRows=1)
        prod_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A3D5C')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
        ]))
        elements.append(prod_table)
    
    # ── QUOTE SUMMARY (per-destination pricing breakdown) ──
    destinations = quote_data.get('destinations', [])
    sizes = quote_data.get('sizes', [])
    
    if destinations and sizes:
        elements.append(Spacer(1, 0.25*inch))
        elements.append(Paragraph("<b>QUOTE SUMMARY</b>", ParagraphStyle(
            'SummaryHeader',
            fontSize=12,
            textColor=colors.white,
            backColor=colors.HexColor('#0A3D5C'),
            spaceBefore=6,
            spaceAfter=6,
        )))
        
        cell_normal = ParagraphStyle('SumCellNormal', fontSize=9, leading=11)
        cell_center = ParagraphStyle('SumCellCenter', fontSize=9, leading=11, alignment=TA_CENTER)
        cell_right = ParagraphStyle('SumCellRight', fontSize=9, leading=11, alignment=TA_RIGHT)
        cell_right_bold = ParagraphStyle('SumCellRightBold', fontSize=9, leading=11, alignment=TA_RIGHT, fontName='Helvetica-Bold', textColor=colors.HexColor('#1e40af'))
        
        for dest in destinations:
            dest_name = dest.get('destination', '')
            airfreight = float(dest.get('airfreight_per_kg', 0))
            arrival = dest.get('arrival_date', '')
            min_wt = dest.get('min_weight', '')
            max_wt = dest.get('max_weight', '')
            
            # Destination sub-header
            dest_label = f"<b>{dest_name}</b>"
            if arrival:
                dest_label += f"  —  Arrival: {arrival}"
            if min_wt and max_wt:
                dest_label += f"  |  Weight: {min_wt} – {max_wt} kg"
            
            elements.append(Spacer(1, 0.1*inch))
            elements.append(Paragraph(dest_label, ParagraphStyle(
                'DestSubHeader',
                fontSize=10,
                textColor=colors.white,
                backColor=colors.HexColor('#2563EB'),
                spaceBefore=4,
                spaceAfter=4,
                leftIndent=4,
                rightIndent=4,
            )))
            
            # Table: Fish | Cut | Grade | Wt Range | Airfreight/kg | Price/kg | Total/kg
            sum_header = ['Fish', 'Cut', 'Grade', 'Wt/Fish (kg)', 'Airfreight/kg', 'Price/kg', 'Total/kg']
            sum_data = [sum_header]
            
            for size in sizes:
                price_per_kg = float(size.get('price_per_kg', 0))
                total_per_kg = airfreight + price_per_kg
                sum_data.append([
                    Paragraph(str(size.get('fish_type', '-')), cell_normal),
                    Paragraph(str(size.get('cut_name', '-')), cell_center),
                    Paragraph(str(size.get('grade_name', '-')), cell_center),
                    Paragraph(str(size.get('weight_range', '-')), cell_center),
                    Paragraph(f"${airfreight:.2f}", cell_right),
                    Paragraph(f"${price_per_kg:.2f}", cell_right),
                    Paragraph(f"${total_per_kg:.2f}", cell_right_bold),
                ])
            
            sum_table = Table(sum_data, colWidths=[1.6*inch, 0.8*inch, 0.8*inch, 0.9*inch, 1*inch, 0.9*inch, 0.9*inch], repeatRows=1)
            sum_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A3D5C')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')]),
            ]))
            elements.append(sum_table)
    
    # Notes
    if quote_data.get('notes'):
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("<b>Notes:</b>", styles['Heading3']))
        elements.append(Paragraph(quote_data['notes'], styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


# ═══════════════════════════════════════════════════════════
# BPL PDF GENERATORS
# ═══════════════════════════════════════════════════════════


def generate_bpl_owner_pdf(bpl_data: Dict[str, Any]) -> bytes:
    """
    Generate a Blue Lotus branded BPL PDF for the owner.
    Includes logo, header banner, shipment info, and box details.
    """
    import io

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter,
                         rightMargin=0.5*inch, leftMargin=0.5*inch,
                         topMargin=0.5*inch, bottomMargin=0.9*inch)

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template = PageTemplate(id='main', frames=frame, onPage=add_page_footer)
    doc.addPageTemplates([template])

    elements = []
    styles = getSampleStyleSheet()
    brand = colors.HexColor('#0A3D5C')

    # ── Header banner with logo ──
    if os.path.exists(LOGO_PATH):
        logo_img = Image(LOGO_PATH, width=0.8*inch, height=0.8*inch)
        header_data = [[
            logo_img,
            Paragraph("<b>Blue Lotus Foods LLC</b>", ParagraphStyle(
                'BannerLeft', fontSize=18, textColor=colors.white, alignment=TA_LEFT)),
            Paragraph("<b>Detailed BPL</b>", ParagraphStyle(
                'BannerRight', fontSize=14, textColor=colors.white, alignment=TA_RIGHT)),
        ]]
        header_table = Table(header_data, colWidths=[1.0*inch, 4.2*inch, 2.3*inch])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), brand),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 10),
            ('RIGHTPADDING', (-1, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 0.15*inch))

    # ── Shipment info grid ──
    po_number = bpl_data.get('po_number', 'N/A')
    invoice_number = bpl_data.get('invoice_number') or 'N/A'
    air_way_bill = bpl_data.get('air_way_bill') or 'N/A'
    packed_date = format_date(bpl_data.get('packed_date')) if bpl_data.get('packed_date') else 'N/A'
    expiry_date = format_date(bpl_data.get('expiry_date')) if bpl_data.get('expiry_date') else 'N/A'
    port_code = bpl_data.get('port_code', 'N/A')
    total_boxes = bpl_data.get('total_boxes', 0)

    info_data = [
        ['PO #:', po_number, 'Port:', port_code],
        ['Invoice #:', invoice_number, 'Total Boxes:', str(total_boxes)],
        ['Air Way Bill #:', air_way_bill, '', ''],
        ['Packed Date:', packed_date, 'Expiry Date:', expiry_date],
    ]
    info_table = Table(info_data, colWidths=[1.1*inch, 2.4*inch, 1.1*inch, 2.4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), brand),
        ('TEXTCOLOR', (2, 0), (2, -1), brand),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2*inch))

    # ── Box details per PO item ──
    _build_bpl_box_tables(elements, bpl_data, styles, brand, owner_mode=True)

    # ── Notes ──
    notes = bpl_data.get('notes')
    if notes:
        elements.append(Spacer(1, 0.15*inch))
        elements.append(Paragraph("<b>Notes:</b>", styles['Normal']))
        elements.append(Paragraph(notes, styles['Normal']))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_bpl_vendor_pdf(bpl_data: Dict[str, Any]) -> bytes:
    """
    Generate a plain BPL PDF for the vendor.
    Includes vendor name/details, shipment info, and box details — no BLF branding.
    """
    import io

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter,
                         rightMargin=0.5*inch, leftMargin=0.5*inch,
                         topMargin=0.5*inch, bottomMargin=0.7*inch)

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    doc.addPageTemplates([PageTemplate(id='main', frames=frame)])

    elements = []
    styles = getSampleStyleSheet()
    dark = colors.HexColor('#1e293b')

    # ── Title ──
    elements.append(Paragraph(
        "<b>Box Packaging List</b>",
        ParagraphStyle('BPLTitle', fontSize=18, textColor=dark, alignment=TA_CENTER, spaceAfter=8)))
    elements.append(Spacer(1, 0.1*inch))

    # ── Vendor info ──
    vendor_name = bpl_data.get('vendor_name', 'N/A')
    vendor_country = bpl_data.get('vendor_country', '')
    vendor_email = bpl_data.get('vendor_email', '')

    vendor_lines = [f"<b>{vendor_name}</b>"]
    if vendor_country:
        vendor_lines.append(vendor_country)
    if vendor_email:
        vendor_lines.append(vendor_email)

    elements.append(Paragraph("<br/>".join(vendor_lines), ParagraphStyle(
        'VendorInfo', fontSize=11, textColor=dark, spaceAfter=10)))
    elements.append(Spacer(1, 0.05*inch))

    # ── Shipment info grid ──
    po_number = bpl_data.get('po_number', 'N/A')
    invoice_number = bpl_data.get('invoice_number') or 'N/A'
    air_way_bill = bpl_data.get('air_way_bill') or 'N/A'
    packed_date = format_date(bpl_data.get('packed_date')) if bpl_data.get('packed_date') else 'N/A'
    expiry_date = format_date(bpl_data.get('expiry_date')) if bpl_data.get('expiry_date') else 'N/A'
    port_code = bpl_data.get('port_code', 'N/A')
    total_boxes = bpl_data.get('total_boxes', 0)

    info_data = [
        ['PO #:', po_number, 'Port:', port_code],
        ['Invoice #:', invoice_number, 'Total Boxes:', str(total_boxes)],
        ['Air Way Bill #:', air_way_bill, '', ''],
        ['Packed Date:', packed_date, 'Expiry Date:', expiry_date],
    ]
    info_table = Table(info_data, colWidths=[1.1*inch, 2.4*inch, 1.1*inch, 2.4*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), dark),
        ('TEXTCOLOR', (2, 0), (2, -1), dark),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2*inch))

    # ── Box details per PO item ──
    _build_bpl_box_tables(elements, bpl_data, styles, dark)

    # ── Notes ──
    notes = bpl_data.get('notes')
    if notes:
        elements.append(Spacer(1, 0.15*inch))
        elements.append(Paragraph("<b>Notes:</b>", styles['Normal']))
        elements.append(Paragraph(notes, styles['Normal']))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def _fmt_weight_range(from_kg: float, to_kg: float) -> str:
    """Convert a kg range to a display string.
    If the lb value is < 1 → display in oz (rounded to nearest whole oz).
    If >= 1 lb → round to nearest 0.5 lb.
    """
    def kg_to_display(kg: float) -> str:
        lbs = kg * 2.205
        if lbs < 1.0:
            return f"{round(lbs * 16)}oz"
        rounded = round(lbs * 2) / 2
        return f"{rounded:.1f}lbs"
    return f"{kg_to_display(from_kg)} \u2013 {kg_to_display(to_kg)}"


def _build_bpl_box_tables(elements, bpl_data: Dict[str, Any], styles, accent_color, owner_mode=False):
    """Shared helper: build box detail tables grouped by PO item.
    owner_mode=True  → no size in banner, stacked weights, LBS columns, summary table
    owner_mode=False → includes size, comma-sep weights, KG only, no summary
    """
    KG_TO_LBS = 2.205
    items = bpl_data.get('items', [])

    # Collect per-item totals for the summary table (owner only)
    summary_rows = []  # list of (label, total_kg, total_lbs)

    for item in items:
        fish_label = item.get('fish_name', '')
        cut_label = item.get('cut_name', '')
        grade_label = item.get('grade_name', '')
        size_label = item.get('fish_size') or ''

        sub_header_text = f"{fish_label} · {cut_label} · {grade_label}"
        if not owner_mode and size_label:
            sub_header_text += f" · {size_label}"

        # Sub-header bar
        sh_data = [[Paragraph(f"<b>{sub_header_text}</b>", ParagraphStyle(
            'ItemSub', fontSize=10, textColor=colors.white))]]
        sh_table = Table(sh_data, colWidths=[7.5*inch])
        sh_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), accent_color),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(sh_table)

        if owner_mode:
            elements.append(Spacer(1, 0.08*inch))

        boxes = item.get('boxes', [])
        if not boxes:
            elements.append(Paragraph("No boxes", styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))
            if owner_mode:
                summary_rows.append((sub_header_text, 0.0, 0.0))
            continue

        item_total_kg = 0.0
        item_total_lbs = 0.0

        if owner_mode:
            # ── Owner: 6 columns, stacked weights, LBS ──
            table_data = [['Box #', '# Pcs', 'Individual Wt (KG)', 'Individual Wt (LBS)',
                            'Total Wt (KG)', 'Total Wt (LBS)']]

            for box in boxes:
                pieces = box.get('pieces', [])
                from_kg = box.get('weight_range_from_kg')
                to_kg = box.get('weight_range_to_kg')
                if pieces:
                    kg_lines = '<br/>'.join(
                        [f"Pc{p['piece_number']}: {float(p['weight_kg']):.1f}" for p in pieces])
                    lbs_lines = '<br/>'.join(
                        [f"Pc{p['piece_number']}: {float(p['weight_kg']) * KG_TO_LBS:.1f}" for p in pieces])
                elif from_kg is not None and to_kg is not None:
                    kg_lines = f"From: {float(from_kg):.3f}<br/>To: {float(to_kg):.3f}"
                    lbs_lines = _fmt_weight_range(float(from_kg), float(to_kg))
                else:
                    kg_lines = '-'
                    lbs_lines = '-'

                box_total_kg = sum(float(p['weight_kg']) for p in pieces) if pieces else float(box.get('net_weight_kg', 0))
                box_total_lbs = box_total_kg * KG_TO_LBS
                item_total_kg += box_total_kg
                item_total_lbs += box_total_lbs

                piece_style = ParagraphStyle('PieceCell', fontSize=8, leading=11)
                table_data.append([
                    str(box.get('box_number', '')),
                    str(box.get('num_pieces', len(pieces))),
                    Paragraph(kg_lines, piece_style),
                    Paragraph(lbs_lines, piece_style),
                    f"{box_total_kg:.1f}",
                    f"{box_total_lbs:.1f}",
                ])

            # Totals row
            table_data.append(['', '', '', '',
                               f"{item_total_kg:.1f}", f"{item_total_lbs:.1f}"])

            t = Table(table_data, colWidths=[0.55*inch, 0.55*inch, 1.8*inch, 1.8*inch, 1.0*inch, 1.0*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#D1D5DB')),
                ('LINEABOVE', (0, -1), (-1, -1), 1, accent_color),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (1, -1), 'CENTER'),
                ('ALIGN', (4, 0), (5, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))

        else:
            # ── Vendor: 4 columns, comma-sep weights, KG only ──
            table_data = [['Box #', '# Pieces', 'Individual Weights (KG)', 'Total Wt (KG)']]

            for box in boxes:
                pieces = box.get('pieces', [])
                from_kg = box.get('weight_range_from_kg')
                to_kg = box.get('weight_range_to_kg')
                if pieces:
                    piece_weights = [f"Pc{p['piece_number']}: {float(p['weight_kg']):.1f}" for p in pieces]
                    piece_str = ', '.join(piece_weights)
                elif from_kg is not None and to_kg is not None:
                    piece_str = f"From: {float(from_kg):.3f} / To: {float(to_kg):.3f}"
                else:
                    piece_str = '-'
                box_total_kg = sum(float(p['weight_kg']) for p in pieces) if pieces else float(box.get('net_weight_kg', 0))
                item_total_kg += box_total_kg

                table_data.append([
                    str(box.get('box_number', '')),
                    str(box.get('num_pieces', len(pieces))),
                    Paragraph(piece_str, ParagraphStyle('PieceCell', fontSize=9, leading=12)),
                    f"{box_total_kg:.1f}",
                ])

            # Totals row
            table_data.append(['', '', '', f"{item_total_kg:.1f}"])

            t = Table(table_data, colWidths=[0.7*inch, 0.8*inch, 4.2*inch, 1.2*inch])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#D1D5DB')),
                ('LINEABOVE', (0, -1), (-1, -1), 1, accent_color),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (1, -1), 'CENTER'),
                ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))

        elements.append(t)
        elements.append(Spacer(1, 0.15*inch))

        if owner_mode:
            item_total_lbs = item_total_kg * KG_TO_LBS if item_total_lbs == 0 else item_total_lbs
            summary_rows.append((sub_header_text, item_total_kg, item_total_lbs))

    # ── Summary table at the end (owner only) ──
    if owner_mode and summary_rows:
        elements.append(Spacer(1, 0.1*inch))

        # Header row
        sum_data = [['', 'Wt (KG)', 'Wt (LBS)']]

        grand_kg = 0.0
        grand_lbs = 0.0
        for label, kg, lbs in summary_rows:
            sum_data.append([label, f"{kg:,.1f}", f"{lbs:,.1f}"])
            grand_kg += kg
            grand_lbs += lbs

        # Grand total row
        sum_data.append([Paragraph("<b>Grand Total</b>", ParagraphStyle('GT', fontSize=10)),
                         f"{grand_kg:,.1f}", f"{grand_lbs:,.1f}"])

        sum_table = Table(sum_data, colWidths=[3.2*inch, 1.0*inch, 1.0*inch])
        sum_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#D1D5DB')),
            ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, accent_color),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ]))
        elements.append(sum_table)
