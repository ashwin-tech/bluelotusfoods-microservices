from fastapi import APIRouter, HTTPException, status
from app.schemas.email import VendorQuoteEmailRequest, EmailResponse, VendorQuoteData
from app.services.email_service import EmailService
import structlog

logger = structlog.get_logger()
router = APIRouter()
email_service = EmailService()


@router.post("/vendor-quote", response_model=EmailResponse)
async def send_vendor_quote_email(request: VendorQuoteEmailRequest):
    """Send vendor quote confirmation email with PDF attachment"""
    try:
        logger.info(f"Received email request for quote {request.quote_id}")
        logger.info(f"Quote data keys: {list(request.quote_data.keys())}")
        
        # Convert quote_data dict to VendorQuoteData model
        quote_data = VendorQuoteData(**request.quote_data)
        
        # Send email
        result = await email_service.send_vendor_quote_email(
            vendor_email=request.vendor_email,
            vendor_name=request.vendor_name,
            quote_data=quote_data
        )
        
        logger.info(f"Email service result: success={result.success}, message={result.message}")
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )
        
        return result
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Email API error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)} | Traceback: {error_details[:500]}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "bluelotusfoods-email"}