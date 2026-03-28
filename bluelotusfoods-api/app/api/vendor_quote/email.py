from fastapi import APIRouter, HTTPException, status
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
import httpx
import logging
from decimal import Decimal
from datetime import date, datetime
from app.core.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _convert_for_json(obj):
    """Convert Decimal, date, and datetime objects for JSON serialization."""
    if isinstance(obj, dict):
        return {key: _convert_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_for_json(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj) if obj is not None else 0.0
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


@router.get("/{quote_id}/debug")
async def debug_quote_info(quote_id: int):
    """Comprehensive debug endpoint for quote, vendor, and email data analysis"""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.EMAIL['get_vendor_quote'], (quote_id,))
                email_quote_row = cur.fetchone()

                cur.execute(DatabaseQueries.QUOTES['debug_with_vendor'], (quote_id,))
                debug_quote_row = cur.fetchone()

                if not email_quote_row and not debug_quote_row:
                    return {"error": "Quote not found", "quote_id": quote_id}

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


@router.post("/{quote_id}/email")
async def send_vendor_email(quote_id: int):
    """Send email confirmation to vendor for their quote submission"""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.EMAIL['get_vendor_quote'], (quote_id,))
                quote_row = cur.fetchone()

                if not quote_row:
                    raise HTTPException(status_code=404, detail="Quote not found")

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

                cur.execute(DatabaseQueries.QUOTES['get_destinations'], (quote_id,))
                destinations = cur.fetchall()

                cur.execute(DatabaseQueries.QUOTES['get_products'], (quote_id,))
                sizes = cur.fetchall()

                quote_data = {
                    "quote_id": quote_row['quote_id'],
                    "vendor_name": quote_row['vendor_name'],
                    "vendor_code": quote_row.get('vendor_code', 'N/A'),
                    "country_of_origin": quote_row['country_of_origin'],
                    "quote_valid_till": f"{quote_row['quote_valid_till']}T00:00:00" if quote_row['quote_valid_till'] else None,
                    "fish_type": quote_row['fish_type'],
                    "destinations": _convert_for_json([dict(dest) for dest in destinations]),
                    "sizes": _convert_for_json([dict(size) for size in sizes]),
                    "notes": quote_row.get('notes'),
                    "price_negotiable": quote_row.get('price_negotiable', False),
                    "exclusive_offer": quote_row.get('exclusive_offer', False),
                    "created_at": quote_row['created_at'].isoformat() if quote_row['created_at'] else None
                }

                vendor_email = quote_row['contact_email']
                email_payload = {
                    "quote_id": quote_id,
                    "vendor_email": vendor_email,
                    "vendor_name": quote_row['vendor_name'],
                    "quote_data": _convert_for_json(quote_data)
                }

                logger.info(f"Calling email service for quote {quote_id}, vendor: {quote_row['vendor_name']}")

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.email_service_url}/email/vendor-notification",
                        json=email_payload,
                        timeout=30.0
                    )

                    if response.status_code != 200:
                        logger.error(f"Email service error: {response.status_code} - {response.text}")
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Email service error: {response.text}"
                        )

                    email_result = response.json()
                    logger.info(f"Email service success: {email_result}")

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
            raise HTTPException(status_code=503, detail="Email service unavailable")
        except Exception as e:
            import traceback
            logger.error(f"Quote email error for quote_id {quote_id}: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


@router.post("/{quote_id}/owner-notification")
async def send_owner_notification(quote_id: int):
    """Send owner notification email when a vendor submits a quote"""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.EMAIL['get_vendor_quote'], (quote_id,))
                quote_row = cur.fetchone()

                if not quote_row:
                    raise HTTPException(status_code=404, detail="Quote not found")

                cur.execute(DatabaseQueries.QUOTES['get_destinations'], (quote_id,))
                destinations = cur.fetchall()

                cur.execute(DatabaseQueries.QUOTES['get_products'], (quote_id,))
                sizes = cur.fetchall()

                quote_data = {
                    "quote_id": quote_row['quote_id'],
                    "vendor_name": quote_row['vendor_name'],
                    "vendor_code": quote_row.get('vendor_code', 'N/A'),
                    "country_of_origin": quote_row['country_of_origin'],
                    "quote_valid_till": f"{quote_row['quote_valid_till']}T00:00:00" if quote_row['quote_valid_till'] else None,
                    "fish_type": quote_row['fish_type'],
                    "destinations": _convert_for_json([dict(dest) for dest in destinations]),
                    "sizes": _convert_for_json([dict(size) for size in sizes]),
                    "notes": quote_row.get('notes'),
                    "price_negotiable": quote_row.get('price_negotiable', False),
                    "exclusive_offer": quote_row.get('exclusive_offer', False),
                    "created_at": quote_row['created_at'].isoformat() if quote_row['created_at'] else None
                }

                owner_email = settings.owner_notification_email
                email_payload = {
                    "quote_id": quote_id,
                    "owner_email": owner_email,
                    "vendor_name": quote_row['vendor_name'],
                    "quote_data": _convert_for_json(quote_data)
                }

                logger.info(f"Sending owner notification for quote {quote_id}, vendor: {quote_row['vendor_name']}")

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{settings.email_service_url}/email/owner-notification",
                        json=email_payload,
                        timeout=30.0
                    )

                    if response.status_code != 200:
                        logger.error(f"Email service error: {response.status_code} - {response.text}")
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Email service error: {response.text}"
                        )

                    email_result = response.json()
                    return {
                        "success": email_result['success'],
                        "message": email_result['message'],
                        "quote_id": quote_id,
                        "owner_email": owner_email
                    }

        except httpx.RequestError as e:
            logger.error(f"Email service connection error: {str(e)}")
            raise HTTPException(status_code=503, detail="Email service unavailable")
        except Exception as e:
            import traceback
            logger.error(f"Owner notification error for quote_id {quote_id}: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to send owner notification: {str(e)}")
