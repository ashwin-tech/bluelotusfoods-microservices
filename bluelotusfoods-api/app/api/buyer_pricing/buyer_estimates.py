from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.services.pricing_calculations import calculate_estimate_totals
from app.services.pdf_generator import generate_estimate_pdf, get_pdf_filename
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import date
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class EstimateItemToSave(BaseModel):
    """
    All prices are in LBS (pounds) for buyer pricing.
    Vendor quotes are in KG but converted to LBS on the frontend before saving.
    """
    vendor_id: int
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
            
            # Generate estimate number: EST-YYYY-NNN
            cur.execute("SELECT NEXTVAL('buyer_estimate_number_seq')")
            seq_num = cur.fetchone()['nextval']
            from datetime import datetime
            estimate_number = f"EST-{datetime.now().year}-{seq_num:04d}"
            
            # Insert buyer_estimate header
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
                    %s, %s, %s, %s, %s, %s, 'draft'
                )
                RETURNING id, estimate_date, delivery_date_from, delivery_date_to, created_at
            """, (
                estimate_number,
                request.company_id,
                request.buyer_ids or str(request.buyer_id),  # Use buyer_ids if provided, otherwise use buyer_id
                request.notes,
                request.delivery_date_from,
                request.delivery_date_to
            ))
            
            result = cur.fetchone()
            estimate_id = result['id']
            estimate_date = result['estimate_date']
            created_at = result['created_at']
            
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
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    estimate_id,
                    item.vendor_id,
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
                }
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
async def send_estimate(estimate_id: int):
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
            
            # Generate PDF
            pdf_path = generate_estimate_pdf(
                estimate_data=dict(estimate),
                items=[dict(item) for item in items]
            )
            
            pdf_filename = get_pdf_filename(estimate['estimate_number'])
            
            return {
                "success": True,
                "message": "Estimate sent successfully",
                "pdf_filename": pdf_filename,
                "pdf_path": pdf_path,
                "estimate_id": estimate_id,
                "estimate_number": estimate['estimate_number']
            }
            
    except Exception as e:
        logger.error(f"Error sending estimate: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending estimate: {str(e)}")
    finally:
        release_connection(conn)
