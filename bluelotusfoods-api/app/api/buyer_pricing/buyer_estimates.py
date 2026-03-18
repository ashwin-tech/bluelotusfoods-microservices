from fastapi import APIRouter, Body, HTTPException
from app.db.db import get_connection, release_connection
from app.services.pricing_calculations import calculate_estimate_totals
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import date
import logging
import httpx
import os
from app.core.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class EstimateItemToSave(BaseModel):
    """
    All prices are in LBS (pounds) for buyer pricing.
    Vendor quotes are in KG but converted to LBS on the frontend before saving.
    """
    vendor_id: int
    quote_id: Optional[int] = None  # Original vendor quote ID for PO traceability
    port_code: str
    fish_species_id: int
    cut_id: int
    grade_id: int
    fish_size: Optional[str] = None  # Weight range from vendor quote
    fish_price: Decimal  # Per LB
    freight_price: Decimal  # Per LB
    tariff_percent: Decimal
    margin: Decimal  # Per LB
    clearing_charges: Decimal = Decimal('0.00')  # Per LB
    offer_quantity: Optional[Decimal] = None  # In LBS


class SaveBuyerEstimateRequest(BaseModel):
    company_id: int
    buyer_id: int
    buyer_ids: Optional[str] = None  # Comma-separated buyer IDs
    items: List[EstimateItemToSave]
    notes: Optional[str] = None
    delivery_date_from: Optional[date] = None
    delivery_date_to: Optional[date] = None
    region_groups: Optional[List[dict]] = None  # [{"region_name": "Asia", "port_codes": ["LAX", "SEA"]}]


class SendEstimateRequest(BaseModel):
    notify_buyer: bool = True


class BuyerEstimateResponse(BaseModel):
    id: int
    estimate_number: str
    buyer_ids: str
    company_id: int
    estimate_date: str
    delivery_date_from: Optional[str]
    delivery_date_to: Optional[str]
    status: str
    notes: Optional[str]
    item_count: int
    created_at: str


@router.post("/save")
async def save_buyer_estimate(request: SaveBuyerEstimateRequest):
    """
    Save a new buyer estimate with selected quote items.
    Generates unique estimate number and stores all selected items.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Start transaction
            cur.execute("BEGIN")
            
            from datetime import datetime
            now = datetime.now()
            
            # Step 1: INSERT with placeholder — let PostgreSQL assign the id via SERIAL.
            # Step 2: Use the RETURNING id to build EST-YYYY-MM-<id>, then UPDATE.
            # This is concurrency-safe (unlike SELECT MAX(id)+1 which has race conditions).
            cur.execute("""
                INSERT INTO buyer_estimate (
                    estimate_number,
                    company_id,
                    buyer_ids,
                    notes,
                    delivery_date_from,
                    delivery_date_to,
                    status
                ) VALUES (
                    'PENDING', %s, %s, %s, %s, %s, 'draft'
                )
                RETURNING id, estimate_date, delivery_date_from, delivery_date_to, created_at
            """, (
                request.company_id,
                request.buyer_ids or str(request.buyer_id),
                request.notes,
                request.delivery_date_from,
                request.delivery_date_to
            ))
            
            result = cur.fetchone()
            estimate_id = result['id']
            estimate_date = result['estimate_date']
            created_at = result['created_at']
            
            # Generate estimate_number: EST-YYYY-MM-<id>
            estimate_number = f"EST-{now.year}-{now.month:02d}-{estimate_id}"
            cur.execute(
                "UPDATE buyer_estimate SET estimate_number = %s WHERE id = %s",
                (estimate_number, estimate_id)
            )
            
            # Insert estimate items
            for item in request.items:
                # Calculate price and totals using pricing service
                calc_data = calculate_estimate_totals({
                    'fish_price': float(item.fish_price),
                    'freight_price': float(item.freight_price),
                    'tariff_percent': float(item.tariff_percent),
                    'margin': float(item.margin)
                })
                
                # price = (fish_price + tariff_amount) + freight_price + margin
                price = Decimal(str(calc_data['total_price']))
                
                # total_price = price + clearing_charges
                total_price = price + item.clearing_charges
                
                cur.execute("""
                    INSERT INTO buyer_estimate_item (
                        buyer_estimate_id,
                        vendor_id,
                        quote_id,
                        port_code,
                        fish_species_id,
                        cut_id,
                        grade_id,
                        fish_size,
                        fish_price,
                        freight_price,
                        tariff_percent,
                        tariff_amount,
                        margin,
                        price,
                        clearing_charges,
                        offer_quantity,
                        total_price
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    estimate_id,
                    item.vendor_id,
                    item.quote_id,
                    item.port_code,
                    item.fish_species_id,
                    item.cut_id,
                    item.grade_id,
                    item.fish_size,
                    item.fish_price,
                    item.freight_price,
                    item.tariff_percent,
                    calc_data['tariff_amount'],
                    item.margin,
                    price,
                    item.clearing_charges,
                    item.offer_quantity,
                    total_price
                ))
            
            # Insert region groups if provided
            if request.region_groups:
                for region in request.region_groups:
                    cur.execute("""
                        INSERT INTO buyer_estimate_region_group (
                            buyer_estimate_id,
                            region_name,
                            port_codes,
                            notes
                        ) VALUES (
                            %s, %s, %s, %s
                        )
                    """, (
                        estimate_id,
                        region['region_name'],
                        region.get('port_codes', []),
                        region.get('notes')
                    ))
            
            conn.commit()
            
            # Fetch the saved items with all details for email
            cur.execute("""
                SELECT 
                    bei.*,
                    v.name as vendor_name,
                    fs.common_name,
                    fs.scientific_name,
                    fc.name as cut,
                    fg.name as grade,
                    bei.port_code as port
                FROM buyer_estimate_item bei
                JOIN vendors v ON bei.vendor_id = v.id
                JOIN fish_species fs ON bei.fish_species_id = fs.id
                JOIN fish_cut fc ON bei.cut_id = fc.id
                JOIN fish_grade fg ON bei.grade_id = fg.id
                WHERE bei.buyer_estimate_id = %s
                ORDER BY v.name, fs.common_name
            """, (estimate_id,))
            
            saved_items = cur.fetchall()
            
            return {
                "success": True,
                "message": "Buyer estimate saved successfully",
                "estimate_number": estimate_number,
                "estimate": {
                    "id": estimate_id,
                    "estimate_number": estimate_number,
                    "buyer_ids": request.buyer_ids or str(request.buyer_id),
                    "company_id": request.company_id,
                    "estimate_date": estimate_date.isoformat(),
                    "delivery_date_from": result['delivery_date_from'].isoformat() if result.get('delivery_date_from') else None,
                    "delivery_date_to": result['delivery_date_to'].isoformat() if result.get('delivery_date_to') else None,
                    "status": "draft",
                    "item_count": len(request.items),
                    "created_at": created_at.isoformat()
                },
                "items": [dict(item) for item in saved_items]
            }
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving buyer estimate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving estimate: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/buyer/{buyer_id}")
async def get_buyer_estimates(buyer_id: int, limit: int = 50):
    """Get all estimates for a specific buyer"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    be.id,
                    be.estimate_number,
                    be.buyer_ids,
                    be.company_id,
                    be.estimate_date,
                    be.delivery_date_from,
                    be.delivery_date_to,
                    be.status,
                    be.notes,
                    be.created_at,
                    be.updated_at,
                    c.name as company_name,
                    COUNT(bei.id) as item_count,
                    (
                        SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
                        FROM buyers
                        WHERE buyers.id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                        )
                    ) as buyer_names
                FROM buyer_estimate be
                JOIN company c ON be.company_id = c.id
                LEFT JOIN buyer_estimate_item bei ON be.id = bei.buyer_estimate_id
                WHERE %s = ANY(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                GROUP BY be.id, c.name
                ORDER BY be.created_at DESC
                LIMIT %s
            """, (buyer_id, limit))
            
            results = cur.fetchall()
            
            return {
                "success": True,
                "estimates": [dict(row) for row in results]
            }
            
    except Exception as e:
        logger.error(f"Error fetching buyer estimates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching estimates: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/{estimate_id}")
async def get_estimate_details(estimate_id: int):
    """Get full details of a specific estimate including all items"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get estimate header
            cur.execute("""
                SELECT 
                    be.*,
                    c.name as company_name,
                    (
                        SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
                        FROM buyers
                        WHERE buyers.id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                        )
                    ) as buyer_names,
                    (
                        SELECT STRING_AGG(buyers.email, ', ' ORDER BY buyers.name)
                        FROM buyers
                        WHERE buyers.id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                        )
                    ) as buyer_emails
                FROM buyer_estimate be
                JOIN company c ON be.company_id = c.id
                WHERE be.id = %s
            """, (estimate_id,))
            
            estimate = cur.fetchone()
            if not estimate:
                raise HTTPException(status_code=404, detail="Estimate not found")
            
            # Get estimate items
            cur.execute("""
                SELECT 
                    bei.*,
                    v.name as vendor_name,
                    fs.common_name,
                    fs.scientific_name,
                    fc.name as cut_name,
                    fg.name as grade_name
                FROM buyer_estimate_item bei
                JOIN vendors v ON bei.vendor_id = v.id
                JOIN fish_species fs ON bei.fish_species_id = fs.id
                JOIN fish_cut fc ON bei.cut_id = fc.id
                JOIN fish_grade fg ON bei.grade_id = fg.id
                WHERE bei.buyer_estimate_id = %s
                ORDER BY v.name, fs.common_name
            """, (estimate_id,))
            
            items = cur.fetchall()
            
            # Get region groups if any
            cur.execute("""
                SELECT *
                FROM buyer_estimate_region_group
                WHERE buyer_estimate_id = %s
                ORDER BY region_name
            """, (estimate_id,))
            
            region_groups = cur.fetchall()
            
            return {
                "success": True,
                "estimate": dict(estimate),
                "items": [dict(item) for item in items],
                "region_groups": [dict(rg) for rg in region_groups]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching estimate details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching estimate: {str(e)}")
    finally:
        release_connection(conn)


@router.put("/{estimate_id}/status")
async def update_estimate_status(estimate_id: int, status: str):
    """Update the status of an estimate (draft, sent, accepted, rejected)"""
    valid_statuses = ['draft', 'sent', 'accepted', 'rejected']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE buyer_estimate
                SET status = %s
                WHERE id = %s
                RETURNING id, estimate_number, status
            """, (status, estimate_id))
            
            result = cur.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Estimate not found")
            
            conn.commit()
            
            return {
                "success": True,
                "message": f"Estimate status updated to {status}",
                "estimate": dict(result)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating estimate status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/company/{company_id}")
async def get_company_estimates(company_id: int, limit: int = 5):
    """Get recent estimates for a specific company with items grouped by tier"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get estimates
            cur.execute("""
                SELECT 
                    be.id,
                    be.estimate_number,
                    be.buyer_ids,
                    be.company_id,
                    be.estimate_date,
                    be.delivery_date_from,
                    be.delivery_date_to,
                    be.status,
                    be.notes,
                    be.created_at,
                    be.updated_at,
                    c.name as company_name,
                    (
                        SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
                        FROM buyers
                        WHERE buyers.id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                        )
                    ) as all_buyers
                FROM buyer_estimate be
                JOIN company c ON be.company_id = c.id
                WHERE be.company_id = %s
                ORDER BY be.created_at DESC
                LIMIT %s
            """, (company_id, limit))
            
            estimates = cur.fetchall()
            
            # For each estimate, get items with details
            results = []
            for estimate in estimates:
                cur.execute("""
                    SELECT 
                        bei.id,
                        bei.buyer_estimate_id,
                        bei.vendor_id,
                        bei.quote_id,
                        v.name as vendor_name,
                        bei.port_code,
                        bei.fish_species_id,
                        fs.common_name,
                        fs.scientific_name,
                        bei.cut_id,
                        fc.name as cut_name,
                        bei.grade_id,
                        fg.name as grade_name,
                        bei.fish_size,
                        bei.fish_price,
                        bei.freight_price,
                        bei.tariff_percent,
                        bei.tariff_amount,
                        bei.margin,
                        bei.price,
                        bei.clearing_charges,
                        bei.offer_quantity,
                        bei.total_price
                    FROM buyer_estimate_item bei
                    JOIN vendors v ON bei.vendor_id = v.id
                    JOIN fish_species fs ON bei.fish_species_id = fs.id
                    JOIN fish_cut fc ON bei.cut_id = fc.id
                    JOIN fish_grade fg ON bei.grade_id = fg.id
                    WHERE bei.buyer_estimate_id = %s
                    ORDER BY bei.offer_quantity, v.name, fs.common_name
                """, (estimate['id'],))
                
                items = cur.fetchall()
                
                estimate_dict = dict(estimate)
                estimate_dict['items'] = [dict(item) for item in items]
                estimate_dict['item_count'] = len(items)
                results.append(estimate_dict)
            
            return {
                "success": True,
                "estimates": results
            }
            
    except Exception as e:
        logger.error(f"Error fetching company estimates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching estimates: {str(e)}")
    finally:
        release_connection(conn)


@router.post("/{estimate_id}/send")
async def send_estimate(estimate_id: int, request: Optional[SendEstimateRequest] = Body(default=None)):
    """Send estimate - update status to 'sent' and generate PDF"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get estimate details
            cur.execute("""
                SELECT 
                    be.*,
                    c.name as company_name,
                    (
                        SELECT STRING_AGG(buyers.name, ', ' ORDER BY buyers.name)
                        FROM buyers
                        WHERE buyers.id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(be.buyer_ids, ',')::INTEGER[])
                        )
                    ) as buyer_names
                FROM buyer_estimate be
                JOIN company c ON be.company_id = c.id
                WHERE be.id = %s
            """, (estimate_id,))
            
            estimate = cur.fetchone()
            if not estimate:
                raise HTTPException(status_code=404, detail="Estimate not found")
            
            # Get estimate items
            cur.execute("""
                SELECT 
                    bei.*,
                    v.name as vendor_name,
                    fs.common_name,
                    fs.scientific_name,
                    fc.name as cut_name,
                    fg.name as grade_name
                FROM buyer_estimate_item bei
                JOIN vendors v ON bei.vendor_id = v.id
                JOIN fish_species fs ON bei.fish_species_id = fs.id
                JOIN fish_cut fc ON bei.cut_id = fc.id
                JOIN fish_grade fg ON bei.grade_id = fg.id
                WHERE bei.buyer_estimate_id = %s
                ORDER BY bei.offer_quantity, fs.common_name
            """, (estimate_id,))
            
            items = cur.fetchall()
            
            # Update status to 'sent'
            cur.execute("""
                UPDATE buyer_estimate
                SET status = 'sent', updated_at = NOW()
                WHERE id = %s
            """, (estimate_id,))
            
            conn.commit()

            notify_buyer = request.notify_buyer if request else True

            # Prepare items for email API
            email_items = []
            for item in items:
                email_items.append({
                    'vendor_name': item['vendor_name'],
                    'common_name': item['common_name'],
                    'scientific_name': item.get('scientific_name') or '',
                    'cut': item['cut_name'],
                    'grade': item['grade_name'],
                    'fish_size': item.get('fish_size') or '',
                    'port': item['port_code'],
                    'offer_quantity': float(item['offer_quantity']),
                    'fish_price': float(item['fish_price']),
                    'margin': float(item['margin']),
                    'freight_price': float(item['freight_price']),
                    'tariff_percent': float(item['tariff_percent']),
                    'clearing_charges': float(item['clearing_charges']),
                    'total_price': float(item['total_price']),
                    'fish_species_id': item['fish_species_id'],
                    'cut_id': item['cut_id'],
                    'grade_id': item['grade_id']
                })

            email_api_url = os.environ.get('EMAIL_SERVICE_URL', 'http://localhost:8001')
            buyer_emails: list = []

            async with httpx.AsyncClient() as client:
                if notify_buyer:
                    # Get buyer emails
                    cur.execute("""
                        SELECT email
                        FROM buyers
                        WHERE id IN (
                            SELECT UNNEST(STRING_TO_ARRAY(%s, ',')::INTEGER[])
                        )
                        AND email IS NOT NULL
                        AND is_email_enabled = true
                    """, (estimate['buyer_ids'],))
                    buyer_emails = [row['email'] for row in cur.fetchall()]

                    if not buyer_emails:
                        raise HTTPException(status_code=400, detail="No valid buyer emails found for this estimate")

                    email_response = await client.post(
                        f"{email_api_url}/email/buyer-pricing/send-estimate",
                        json={
                            'buyer_emails': buyer_emails,
                            'buyer_name': estimate['buyer_names'],
                            'company_name': estimate['company_name'],
                            'estimate_number': estimate['estimate_number'],
                            'items': email_items,
                            'delivery_date_from': estimate.get('delivery_date_from').isoformat() if estimate.get('delivery_date_from') else None,
                            'delivery_date_to': estimate.get('delivery_date_to').isoformat() if estimate.get('delivery_date_to') else None,
                            'notes': estimate.get('notes')
                        },
                        timeout=30.0
                    )
                    email_data = email_response.json()
                    if not email_data.get('success'):
                        raise HTTPException(status_code=500, detail=f"Failed to send email: {email_data.get('message')}")
                else:
                    logger.info(f"Buyer notification skipped for estimate {estimate['estimate_number']} (notify_buyer=False)")

                # Send owner notification (always, fire and forget)
                try:
                    owner_email = settings.owner_notification_email
                    await client.post(
                        f"{email_api_url}/email/buyer-pricing/send-owner-notification",
                        json={
                            'owner_email': owner_email,
                            'company_name': estimate['company_name'],
                            'estimate_number': estimate['estimate_number'],
                            'items': email_items,
                            'delivery_date_from': estimate.get('delivery_date_from').isoformat() if estimate.get('delivery_date_from') else None,
                            'delivery_date_to': estimate.get('delivery_date_to').isoformat() if estimate.get('delivery_date_to') else None
                        },
                        timeout=30.0
                    )
                    logger.info(f"Owner notification sent to {owner_email} for estimate {estimate['estimate_number']}")
                except Exception as owner_err:
                    logger.error(f"Failed to send owner notification: {str(owner_err)}")

            return {
                "success": True,
                "message": f"Estimate sent. Buyer notified: {notify_buyer}.",
                "estimate_id": estimate_id,
                "estimate_number": estimate['estimate_number'],
                "buyer_emails": buyer_emails,
                "notify_buyer": notify_buyer
            }
            
    except Exception as e:
        logger.error(f"Error sending estimate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending estimate: {str(e)}")
    finally:
        release_connection(conn)


class VendorQuoteLookupRequest(BaseModel):
    quote_ids: List[int]


@router.post("/vendor-quotes-lookup")
async def get_vendor_quotes_by_ids(request: VendorQuoteLookupRequest):
    """
    Fetch original vendor quote details for a list of quote IDs.
    Used by the PO dialog to show original vendor quotes alongside estimate items.
    """
    if not request.quote_ids:
        return {"success": True, "quotes": {}}

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get quote header + vendor info
            cur.execute("""
                SELECT
                    q.id as quote_id,
                    q.vendor_id,
                    v.name as vendor_name,
                    v.code as vendor_code,
                    v.contact_email as vendor_email,
                    v.country as country_of_origin,
                    q.quote_valid_till,
                    q.notes,
                    q.price_negotiable,
                    q.exclusive_offer,
                    q.created_at as quote_date
                FROM quote q
                JOIN vendors v ON q.vendor_id = v.id
                WHERE q.id = ANY(%s)
            """, (request.quote_ids,))

            quotes_raw = cur.fetchall()

            # Build a dict keyed by quote_id
            quotes = {}
            for q in quotes_raw:
                qid = q['quote_id']
                quotes[qid] = dict(q)
                quotes[qid]['products'] = []
                quotes[qid]['destinations'] = []

            if not quotes:
                return {"success": True, "quotes": {}}

            # Get products for these quotes
            cur.execute("""
                SELECT
                    qp.quote_id,
                    fs.common_name as fish_type,
                    fc.name as cut_name,
                    fg.name as grade_name,
                    qp.weight_range,
                    qp.price_per_kg,
                    qp.quantity
                FROM quote_product qp
                JOIN fish_species fs ON qp.fish_id = fs.id
                JOIN fish_cut fc ON qp.cut = fc.id
                JOIN fish_grade fg ON qp.grade = fg.id
                WHERE qp.quote_id = ANY(%s)
            """, (request.quote_ids,))

            for prod in cur.fetchall():
                qid = prod['quote_id']
                if qid in quotes:
                    quotes[qid]['products'].append(dict(prod))

            # Get destinations for these quotes
            cur.execute("""
                SELECT
                    qd.quote_id,
                    d.name as destination,
                    d.code as destination_code,
                    qd.airfreight_per_kg,
                    qd.arrival_date,
                    qd.min_weight,
                    qd.max_weight
                FROM quote_destination qd
                JOIN dictionary d ON qd.destination_id = d.id
                WHERE qd.quote_id = ANY(%s)
            """, (request.quote_ids,))

            for dest in cur.fetchall():
                qid = dest['quote_id']
                if qid in quotes:
                    quotes[qid]['destinations'].append(dict(dest))

            return {"success": True, "quotes": quotes}

    except Exception as e:
        logger.error(f"Error fetching vendor quotes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching vendor quotes: {str(e)}")
    finally:
        release_connection(conn)


# =====================================================
# PURCHASE ORDER ENDPOINTS
# =====================================================

class POItemRequest(BaseModel):
    fish_name: str
    cut_name: str
    grade_name: str
    fish_size: Optional[str] = None
    port_code: str
    destination_name: Optional[str] = None
    price_per_kg: float
    airfreight_per_kg: float
    total_per_kg: float
    order_weight_lbs: float
    order_weight_kg: int


class CreatePORequest(BaseModel):
    quote_id: int
    estimate_id: int
    vendor_id: int
    items: List[POItemRequest]
    delivery_date_from: Optional[str] = None
    delivery_date_to: Optional[str] = None


@router.post("/purchase-orders/create")
async def create_purchase_order(request: CreatePORequest):
    """
    Create a purchase order. PO number = PO-{quote_id}-{estimate_id}-{vendor_code}.
    Since estimate_number = EST-YYYY-MM-{id}, the estimate_id IS the suffix.
    Vendor code is looked up from the vendors table using vendor_id.
    One PO per quote+estimate+vendor combination (enforced by unique constraint).
    """
    if not request.items:
        raise HTTPException(status_code=400, detail="At least one PO item is required")

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Look up vendor_code from vendors table
            cur.execute("SELECT code FROM vendors WHERE id = %s", (request.vendor_id,))
            vendor_row = cur.fetchone()
            if not vendor_row:
                raise HTTPException(status_code=404, detail=f"Vendor {request.vendor_id} not found")
            vendor_code = vendor_row['code']

            # PO number uses estimate_id directly (matches estimate_number suffix)
            po_number = f"PO-{request.quote_id}-{request.estimate_id}-{vendor_code}"

            # Check if PO already exists
            cur.execute(
                "SELECT id, po_number, status FROM purchase_order WHERE quote_id = %s AND estimate_id = %s AND vendor_id = %s",
                (request.quote_id, request.estimate_id, request.vendor_id)
            )
            existing = cur.fetchone()
            if existing:
                return {
                    "success": False,
                    "detail": f"PO {existing['po_number']} already exists (status: {existing['status']})",
                    "po_number": existing['po_number'],
                    "po_id": existing['id']
                }

            # Insert PO header
            cur.execute("""
                INSERT INTO purchase_order (po_number, quote_id, estimate_id, vendor_id, status, delivery_date_from, delivery_date_to)
                VALUES (%s, %s, %s, %s, 'sent', %s, %s)
                RETURNING id, po_number, status, created_at
            """, (po_number, request.quote_id, request.estimate_id, request.vendor_id,
                  request.delivery_date_from, request.delivery_date_to))
            po_row = cur.fetchone()
            po_id = po_row['id']

            # Insert PO items
            for item in request.items:
                cur.execute("""
                    INSERT INTO purchase_order_item
                        (po_id, fish_name, cut_name, grade_name, fish_size, port_code,
                         destination_name, price_per_kg, airfreight_per_kg, total_per_kg,
                         order_weight_lbs, order_weight_kg)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    po_id, item.fish_name, item.cut_name, item.grade_name, item.fish_size,
                    item.port_code, item.destination_name, item.price_per_kg,
                    item.airfreight_per_kg, item.total_per_kg,
                    item.order_weight_lbs, item.order_weight_kg
                ))

            conn.commit()

            logger.info(f"Created PO {po_number} with {len(request.items)} items")
            return {
                "success": True,
                "po_id": po_id,
                "po_number": po_number,
                "status": "sent",
                "created_at": str(po_row['created_at']),
                "item_count": len(request.items)
            }

    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating purchase order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating purchase order: {str(e)}")
    finally:
        release_connection(conn)


class POCancelRequest(BaseModel):
    actor_name: str
    actor_code: str
    notes: Optional[str] = None


@router.post("/purchase-orders/{po_id}/cancel")
def cancel_purchase_order(po_id: int, request: POCancelRequest):
    """
    Buyer cancels a purchase order. Only allowed from 'sent' status
    (before vendor has accepted).
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Row-lock and validate transition
            cur.execute(
                "SELECT id, status FROM purchase_order WHERE id = %s FOR UPDATE",
                (po_id,)
            )
            po = cur.fetchone()
            if not po:
                raise HTTPException(status_code=404, detail="Purchase order not found")

            if po['status'] not in ['sent']:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel PO from status '{po['status']}'. "
                           f"Cancellation is only allowed before vendor accepts."
                )

            cur.execute(
                "UPDATE purchase_order SET status = 'cancelled', updated_at = NOW() WHERE id = %s",
                (po_id,)
            )
            cur.execute(
                """
                INSERT INTO purchase_order_audit
                    (po_id, from_status, to_status, actor_role, actor_name, actor_code, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (po_id, po['status'], 'cancelled', 'buyer', request.actor_name, request.actor_code, request.notes)
            )
            conn.commit()
            logger.info(f"PO {po_id} cancelled by buyer {request.actor_code}")
            return {"success": True, "po_id": po_id, "status": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error cancelling PO {po_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_connection(conn)


@router.get("/purchase-orders/by-estimate/{estimate_id}")
async def get_pos_by_estimate(estimate_id: int):
    """
    Get all POs for a given estimate. Used to check PO status on the SummaryTab.
    Returns a dict keyed by vendor_id so the frontend can quickly look up PO state.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    po.id, po.po_number, po.quote_id, po.estimate_id,
                    po.vendor_id, po.status, po.created_at
                FROM purchase_order po
                WHERE po.estimate_id = %s
                ORDER BY po.created_at DESC
            """, (estimate_id,))

            rows = cur.fetchall()
            # Build a dict keyed by vendor_id for easy lookup
            pos_by_vendor: dict = {}
            for row in rows:
                vid = row['vendor_id']
                pos_by_vendor[vid] = dict(row)
                # Convert datetime to string
                pos_by_vendor[vid]['created_at'] = str(row['created_at'])

            # Fetch items for each PO so the buyer can see what weights were ordered
            for po_dict in pos_by_vendor.values():
                cur.execute("""
                    SELECT fish_name, cut_name, grade_name, fish_size,
                           port_code, order_weight_lbs, order_weight_kg
                    FROM purchase_order_item
                    WHERE po_id = %s
                    ORDER BY port_code, fish_name
                """, (po_dict['id'],))
                po_dict['items'] = [dict(r) for r in cur.fetchall()]

            return {"success": True, "purchase_orders": pos_by_vendor}

    except Exception as e:
        logger.error(f"Error fetching POs for estimate {estimate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        release_connection(conn)
