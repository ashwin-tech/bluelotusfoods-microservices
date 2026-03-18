from fastapi import APIRouter, HTTPException, status
from app.schemas.email import VendorQuoteEmailRequest, OwnerNotificationEmailRequest, EmailResponse, VendorQuoteData, BuyerPricingEmailRequest, OwnerEstimateNotificationRequest, SendBPLEmailRequest, SendBPLUploadedEmailRequest
from app.services.email_service import EmailService
import structlog

logger = structlog.get_logger()
router = APIRouter()
email_service = EmailService()


@router.post("/vendor-notification", response_model=EmailResponse)
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


@router.post("/owner-notification", response_model=EmailResponse)
async def send_owner_notification_email(request: OwnerNotificationEmailRequest):
    """Send owner notification email when a vendor submits a quote"""
    try:
        logger.info(f"Received owner notification request for quote {request.quote_id}")
        logger.info(f"Quote data keys: {list(request.quote_data.keys())}")
        
        # Convert quote_data dict to VendorQuoteData model
        quote_data = VendorQuoteData(**request.quote_data)
        
        # Send email
        result = await email_service.send_owner_notification_email(
            owner_email=request.owner_email,
            vendor_name=request.vendor_name,
            quote_data=quote_data
        )
        
        logger.info(f"Owner notification result: success={result.success}, message={result.message}")
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )
        
        return result
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Owner notification email API error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send owner notification: {str(e)} | Traceback: {error_details[:500]}"
        )

@router.post("/buyer-pricing/send-estimate", response_model=EmailResponse)
async def send_buyer_pricing_email(request: BuyerPricingEmailRequest):
    """Send buyer pricing estimate email with PDF attachment"""
    try:
        logger.info(f"Received buyer pricing email request for estimate {request.estimate_number}")
        logger.info(f"Sending to emails: {request.buyer_emails}")
        
        # Send email
        result = await email_service.send_buyer_pricing_email(
            buyer_emails=request.buyer_emails,
            buyer_name=request.buyer_name,
            company_name=request.company_name,
            estimate_number=request.estimate_number,
            items=request.items,
            delivery_date_from=request.delivery_date_from,
            delivery_date_to=request.delivery_date_to,
            notes=request.notes
        )
        
        logger.info(f"Buyer pricing email result: success={result.success}, message={result.message}")
        
        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )
        
        return result
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Buyer pricing email API error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send buyer pricing email: {str(e)} | Traceback: {error_details[:500]}"
        )


@router.post("/buyer-pricing/send-owner-notification", response_model=EmailResponse)
async def send_owner_estimate_notification(request: OwnerEstimateNotificationRequest):
    """Send owner notification email when an estimate is sent to a buyer"""
    try:
        logger.info(f"Received owner estimate notification for estimate {request.estimate_number}")

        result = await email_service.send_owner_estimate_notification(
            owner_email=request.owner_email,
            company_name=request.company_name,
            estimate_number=request.estimate_number,
            items=request.items,
            delivery_date_from=request.delivery_date_from,
            delivery_date_to=request.delivery_date_to
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

        return result

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Owner estimate notification error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send owner estimate notification: {str(e)} | Traceback: {error_details[:500]}"
        )


@router.post("/bpl/send-emails", response_model=EmailResponse)
async def send_bpl_emails(request: SendBPLEmailRequest):
    """Send BPL emails - branded PDF to owner, plain PDF to vendor"""
    try:
        logger.info(f"Received BPL email request for PO {request.po_number}, port {request.port_code}")
        logger.info(f"Vendor: {request.vendor_name}, items count: {len(request.items)}")

        result = await email_service.send_bpl_emails(request)

        logger.info(f"BPL email result: success={result.success}, message={result.message}")

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

        return result

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("BPL email API error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send BPL emails: {str(e)} | Traceback: {error_details[:500]}"
        )


@router.post("/bpl/send-uploaded", response_model=EmailResponse)
async def send_bpl_uploaded_email(request: SendBPLUploadedEmailRequest):
    """Send BPL emails with the vendor's uploaded document as the attachment."""
    try:
        logger.info(f"Received uploaded BPL email request for PO {request.po_number}, port {request.port_code}")
        logger.info(f"Vendor: {request.vendor_name}, file: {request.attachment_filename}")

        result = await email_service.send_bpl_uploaded_emails(request)

        logger.info(f"Uploaded BPL email result: success={result.success}, message={result.message}")

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

        return result

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Uploaded BPL email API error", error=str(e), traceback=error_details)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send uploaded BPL email: {str(e)} | Traceback: {error_details[:500]}"
        )
