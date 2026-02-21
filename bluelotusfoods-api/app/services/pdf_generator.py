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

# PDF storage directory
PDF_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'pdfs')

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

def ensure_pdf_directory():
    """Create PDF storage directory if it doesn't exist"""
    os.makedirs(PDF_STORAGE_DIR, exist_ok=True)
    return PDF_STORAGE_DIR

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

def generate_estimate_pdf(estimate_data: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    """
    Generate a PDF for a buyer estimate using ReportLab
    
    Args:
        estimate_data: Estimate details (estimate_number, company_name, buyer_names, etc.)
        items: List of estimate items with pricing details
    
    Returns:
        str: Path to the generated PDF file
    """
    ensure_pdf_directory()
    
    # Generate filename: date-BLF-Pricing-{estimate_number}.pdf
    date_str = datetime.now().strftime('%Y-%m-%d')
    estimate_number = estimate_data.get('estimate_number', 'UNKNOWN')
    pdf_filename = f"{date_str}-BLF-Pricing-{estimate_number}.pdf"
    pdf_path = os.path.join(PDF_STORAGE_DIR, pdf_filename)
    
    # Create PDF document with custom page template
    doc = BaseDocTemplate(pdf_path, pagesize=letter,
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
    
    # Count pages in the generated PDF
    from PyPDF2 import PdfReader
    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        doc.total_pages = total_pages
        
        # Rebuild with page count information
        doc.build(elements)
    except:
        # If PyPDF2 is not available, just use the first build
        pass
    
    return pdf_path

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
