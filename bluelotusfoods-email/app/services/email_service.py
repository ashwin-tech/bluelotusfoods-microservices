import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
import aiosmtplib
from app.core.settings import settings
from app.schemas.email import VendorQuoteData, EmailResponse
from app.services.pdf_generator import PDFGenerator
import structlog

logger = structlog.get_logger()


class EmailService:
    def __init__(self):
        self.pdf_generator = PDFGenerator()
    
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
                pdf_data = self.pdf_generator.generate_vendor_quote_pdf(quote_data)
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
            pdf_data = self.pdf_generator.generate_vendor_quote_pdf(quote_data)
            
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