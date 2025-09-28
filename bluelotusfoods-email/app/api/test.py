from fastapi import APIRouter
from app.schemas.email import VendorQuoteData, EmailResponse
from app.services.email_service import EmailService
import structlog

logger = structlog.get_logger()
router = APIRouter()
email_service = EmailService()


@router.post("/test-email")
async def test_email():
    """Simple test of email service with minimal data"""
    try:
        # Create minimal test data
        quote_data = VendorQuoteData(
            quote_id=1,
            vendor_name="Test Vendor",
            vendor_code="TEST",
            country_of_origin="USA",
            quote_valid_till="2025-09-21T00:00:00",  # Full datetime string
            fish_type="Test Fish",
            destinations=[],
            sizes=[],
            notes="Test notes",
            price_negotiable=False,
            exclusive_offer=False,
            created_at="2025-09-21T10:00:00"
        )
        
        # Call email service
        result = await email_service.send_vendor_quote_email(
            vendor_email="test@example.com",
            vendor_name="Test Vendor",
            quote_data=quote_data
        )
        
        # Return the result directly without raising exceptions
        return {
            "success": result.success,
            "message": result.message,
            "email_id": result.email_id
        }
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }