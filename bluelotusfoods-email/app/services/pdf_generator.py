import io
from datetime import datetime
from typing import List
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from app.schemas.email import VendorQuoteData


class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for the PDF"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            textColor=colors.HexColor('#1f4e79')
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'], 
            fontSize=14,
            spaceAfter=12,
            textColor=colors.HexColor('#2d5aa0')
        ))
    
    def generate_vendor_quote_pdf(self, quote_data: VendorQuoteData) -> bytes:
        """Generate PDF for vendor quote"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        # Build the PDF content
        story = []
        
        # Header
        story.append(Paragraph("VENDOR QUOTE CONFIRMATION", self.styles['CustomTitle']))
        story.append(Spacer(1, 12))
        
        # Quote Information
        quote_info = [
            ['Quote ID:', str(quote_data.quote_id)],
            ['Vendor:', quote_data.vendor_name],
            ['Country of Origin:', quote_data.country_of_origin],
            ['Valid Until:', quote_data.quote_valid_till.strftime('%B %d, %Y')],
            ['Fish Type:', quote_data.fish_type],
            ['Date Created:', quote_data.created_at.strftime('%B %d, %Y %I:%M %p')]
        ]
        
        quote_table = Table(quote_info, colWidths=[2*inch, 4*inch])
        quote_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ]))
        
        story.append(quote_table)
        story.append(Spacer(1, 20))
        
        # Destinations
        if quote_data.destinations:
            story.append(Paragraph("DESTINATIONS & LOGISTICS", self.styles['CustomHeading']))
            
            dest_data = [['Destination', 'Airfreight/Kg', 'Arrival Date', 'Min Weight', 'Max Weight']]
            for dest in quote_data.destinations:
                dest_data.append([
                    dest.destination,
                    dest.airfreight_per_kg,
                    dest.arrival_date,
                    dest.min_weight,
                    dest.max_weight
                ])
            
            dest_table = Table(dest_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
            dest_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472c4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(dest_table)
            story.append(Spacer(1, 20))
        
        # Sizes & Pricing
        if quote_data.sizes:
            story.append(Paragraph("PRODUCT DETAILS & PRICING", self.styles['CustomHeading']))
            
            size_data = [['Fish Type', 'Cut', 'Grade', 'Weight Range', 'Price/Kg', 'Quantity']]
            for size in quote_data.sizes:
                size_data.append([
                    size.fish_type,
                    size.cut_name,  # Changed from size.cut to size.cut_name
                    size.grade_name,  # Changed from size.grade to size.grade_name
                    size.weight_range,
                    size.price_per_kg,
                    size.quantity
                ])
            
            size_table = Table(size_data, colWidths=[1*inch, 0.8*inch, 0.8*inch, 1*inch, 1*inch, 1*inch])
            size_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472c4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(size_table)
            story.append(Spacer(1, 20))
        
        # Quote Summary - Breakdown by Destination
        if quote_data.destinations and quote_data.sizes:
            story.append(Paragraph("QUOTE SUMMARY", self.styles['CustomHeading']))
            story.append(Spacer(1, 10))
            
            for dest in quote_data.destinations:
                # Destination header
                dest_header = f"{dest.destination} - Arrival: {dest.arrival_date}"
                story.append(Paragraph(dest_header, self.styles['Heading3']))
                story.append(Spacer(1, 6))
                
                # Summary table for this destination
                summary_data = [['Fish', 'Cut', 'Grade', 'Wt/Fish (Kg up)', 'Airfreight/kg', 'Price/kg', 'Total/kg']]
                
                airfreight_per_kg = float(dest.airfreight_per_kg)
                
                for size in quote_data.sizes:
                    price_per_kg = float(size.price_per_kg)
                    total_per_kg = airfreight_per_kg + price_per_kg
                    
                    summary_data.append([
                        size.fish_type,
                        size.cut_name,
                        size.grade_name,
                        str(size.weight_range),
                        f"${airfreight_per_kg:.2f}",
                        f"${price_per_kg:.2f}",
                        f"${total_per_kg:.2f}"
                    ])
                
                summary_table = Table(summary_data, colWidths=[1.1*inch, 0.8*inch, 0.7*inch, 1*inch, 0.9*inch, 0.8*inch, 0.8*inch])
                summary_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (3, -1), 'LEFT'),
                    ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f9fafb'), colors.white]),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (6, 1), (6, -1), 'Helvetica-Bold'),
                    ('TEXTCOLOR', (6, 1), (6, -1), colors.HexColor('#1e40af')),
                ]))
                
                story.append(summary_table)
                
                # Weight range info
                if dest.min_weight and dest.max_weight:
                    weight_info = f"Weight Range: {dest.min_weight} - {dest.max_weight} kg"
                    story.append(Spacer(1, 6))
                    story.append(Paragraph(weight_info, self.styles['Normal']))
                
                story.append(Spacer(1, 15))
        
        # Additional Information
        story.append(Paragraph("ADDITIONAL INFORMATION", self.styles['CustomHeading']))
        
        additional_info = []
        if quote_data.price_negotiable:
            additional_info.append("✓ Price is negotiable")
        if quote_data.exclusive_offer:
            additional_info.append("✓ This is an exclusive offer")
        
        if additional_info:
            for info in additional_info:
                story.append(Paragraph(info, self.styles['Normal']))
            story.append(Spacer(1, 12))
        
        # Notes
        if quote_data.notes:
            story.append(Paragraph("NOTES", self.styles['CustomHeading']))
            story.append(Paragraph(quote_data.notes, self.styles['Normal']))
            story.append(Spacer(1, 20))
        
        # Footer
        story.append(Spacer(1, 30))
        story.append(Paragraph("Thank you for your quote submission!", self.styles['Normal']))
        story.append(Paragraph("Blue Lotus Foods Team", self.styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        # Get the PDF data
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return pdf_data