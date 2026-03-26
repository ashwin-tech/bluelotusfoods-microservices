import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
import aiosmtplib
from app.core.settings import settings
from app.schemas.email import VendorQuoteData, EmailResponse, SendBPLEmailRequest, SendBPLUploadedEmailRequest
import base64
from app.services.pdf_generator import generate_vendor_quote_pdf, generate_estimate_pdf, generate_bpl_owner_pdf, generate_bpl_vendor_pdf
import structlog

logger = structlog.get_logger()


class EmailService:
    def __init__(self):
        pass
    
    async def send_vendor_quote_email(
        self, 
        vendor_email: str, 
        vendor_name: str, 
        quote_data: VendorQuoteData
    ) -> EmailResponse:
        """Send vendor quote confirmation email with PDF attachment"""
        try:
            # Check if we're in simulation mode
            if settings.email_simulation_mode:
                logger.warning("Email simulation mode enabled - generating PDF but skipping SMTP")
                # Generate PDF but skip actual email sending
                # Convert VendorQuoteData to dict for the function
                quote_dict = {
                    'quote_id': quote_data.quote_id,
                    'vendor_name': quote_data.vendor_name,
                    'vendor_code': quote_data.vendor_code,
                    'country_of_origin': quote_data.country_of_origin,
                    'quote_valid_till': quote_data.quote_valid_till,
                    'fish_type': quote_data.fish_type,
                    'destinations': [d.dict() for d in quote_data.destinations],
                    'sizes': [s.dict() for s in quote_data.sizes],
                    'notes': quote_data.notes,
                    'price_negotiable': quote_data.price_negotiable,
                    'exclusive_offer': quote_data.exclusive_offer,
                    'created_at': quote_data.created_at
                }
                pdf_data = generate_vendor_quote_pdf(quote_dict)
                logger.info(f"Generated PDF for quote {quote_data.quote_id}, size: {len(pdf_data)} bytes")
                return EmailResponse(
                    success=True,
                    message="Email simulation successful - PDF generated, SMTP skipped",
                    email_id=f"quote_{quote_data.quote_id}_simulation"
                )
            
            # Check if SMTP is configured
            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping email send")
                return EmailResponse(
                    success=False,
                    message="Email service not configured (missing SMTP credentials)"
                )
            
            # Generate PDF
            # Convert VendorQuoteData to dict for the function
            quote_dict = {
                'quote_id': quote_data.quote_id,
                'vendor_name': quote_data.vendor_name,
                'vendor_code': quote_data.vendor_code,
                'country_of_origin': quote_data.country_of_origin,
                'quote_valid_till': quote_data.quote_valid_till,
                'fish_type': quote_data.fish_type,
                'destinations': [d.dict() for d in quote_data.destinations],
                'sizes': [s.dict() for s in quote_data.sizes],
                'notes': quote_data.notes,
                'price_negotiable': quote_data.price_negotiable,
                'exclusive_offer': quote_data.exclusive_offer,
                'created_at': quote_data.created_at
            }
            pdf_data = generate_vendor_quote_pdf(quote_dict)
            
            # Create email message
            message = MIMEMultipart()
            message["From"] = f"{settings.from_name} <{settings.from_email}>"
            message["To"] = vendor_email
            message["Subject"] = f"Quote Confirmation #{quote_data.quote_id} - Blue Lotus Foods"
            
            # Email body
            email_body = self._create_email_body(vendor_name, quote_data)
            message.attach(MIMEText(email_body, "html"))
            
            # Attach PDF
            pdf_attachment = MIMEBase('application', 'octet-stream')
            pdf_attachment.set_payload(pdf_data)
            encoders.encode_base64(pdf_attachment)
            pdf_attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="quote_{quote_data.quote_id}_confirmation.pdf"'
            )
            message.attach(pdf_attachment)
            
            # Send email
            await self._send_email(message)
            
            logger.info(
                "Vendor quote email sent successfully",
                quote_id=quote_data.quote_id,
                vendor_email=vendor_email
            )
            
            return EmailResponse(
                success=True,
                message="Email sent successfully",
                email_id=f"quote_{quote_data.quote_id}"
            )
            
        except Exception as e:
            logger.error(
                "Failed to send vendor quote email",
                error=str(e),
                quote_id=quote_data.quote_id,
                vendor_email=vendor_email
            )
            return EmailResponse(
                success=False,
                message=f"Failed to send email: {str(e)}"
            )
    
    async def send_owner_notification_email(
        self, 
        owner_email: str, 
        vendor_name: str, 
        quote_data: VendorQuoteData
    ) -> EmailResponse:
        """Send owner notification email when a vendor submits a quote"""
        try:
            # Check if we're in simulation mode
            if settings.email_simulation_mode:
                logger.warning("Email simulation mode enabled - generating PDF but skipping SMTP")
                # Generate PDF but skip actual email sending
                quote_dict = {
                    'quote_id': quote_data.quote_id,
                    'vendor_name': quote_data.vendor_name,
                    'vendor_code': quote_data.vendor_code,
                    'country_of_origin': quote_data.country_of_origin,
                    'quote_valid_till': quote_data.quote_valid_till,
                    'fish_type': quote_data.fish_type,
                    'destinations': [d.dict() for d in quote_data.destinations],
                    'sizes': [s.dict() for s in quote_data.sizes],
                    'notes': quote_data.notes,
                    'price_negotiable': quote_data.price_negotiable,
                    'exclusive_offer': quote_data.exclusive_offer,
                    'created_at': quote_data.created_at
                }
                pdf_data = generate_vendor_quote_pdf(quote_dict)
                logger.info(f"Generated PDF for owner notification quote {quote_data.quote_id}, size: {len(pdf_data)} bytes")
                return EmailResponse(
                    success=True,
                    message="Owner notification email simulation successful - PDF generated, SMTP skipped",
                    email_id=f"owner_notification_quote_{quote_data.quote_id}_simulation"
                )
            
            # Check if SMTP is configured
            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping owner notification email")
                return EmailResponse(
                    success=False,
                    message="Email service not configured (missing SMTP credentials)"
                )
            
            # Generate PDF
            quote_dict = {
                'quote_id': quote_data.quote_id,
                'vendor_name': quote_data.vendor_name,
                'vendor_code': quote_data.vendor_code,
                'country_of_origin': quote_data.country_of_origin,
                'quote_valid_till': quote_data.quote_valid_till,
                'fish_type': quote_data.fish_type,
                'destinations': [d.dict() for d in quote_data.destinations],
                'sizes': [s.dict() for s in quote_data.sizes],
                'notes': quote_data.notes,
                'price_negotiable': quote_data.price_negotiable,
                'exclusive_offer': quote_data.exclusive_offer,
                'created_at': quote_data.created_at
            }
            pdf_data = generate_vendor_quote_pdf(quote_dict)
            
            # Create email message
            message = MIMEMultipart()
            message["From"] = f"{settings.from_name} <{settings.from_email}>"
            message["To"] = owner_email
            
            # Format the subject with vendor name, quote ID, and current time in Central Time
            from datetime import datetime
            import pytz
            central_tz = pytz.timezone('US/Central')
            current_time_ct = datetime.now(central_tz).strftime('%m/%d/%Y %I:%M %p')
            
            message["Subject"] = f"New Quote Message - {vendor_name} - quote #{quote_data.quote_id} - {current_time_ct}"
            
            # Email body
            email_body = self._create_owner_notification_body(vendor_name, quote_data)
            message.attach(MIMEText(email_body, "html"))
            
            # Attach PDF
            pdf_attachment = MIMEBase('application', 'octet-stream')
            pdf_attachment.set_payload(pdf_data)
            encoders.encode_base64(pdf_attachment)
            pdf_attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="quote_{quote_data.quote_id}_confirmation.pdf"'
            )
            message.attach(pdf_attachment)
            
            # Send email
            await self._send_email(message)
            
            logger.info(
                "Owner notification email sent successfully",
                quote_id=quote_data.quote_id,
                owner_email=owner_email,
                vendor_name=vendor_name
            )
            
            return EmailResponse(
                success=True,
                message="Owner notification email sent successfully",
                email_id=f"owner_notification_quote_{quote_data.quote_id}"
            )
            
        except Exception as e:
            logger.error(
                "Failed to send owner notification email",
                error=str(e),
                quote_id=quote_data.quote_id,
                owner_email=owner_email
            )
            return EmailResponse(
                success=False,
                message=f"Failed to send owner notification email: {str(e)}"
            )
    
    def _create_owner_notification_body(self, vendor_name: str, quote_data: VendorQuoteData) -> str:
        """Create HTML email body for owner notification"""
        # Format destinations for display
        destinations_html = ""
        for dest in quote_data.destinations:
            destinations_html += f"""
            <tr>
                <td>{dest.destination}</td>
                <td>${dest.airfreight_per_kg}/kg</td>
                <td>{dest.arrival_date}</td>
                <td>{dest.min_weight} - {dest.max_weight} kg</td>
            </tr>
            """
        
        # Format products for display
        products_html = ""
        for product in quote_data.sizes:
            products_html += f"""
            <tr>
                <td>{product.fish_type}</td>
                <td>{product.cut_name}</td>
                <td>{product.grade_name}</td>
                <td>{product.weight_range}</td>
                <td>${product.price_per_kg}/kg</td>
                <td>{product.quantity}</td>
            </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1f4e79; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .footer {{ padding: 15px; text-align: center; font-size: 12px; color: #666; }}
                .highlight {{ background-color: #e7f3ff; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #4472c4; color: white; }}
                .note {{ background-color: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>New Quote Submitted</h1>
                    <h2>Quote #{quote_data.quote_id}</h2>
                </div>
                
                <div class="content">
                    <p>Dear Blue Lotus Sales,</p>
                    
                    <p><strong>New quote submitted by vendor {vendor_name}</strong></p>
                    
                    <div class="highlight">
                        <h3>Quote Summary:</h3>
                        <ul>
                            <li><strong>Quote ID:</strong> {quote_data.quote_id}</li>
                            <li><strong>Vendor:</strong> {vendor_name} ({quote_data.vendor_code})</li>
                            <li><strong>Fish Type:</strong> {quote_data.fish_type}</li>
                            <li><strong>Country of Origin:</strong> {quote_data.country_of_origin}</li>
                            <li><strong>Valid Until:</strong> {quote_data.quote_valid_till.strftime('%B %d, %Y')}</li>
                            <li><strong>Price Negotiable:</strong> {'Yes' if quote_data.price_negotiable else 'No'}</li>
                            <li><strong>Exclusive Offer:</strong> {'Yes' if quote_data.exclusive_offer else 'No'}</li>
                        </ul>
                    </div>
                    
                    <h3>Destinations:</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Destination</th>
                                <th>Airfreight/kg</th>
                                <th>Arrival Date</th>
                                <th>Weight Range (kg)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {destinations_html}
                        </tbody>
                    </table>
                    
                    <h3>Products:</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Fish Type</th>
                                <th>Cut</th>
                                <th>Grade</th>
                                <th>Weight Range</th>
                                <th>Price/kg</th>
                                <th>Quantity</th>
                            </tr>
                        </thead>
                        <tbody>
                            {products_html}
                        </tbody>
                    </table>
                    
                    {f'<div class="note"><strong>Notes:</strong> {quote_data.notes}</div>' if quote_data.notes else ''}
                    
                    <p><strong>Please find the attached PDF with complete details.</strong></p>
                    
                    <p>Thank you,<br>
                    <strong>Vendor Quote System</strong></p>
                </div>
                
                <div class="footer">
                    <p>This is an automated notification from the Vendor Quote System.</p>
                    <p>© Blue Lotus Foods LLC. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _create_email_body(self, vendor_name: str, quote_data: VendorQuoteData) -> str:
        """Create HTML email body"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #1f4e79; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .footer {{ padding: 15px; text-align: center; font-size: 12px; color: #666; }}
                .highlight {{ background-color: #e7f3ff; padding: 10px; border-radius: 5px; margin: 10px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #4472c4; color: white; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Quote Confirmation</h1>
                    <h2>#{quote_data.quote_id}</h2>
                </div>
                
                <div class="content">
                    <p>Dear {vendor_name},</p>
                    
                    <p>Thank you for submitting your quote for <strong>{quote_data.fish_type}</strong> from <strong>{quote_data.country_of_origin}</strong>.</p>
                    
                    <div class="highlight">
                        <h3>Quote Summary:</h3>
                        <ul>
                            <li><strong>Quote ID:</strong> {quote_data.quote_id}</li>
                            <li><strong>Valid Until:</strong> {quote_data.quote_valid_till.strftime('%B %d, %Y')}</li>
                            <li><strong>Fish Type:</strong> {quote_data.fish_type}</li>
                            <li><strong>Country of Origin:</strong> {quote_data.country_of_origin}</li>
                        </ul>
                    </div>
                    
                    <p>Please find the detailed quote confirmation attached as a PDF document.</p>
                    
                    <p>If you have any questions or need to make changes to this quote, please contact us immediately.</p>
                    
                    <p>Thank you for your business!</p>
                    
                    <p>Best regards,<br>
                    <strong>Blue Lotus Foods Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>This is an automated email. Please do not reply directly to this email.</p>
                    <p>© Blue Lotus Foods LLC. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    async def _send_email(self, message: MIMEMultipart):
        """Send email using SMTP"""
        try:
            if settings.smtp_use_tls:
                await aiosmtplib.send(
                    message,
                    hostname=settings.smtp_server,
                    port=settings.smtp_port,
                    start_tls=True,
                    username=settings.smtp_username,
                    password=settings.smtp_password,
                )
            else:
                await aiosmtplib.send(
                    message,
                    hostname=settings.smtp_server,
                    port=settings.smtp_port,
                    username=settings.smtp_username,
                    password=settings.smtp_password,
                )
        except Exception as e:
            logger.error("SMTP send failed", error=str(e))
            raise
    
    async def send_buyer_pricing_email(
        self,
        buyer_emails: list[str],
        buyer_name: str,
        company_name: str,
        estimate_number: str,
        items: list,
        delivery_date_from: str = None,
        delivery_date_to: str = None,
        notes: str = None
    ) -> EmailResponse:
        """Send buyer pricing estimate email with PDF attachment"""
        try:
            # Prepare estimate data
            estimate_data = {
                'estimate_number': estimate_number,
                'estimate_date': datetime.now().strftime("%Y-%m-%d"),
                'company_name': company_name,
                'buyer_names': buyer_name,  # Pass as string, not list
                'delivery_date_from': delivery_date_from,
                'delivery_date_to': delivery_date_to,
                'notes': notes
            }
            
            # Convert items to dict format
            items_dict = [
                {
                    'vendor_name': item.vendor_name,
                    'common_name': item.common_name,
                    'scientific_name': item.scientific_name or '',
                    'cut_name': item.cut,
                    'grade_name': item.grade,
                    'fish_size': item.fish_size,
                    'port_code': item.port,
                    'offer_quantity': item.offer_quantity,
                    'fish_price': item.fish_price,
                    'margin': item.margin,
                    'freight_price': item.freight_price,
                    'tariff_percent': item.tariff_percent,
                    'clearing_charges': item.clearing_charges,
                    'total_price': item.total_price,
                    'fish_species_id': item.fish_species_id,
                    'cut_id': item.cut_id,
                    'grade_id': item.grade_id,
                }
                for item in items
            ]
            
            # Check if we're in simulation mode
            if settings.email_simulation_mode:
                logger.warning("Email simulation mode enabled - generating PDF but skipping SMTP")
                # Generate PDF using the shared function - returns bytes directly
                pdf_data = generate_estimate_pdf(estimate_data, items_dict)
                logger.info(f"Generated buyer pricing PDF for estimate {estimate_number}, size: {len(pdf_data)} bytes")
                return EmailResponse(
                    success=True,
                    message="Email simulation successful - PDF generated, SMTP skipped",
                    email_id=f"estimate_{estimate_number}_simulation"
                )
            
            # Check if SMTP is configured
            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping email send")
                return EmailResponse(
                    success=False,
                    message="Email service not configured (missing SMTP credentials)"
                )
            
            # Generate PDF using the shared function (returns bytes)
            pdf_data = generate_estimate_pdf(estimate_data, items_dict)
            
            # Create email message
            message = MIMEMultipart()
            message["From"] = f"{settings.from_name} <{settings.from_email}>"
            message["To"] = ", ".join(buyer_emails)
            message["Subject"] = f"Pricing - Blue Lotus Foods - {datetime.now().strftime('%m/%d/%Y %I:%M %p')}"
            
            # Email body
            email_body = self._create_buyer_pricing_email_body(
                buyer_name, company_name, estimate_number, items,
                delivery_date_from, delivery_date_to, notes
            )
            message.attach(MIMEText(email_body, "html"))
            
            # Attach PDF
            pdf_attachment = MIMEBase('application', 'octet-stream')
            pdf_attachment.set_payload(pdf_data)
            encoders.encode_base64(pdf_attachment)
            pdf_attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="estimate_{estimate_number}_{company_name.replace(" ", "_")}.pdf"'
            )
            message.attach(pdf_attachment)
            
            # Send email
            await self._send_email(message)
            
            logger.info(
                "Buyer pricing email sent successfully",
                estimate_number=estimate_number,
                buyer_emails=buyer_emails
            )
            
            return EmailResponse(
                success=True,
                message="Email sent successfully",
                email_id=f"estimate_{estimate_number}"
            )
            
        except Exception as e:
            logger.error(
                "Failed to send buyer pricing email",
                error=str(e),
                estimate_number=estimate_number,
                buyer_emails=buyer_emails
            )
            return EmailResponse(
                success=False,
                message=f"Failed to send email: {str(e)}"
            )
    
    def _create_buyer_pricing_email_body(
        self,
        buyer_name: str,
        company_name: str,
        estimate_number: str,
        items: list,
        delivery_date_from: str = None,
        delivery_date_to: str = None,
        notes: str = None
    ) -> str:
        """Create HTML email body for buyer pricing estimate"""
        
        # Build delivery window string
        delivery_window = "TBD"
        if delivery_date_from and delivery_date_to:
            delivery_window = f"{delivery_date_from} to {delivery_date_to}"
        elif delivery_date_from:
            delivery_window = f"From {delivery_date_from}"
        
        # Get unique species/cut/grade combinations from items
        product_lines = {}
        for item in items:
            key = f"{item.common_name}|{item.cut}|{item.grade}"
            if key not in product_lines:
                product_lines[key] = {
                    'species': item.common_name,
                    'cut': item.cut,
                    'grade': item.grade
                }
        
        # Build product summary rows
        product_rows = ""
        for pl in product_lines.values():
            product_rows += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['species']}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['cut']}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['grade']}</td>
                </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 640px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #0A3D5C; color: white; padding: 10px 20px; text-align: center; border-radius: 4px 4px 0 0; }}
                .header h2 {{ margin: 0; font-size: 16px; font-weight: 600; }}
                .content {{ padding: 20px; background-color: #f9fafb; }}
                .footer {{ padding: 12px; text-align: center; font-size: 11px; color: #94a3b8; }}
                .summary {{ background-color: #ffffff; padding: 16px; border-radius: 6px; border: 1px solid #e2e8f0; margin: 16px 0; }}
                .summary-label {{ color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }}
                .summary-value {{ color: #1e293b; font-size: 14px; font-weight: 600; margin-bottom: 12px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th {{ background-color: #f1f5f9; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; padding: 8px 12px; text-align: left; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Estimate #{estimate_number}</h2>
                </div>
                
                <div class="content">
                    <p>Dear {buyer_name},</p>
                    
                    <p>Please find attached your pricing estimate from <strong>Blue Lotus Foods</strong>.</p>
                    
                    <div class="summary">
                        <div class="summary-label">Products</div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Cut</th>
                                    <th>Grade</th>
                                </tr>
                            </thead>
                            <tbody>
                                {product_rows}
                            </tbody>
                        </table>
                        
                        <div style="margin-top: 16px;">
                            <div class="summary-label">Delivery Window</div>
                            <div class="summary-value">{delivery_window}</div>
                        </div>
                    </div>
                    
                    <p><strong>Please refer to the attached PDF for complete pricing details.</strong></p>
                    
                    <p>If you have any questions, please don't hesitate to contact us.</p>
                    
                    <p>Best regards,<br>
                    <strong>Blue Lotus Foods Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>&copy; Blue Lotus Foods LLC. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def send_owner_estimate_notification(
        self,
        owner_email: str,
        company_name: str,
        estimate_number: str,
        items: list,
        delivery_date_from: str = None,
        delivery_date_to: str = None
    ) -> EmailResponse:
        """Send owner notification email when an estimate is sent to a buyer"""
        try:
            # Prepare estimate data for PDF (same PDF as buyer receives)
            estimate_data = {
                'estimate_number': estimate_number,
                'estimate_date': datetime.now().strftime("%Y-%m-%d"),
                'company_name': company_name,
                'buyer_names': company_name,
                'delivery_date_from': delivery_date_from,
                'delivery_date_to': delivery_date_to,
            }

            # Convert items to dict format
            items_dict = [
                {
                    'vendor_name': item.vendor_name,
                    'common_name': item.common_name,
                    'scientific_name': item.scientific_name or '',
                    'cut_name': item.cut,
                    'grade_name': item.grade,
                    'fish_size': item.fish_size,
                    'port_code': item.port,
                    'offer_quantity': item.offer_quantity,
                    'fish_price': item.fish_price,
                    'margin': item.margin,
                    'freight_price': item.freight_price,
                    'tariff_percent': item.tariff_percent,
                    'clearing_charges': item.clearing_charges,
                    'total_price': item.total_price,
                    'fish_species_id': item.fish_species_id,
                    'cut_id': item.cut_id,
                    'grade_id': item.grade_id,
                }
                for item in items
            ]

            if settings.email_simulation_mode:
                logger.warning("Email simulation mode - skipping owner estimate notification SMTP")
                pdf_data = generate_estimate_pdf(estimate_data, items_dict)
                logger.info(f"Generated owner notification PDF for estimate {estimate_number}, size: {len(pdf_data)} bytes")
                return EmailResponse(
                    success=True,
                    message="Owner notification simulation successful",
                    email_id=f"owner_estimate_{estimate_number}_simulation"
                )

            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping owner estimate notification")
                return EmailResponse(
                    success=False,
                    message="Email service not configured (missing SMTP credentials)"
                )

            # Generate same PDF as buyer receives
            pdf_data = generate_estimate_pdf(estimate_data, items_dict)

            # Create email message
            now = datetime.now()
            message = MIMEMultipart()
            message["From"] = f"{settings.from_name} <{settings.from_email}>"
            message["To"] = owner_email
            message["Subject"] = f"Estimate - {company_name} - {estimate_number} - {now.strftime('%m/%d/%Y %I:%M %p')}"

            # Email body
            email_body = self._create_owner_estimate_notification_body(
                company_name, estimate_number, items,
                delivery_date_from, delivery_date_to
            )
            message.attach(MIMEText(email_body, "html"))

            # Attach PDF (same as buyer)
            pdf_attachment = MIMEBase('application', 'octet-stream')
            pdf_attachment.set_payload(pdf_data)
            encoders.encode_base64(pdf_attachment)
            pdf_attachment.add_header(
                'Content-Disposition',
                f'attachment; filename="estimate_{estimate_number}_{company_name.replace(" ", "_")}.pdf"'
            )
            message.attach(pdf_attachment)

            await self._send_email(message)

            logger.info(
                "Owner estimate notification sent successfully",
                estimate_number=estimate_number,
                owner_email=owner_email
            )

            return EmailResponse(
                success=True,
                message="Owner notification sent successfully",
                email_id=f"owner_estimate_{estimate_number}"
            )

        except Exception as e:
            logger.error(
                "Failed to send owner estimate notification",
                error=str(e),
                estimate_number=estimate_number
            )
            return EmailResponse(
                success=False,
                message=f"Failed to send owner notification: {str(e)}"
            )

    def _create_owner_estimate_notification_body(
        self,
        company_name: str,
        estimate_number: str,
        items: list,
        delivery_date_from: str = None,
        delivery_date_to: str = None
    ) -> str:
        """Create HTML email body for owner estimate notification"""

        # Build delivery window string
        delivery_window = "TBD"
        if delivery_date_from and delivery_date_to:
            delivery_window = f"{delivery_date_from} to {delivery_date_to}"
        elif delivery_date_from:
            delivery_window = f"From {delivery_date_from}"

        # Get unique species/cut/grade combinations
        product_lines = {}
        for item in items:
            key = f"{item.common_name}|{item.cut}|{item.grade}"
            if key not in product_lines:
                product_lines[key] = {
                    'species': item.common_name,
                    'cut': item.cut,
                    'grade': item.grade
                }

        product_rows = ""
        for pl in product_lines.values():
            product_rows += f"""
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['species']}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['cut']}</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #e2e8f0;">{pl['grade']}</td>
                </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 640px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #0A3D5C; color: white; padding: 10px 20px; text-align: center; border-radius: 4px 4px 0 0; }}
                .header h2 {{ margin: 0; font-size: 16px; font-weight: 600; }}
                .content {{ padding: 20px; background-color: #f9fafb; }}
                .footer {{ padding: 12px; text-align: center; font-size: 11px; color: #94a3b8; }}
                .summary {{ background-color: #ffffff; padding: 16px; border-radius: 6px; border: 1px solid #e2e8f0; margin: 16px 0; }}
                .summary-label {{ color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }}
                .summary-value {{ color: #1e293b; font-size: 14px; font-weight: 600; margin-bottom: 12px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th {{ background-color: #f1f5f9; color: #475569; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; padding: 8px 12px; text-align: left; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Estimate #{estimate_number}</h2>
                </div>

                <div class="content">
                    <p>New estimate submitted to <strong>{company_name}</strong>.</p>

                    <div class="summary">
                        <div class="summary-label">Products</div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Cut</th>
                                    <th>Grade</th>
                                </tr>
                            </thead>
                            <tbody>
                                {product_rows}
                            </tbody>
                        </table>

                        <div style="margin-top: 16px;">
                            <div class="summary-label">Delivery Window</div>
                            <div class="summary-value">{delivery_window}</div>
                        </div>
                    </div>

                    <p>See attached PDF for complete pricing details.</p>
                </div>

                <div class="footer">
                    <p>&copy; Blue Lotus Foods LLC. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def send_bpl_emails(self, request: SendBPLEmailRequest) -> EmailResponse:
        """
        Send two BPL emails:
        1. Blue Lotus branded PDF → owner
        2. Plain PDF with vendor details → vendor
        """
        try:
            # Build the shared bpl_data dict for PDF generators
            bpl_data = {
                'po_number': request.po_number,
                'port_code': request.port_code,
                'vendor_name': request.vendor_name,
                'vendor_country': request.vendor_country or '',
                'vendor_email': request.vendor_email,
                'invoice_number': request.invoice_number,
                'air_way_bill': request.air_way_bill,
                'packed_date': request.packed_date,
                'expiry_date': request.expiry_date,
                'total_boxes': request.total_boxes,
                'notes': request.notes,
                'items': [
                    {
                        'fish_name': item.fish_name,
                        'cut_name': item.cut_name,
                        'grade_name': item.grade_name,
                        'fish_size': item.fish_size,
                        'order_weight_kg': item.order_weight_kg,
                        'boxes': [
                            {
                                'box_number': box.box_number,
                                'num_pieces': box.num_pieces,
                                'net_weight_kg': box.net_weight_kg,
                                'weight_range_from_kg': box.weight_range_from_kg,
                                'weight_range_to_kg': box.weight_range_to_kg,
                                'pieces': [{'piece_number': p.piece_number, 'weight_kg': p.weight_kg} for p in box.pieces],
                            }
                            for box in item.boxes
                        ]
                    }
                    for item in request.items
                ],
            }

            # Generate both PDFs
            owner_pdf = generate_bpl_owner_pdf(bpl_data)
            vendor_pdf = generate_bpl_vendor_pdf(bpl_data)

            logger.info(f"Generated BPL PDFs: owner={len(owner_pdf)} bytes, vendor={len(vendor_pdf)} bytes")

            if settings.email_simulation_mode:
                logger.warning("Email simulation mode - BPL PDFs generated, SMTP skipped")
                return EmailResponse(
                    success=True,
                    message="BPL email simulation successful - PDFs generated, SMTP skipped",
                    email_id=f"bpl_{request.po_number}_{request.port_code}_simulation"
                )

            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping BPL email send")
                return EmailResponse(success=False, message="Email service not configured (missing SMTP credentials)")

            from datetime import datetime
            import pytz
            central_tz = pytz.timezone('US/Central')
            now_ct = datetime.now(central_tz).strftime('%m/%d/%Y %I:%M %p')

            safe_po = request.po_number.replace(' ', '_')

            # ─── Email 1: Owner (Blue Lotus branded) ───
            owner_msg = MIMEMultipart()
            owner_msg["From"] = f"{settings.from_name} <{settings.from_email}>"
            owner_msg["To"] = request.owner_email
            owner_msg["Subject"] = f"BPL - {request.vendor_name} - {request.po_number} - Port {request.port_code} - {now_ct}"

            owner_body = f"""
            <html><body style="font-family:Arial,sans-serif;color:#1e293b;">
            <h2 style="color:#0A3D5C;">Box Packaging List Received</h2>
            <p>Vendor <b>{request.vendor_name}</b> has submitted a Box Packaging List for:</p>
            <ul>
                <li><b>PO:</b> {request.po_number}</li>
                <li><b>Port:</b> {request.port_code}</li>
                <li><b>Invoice:</b> {request.invoice_number or 'N/A'}</li>
                <li><b>AWB:</b> {request.air_way_bill or 'N/A'}</li>
                <li><b>Total Boxes:</b> {request.total_boxes}</li>
            </ul>
            <p>Please see the attached PDF for full details.</p>
            <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
            <p style="font-size:12px;color:#6b7280;">&copy; Blue Lotus Foods LLC</p>
            </body></html>
            """
            owner_msg.attach(MIMEText(owner_body, "html"))

            owner_att = MIMEBase('application', 'octet-stream')
            owner_att.set_payload(owner_pdf)
            encoders.encode_base64(owner_att)
            owner_att.add_header('Content-Disposition', f'attachment; filename="BPL_{safe_po}_{request.port_code}_BLF.pdf"')
            owner_msg.attach(owner_att)

            await self._send_email(owner_msg)
            logger.info(f"BPL owner email sent to {request.owner_email}")

            # ─── Email 2: Vendor (plain) ───
            vendor_msg = MIMEMultipart()
            vendor_msg["From"] = f"{settings.from_name} <{settings.from_email}>"
            vendor_msg["To"] = request.vendor_email
            vendor_msg["Subject"] = f"BPL Confirmation - {request.po_number} - Port {request.port_code}"

            vendor_body = f"""
            <html><body style="font-family:Arial,sans-serif;color:#1e293b;">
            <h2>Box Packaging List Confirmation</h2>
            <p>Dear {request.vendor_name},</p>
            <p>Your Box Packaging List for <b>{request.po_number}</b> (Port: {request.port_code}) has been submitted successfully.</p>
            <p>Please find the attached PDF for your records.</p>
            <br>
            <p>Thank you,<br>Blue Lotus Foods</p>
            </body></html>
            """
            vendor_msg.attach(MIMEText(vendor_body, "html"))

            vendor_att = MIMEBase('application', 'octet-stream')
            vendor_att.set_payload(vendor_pdf)
            encoders.encode_base64(vendor_att)
            vendor_att.add_header('Content-Disposition', f'attachment; filename="BPL_{safe_po}_{request.port_code}.pdf"')
            vendor_msg.attach(vendor_att)

            await self._send_email(vendor_msg)
            logger.info(f"BPL vendor email sent to {request.vendor_email}")

            return EmailResponse(
                success=True,
                message="BPL emails sent to owner and vendor",
                email_id=f"bpl_{request.po_number}_{request.port_code}"
            )

        except Exception as e:
            logger.error(f"Failed to send BPL emails: {str(e)}", error=str(e))
            return EmailResponse(success=False, message=f"Failed to send BPL emails: {str(e)}")

    async def send_bpl_uploaded_emails(self, request: SendBPLUploadedEmailRequest) -> EmailResponse:
        """
        Send BPL emails with vendor's uploaded document as attachment.
        Sent to both owner and vendor. No PDF generation — raw file attached.
        """
        try:
            file_bytes = base64.b64decode(request.attachment_bytes)
            logger.info(f"Decoded uploaded BPL file: {request.attachment_filename} ({len(file_bytes)} bytes)")

            if settings.email_simulation_mode:
                logger.warning("Email simulation mode - uploaded BPL email skipped")
                return EmailResponse(
                    success=True,
                    message="Uploaded BPL email simulation successful - SMTP skipped",
                    email_id=f"bpl_upload_{request.po_number}_{request.port_code}_simulation"
                )

            if not settings.smtp_username or not settings.smtp_password or not settings.from_email:
                logger.warning("SMTP not configured, skipping uploaded BPL email send")
                return EmailResponse(success=False, message="Email service not configured (missing SMTP credentials)")

            from datetime import datetime
            import pytz
            central_tz = pytz.timezone('US/Central')
            now_ct = datetime.now(central_tz).strftime('%m/%d/%Y %I:%M %p')

            safe_po = request.po_number.replace(' ', '_')

            # Determine MIME type from filename extension
            fname_lower = request.attachment_filename.lower()
            if fname_lower.endswith('.pdf'):
                mime_type = 'application/pdf'
            elif fname_lower.endswith('.xlsx') or fname_lower.endswith('.xls'):
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                mime_type = 'application/octet-stream'

            def _build_att(filename: str) -> MIMEBase:
                att = MIMEBase('application', 'octet-stream')
                att.set_payload(file_bytes)
                encoders.encode_base64(att)
                att.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                att.add_header('Content-Type', mime_type)
                return att

            # ─── Email 1: Owner ───
            owner_msg = MIMEMultipart()
            owner_msg["From"] = f"{settings.from_name} <{settings.from_email}>"
            owner_msg["To"] = request.owner_email
            owner_msg["Subject"] = f"BPL (Uploaded) - {request.vendor_name} - {request.po_number} - Port {request.port_code} - {now_ct}"

            owner_body = f"""
            <html><body style="font-family:Arial,sans-serif;color:#1e293b;">
            <h2 style="color:#0A3D5C;">Box Packaging List Received (Uploaded Document)</h2>
            <p>Vendor <b>{request.vendor_name}</b> has submitted a Box Packaging List document for:</p>
            <ul>
                <li><b>PO:</b> {request.po_number}</li>
                <li><b>Port:</b> {request.port_code}</li>
                <li><b>Invoice:</b> {request.invoice_number or 'N/A'}</li>
                <li><b>AWB:</b> {request.air_way_bill or 'N/A'}</li>
            </ul>
            <p>The vendor's uploaded document is attached.</p>
            <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0;">
            <p style="font-size:12px;color:#6b7280;">&copy; Blue Lotus Foods LLC</p>
            </body></html>
            """
            owner_msg.attach(MIMEText(owner_body, "html"))
            owner_msg.attach(_build_att(f"BPL_{safe_po}_{request.port_code}_{request.attachment_filename}"))

            await self._send_email(owner_msg)
            logger.info(f"Uploaded BPL owner email sent to {request.owner_email}")

            # ─── Email 2: Vendor ───
            vendor_msg = MIMEMultipart()
            vendor_msg["From"] = f"{settings.from_name} <{settings.from_email}>"
            vendor_msg["To"] = request.vendor_email
            vendor_msg["Subject"] = f"BPL Confirmation - {request.po_number} - Port {request.port_code}"

            vendor_body = f"""
            <html><body style="font-family:Arial,sans-serif;color:#1e293b;">
            <h2>Box Packaging List Confirmation</h2>
            <p>Dear {request.vendor_name},</p>
            <p>Your Box Packaging List document for <b>{request.po_number}</b> (Port: {request.port_code}) has been submitted successfully.</p>
            <p>Your uploaded document is attached for your records.</p>
            <br>
            <p>Thank you,<br>Blue Lotus Foods</p>
            </body></html>
            """
            vendor_msg.attach(MIMEText(vendor_body, "html"))
            vendor_msg.attach(_build_att(request.attachment_filename))

            await self._send_email(vendor_msg)
            logger.info(f"Uploaded BPL vendor email sent to {request.vendor_email}")

            return EmailResponse(
                success=True,
                message="Uploaded BPL emails sent to owner and vendor",
                email_id=f"bpl_upload_{request.po_number}_{request.port_code}"
            )

        except Exception as e:
            logger.error(f"Failed to send uploaded BPL emails: {str(e)}", error=str(e))
            return EmailResponse(success=False, message=f"Failed to send uploaded BPL emails: {str(e)}")
