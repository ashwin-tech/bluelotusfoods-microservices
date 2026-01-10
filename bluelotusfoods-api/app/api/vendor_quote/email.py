from fastapi import APIRouter, HTTPException, status
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
import httpx
import logging
from decimal import Decimal
from datetime import date, datetime
from app.core.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{quote_id}/debug")
async def debug_quote_info(quote_id: int):
    """Comprehensive debug endpoint for quote, vendor, and email data analysis"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get comprehensive quote and vendor info for email
            cur.execute(DatabaseQueries.EMAIL['get_vendor_quote'], (quote_id,))
            email_quote_row = cur.fetchone()
            
            # Get additional debug info with all quote fields
            cur.execute(DatabaseQueries.QUOTES['debug_with_vendor'], (quote_id,))
            debug_quote_row = cur.fetchone()
            
            if not email_quote_row and not debug_quote_row:
                return {"error": "Quote not found", "quote_id": quote_id}
            
            # Get related data
            cur.execute(DatabaseQueries.QUOTES['get_destinations'], (quote_id,))
            destinations = cur.fetchall()
            
            cur.execute(DatabaseQueries.QUOTES['get_products'], (quote_id,))
            products = cur.fetchall()
            
            return {
                "quote_id": quote_id,
                "email_ready_data": dict(email_quote_row) if email_quote_row else None,
                "full_quote_data": dict(debug_quote_row) if debug_quote_row else None,
                "destinations": [dict(dest) for dest in destinations],
                "products": [dict(prod) for prod in products],
                "email_enabled": email_quote_row.get('is_email_enabled', False) if email_quote_row else False,
                "vendor_email": email_quote_row.get('contact_email') if email_quote_row else None,
                "data_keys": {
                    "email_data_keys": list(email_quote_row.keys()) if email_quote_row else [],
                    "debug_data_keys": list(debug_quote_row.keys()) if debug_quote_row else []
                }
            }
    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "quote_id": quote_id,
            "traceback": traceback.format_exc()
        }
    finally:
        release_connection(conn)


@router.post("/{quote_id}/email")
async def send_vendor_email(quote_id: int):
    """Send email confirmation to vendor for their quote submission"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get vendor quote information for email
            vendor_query = DatabaseQueries.EMAIL['get_vendor_quote']
            
            # Get quote details with vendor information
            cur.execute(vendor_query, (quote_id,))
            quote_row = cur.fetchone()
            
            if not quote_row:
                raise HTTPException(status_code=404, detail="Quote not found")
            

            
            # Check if email is enabled for this vendor
            if not quote_row.get('is_email_enabled', False):
                return {
                    "success": False,
                    "message": "Email notifications disabled for this vendor",
                    "quote_id": quote_id
                }
            
            if not quote_row.get('contact_email'):
                raise HTTPException(
                    status_code=400, 
                    detail="No email address found for this vendor"
                )
            
            # Get quote destinations from quote_destination table
            cur.execute(DatabaseQueries.QUOTES['get_destinations'], (quote_id,))
            destinations = cur.fetchall()
            
            # Get quote products from quote_product table
            cur.execute(DatabaseQueries.QUOTES['get_products'], (quote_id,))
            sizes = cur.fetchall()

            
            # Convert non-JSON serializable objects for JSON serialization
            def convert_for_json(obj):
                """Convert Decimal, date, and datetime objects for JSON serialization"""
                if isinstance(obj, dict):
                    return {key: convert_for_json(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_for_json(item) for item in obj]
                elif isinstance(obj, Decimal):
                    return float(obj) if obj is not None else 0.0
                elif isinstance(obj, date):
                    return obj.isoformat()  # Convert date to string like "2024-03-15"
                elif isinstance(obj, datetime):
                    return obj.isoformat()  # Convert datetime to string like "2024-03-15T10:30:00"
                else:
                    return obj
            
            # Prepare data for email service
            quote_data = {
                "quote_id": quote_row['quote_id'],
                "vendor_name": quote_row['vendor_name'],
                "vendor_code": quote_row.get('vendor_code', 'N/A'),
                "country_of_origin": quote_row['country_of_origin'],
                "quote_valid_till": f"{quote_row['quote_valid_till']}T00:00:00" if quote_row['quote_valid_till'] else None,
                "fish_type": quote_row['fish_type'],
                "destinations": convert_for_json([dict(dest) for dest in destinations]),
                "sizes": convert_for_json([dict(size) for size in sizes]),
                "notes": quote_row.get('notes'),
                "price_negotiable": quote_row.get('price_negotiable', False),
                "exclusive_offer": quote_row.get('exclusive_offer', False),
                "created_at": quote_row['created_at'].isoformat() if quote_row['created_at'] else None
            }
            
            # Call email service - send to vendor's email
            vendor_email = quote_row['contact_email']
            email_payload = {
                "quote_id": quote_id,
                "vendor_email": vendor_email,
                "vendor_name": quote_row['vendor_name'],
                "quote_data": convert_for_json(quote_data)
            }
            
            logger.info(f"🚀 Calling email service with payload keys: {list(email_payload.keys())}")
            logger.info(f"📧 Sending to vendor email: {vendor_email}, Vendor name: {quote_row['vendor_name']}")
            logger.info(f"🌐 Email service URL: {settings.email_service_url}/email/vendor-notification")
            logger.info(f"📦 Quote data keys: {list(quote_data.keys())}")
            
            async with httpx.AsyncClient() as client:
                logger.info(f"⏳ Sending request to email service...")
                response = await client.post(
                    f"{settings.email_service_url}/email/vendor-notification",
                    json=email_payload,
                    timeout=30.0
                )
                logger.info(f"📡 Email service response status: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"❌ Email service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Email service error: {response.text}"
                    )
                
                email_result = response.json()
                logger.info(f"✅ Email service success response: {email_result}")
                
                # Log the email sending attempt if email_log table exists
                cur.execute(DatabaseQueries.SCHEMA['check_email_log'])
                has_email_log_table = cur.fetchone()
                
                if has_email_log_table:
                    cur.execute(
                        DatabaseQueries.EMAIL['insert_log'],
                        (quote_id, vendor_email, 'sent' if email_result['success'] else 'failed')
                    )
                    conn.commit()
                
                return {
                    "success": email_result['success'],
                    "message": email_result['message'],
                    "quote_id": quote_id,
                    "vendor_email": vendor_email
                }
                
    except httpx.RequestError as e:
        logger.error(f"Email service connection error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Email service unavailable"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Quote email error for quote_id {quote_id}: {str(e)}")
        logger.error(f"Full traceback: {error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}"
        )
    finally:
        release_connection(conn)


@router.post("/{quote_id}/owner-notification")
async def send_owner_notification(quote_id: int):
    """Send owner notification email when a vendor submits a quote"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get vendor quote information for email
            vendor_query = DatabaseQueries.EMAIL['get_vendor_quote']
            
            # Get quote details with vendor information
            cur.execute(vendor_query, (quote_id,))
            quote_row = cur.fetchone()
            
            if not quote_row:
                raise HTTPException(status_code=404, detail="Quote not found")
            
            # Get quote destinations from quote_destination table
            cur.execute(DatabaseQueries.QUOTES['get_destinations'], (quote_id,))
            destinations = cur.fetchall()
            
            # Get quote products from quote_product table
            cur.execute(DatabaseQueries.QUOTES['get_products'], (quote_id,))
            sizes = cur.fetchall()
            
            # Convert non-JSON serializable objects for JSON serialization
            def convert_for_json(obj):
                """Convert Decimal, date, and datetime objects for JSON serialization"""
                if isinstance(obj, dict):
                    return {key: convert_for_json(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_for_json(item) for item in obj]
                elif isinstance(obj, Decimal):
                    return float(obj) if obj is not None else 0.0
                elif isinstance(obj, date):
                    return obj.isoformat()
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                else:
                    return obj
            
            # Prepare data for email service
            quote_data = {
                "quote_id": quote_row['quote_id'],
                "vendor_name": quote_row['vendor_name'],
                "vendor_code": quote_row.get('vendor_code', 'N/A'),
                "country_of_origin": quote_row['country_of_origin'],
                "quote_valid_till": f"{quote_row['quote_valid_till']}T00:00:00" if quote_row['quote_valid_till'] else None,
                "fish_type": quote_row['fish_type'],
                "destinations": convert_for_json([dict(dest) for dest in destinations]),
                "sizes": convert_for_json([dict(size) for size in sizes]),
                "notes": quote_row.get('notes'),
                "price_negotiable": quote_row.get('price_negotiable', False),
                "exclusive_offer": quote_row.get('exclusive_offer', False),
                "created_at": quote_row['created_at'].isoformat() if quote_row['created_at'] else None
            }
            
            # Call email service for owner notification
            owner_email = settings.quote_notification_email
            email_payload = {
                "quote_id": quote_id,
                "owner_email": owner_email,
                "vendor_name": quote_row['vendor_name'],
                "quote_data": convert_for_json(quote_data)
            }
            
            logger.info(f"🚀 Calling email service for owner notification with payload keys: {list(email_payload.keys())}")
            logger.info(f"📧 Owner email: {owner_email}, Vendor name: {quote_row['vendor_name']}")
            logger.info(f"🌐 Email service URL: {settings.email_service_url}/email/owner-notification")
            
            async with httpx.AsyncClient() as client:
                logger.info(f"⏳ Sending owner notification request to email service...")
                response = await client.post(
                    f"{settings.email_service_url}/email/owner-notification",
                    json=email_payload,
                    timeout=30.0
                )
                logger.info(f"📡 Email service response status: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"❌ Email service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Email service error: {response.text}"
                    )
                
                email_result = response.json()
                logger.info(f"✅ Email service success response: {email_result}")
                
                return {
                    "success": email_result['success'],
                    "message": email_result['message'],
                    "quote_id": quote_id,
                    "owner_email": owner_email
                }
                
    except httpx.RequestError as e:
        logger.error(f"Email service connection error: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Email service unavailable"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Owner notification error for quote_id {quote_id}: {str(e)}")
        logger.error(f"Full traceback: {error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send owner notification: {str(e)}"
        )
    finally:
        release_connection(conn)
