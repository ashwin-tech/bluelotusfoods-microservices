from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from app.services.pricing_calculations import calculate_estimate_totals
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Conversion constant: 1 kg = 2.20462 lbs
KG_TO_LBS = Decimal('2.20462')


def convert_fish_size_to_lbs(fish_size: Optional[str]) -> Optional[str]:
    """
    Convert fish size from kg to lbs (returns just the number, no unit suffix).
    Examples:
      "2-3 kg" -> "4.4-6.6"
      "2-3" -> "4.4-6.6"
      "0.5 kg" -> "1.1"
      "0.5" -> "1.1"
      "0.2" -> "0.4"
      "5+ kg" -> "11+"
      "45" -> "99.2"
    """
    if not fish_size:
        return None
    
    # Convert to string if it's not already (handles Decimal, int, float)
    fish_size_str = str(fish_size).strip()
    
    import re
    
    # Try to match patterns like "2-3 kg" or "2-3"
    # Pattern for range: "2-3 kg" or "2-3"
    range_match = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(?:kg)?', fish_size_str.lower())
    if range_match:
        min_kg = float(range_match.group(1))
        max_kg = float(range_match.group(2))
        min_lbs = min_kg * 2.20462
        max_lbs = max_kg * 2.20462
        return f"{min_lbs:.1f}-{max_lbs:.1f}"
    
    # Pattern for "5+ kg" or "5+" or "5 kg up"
    plus_match = re.match(r'(\d+\.?\d*)\s*\+\s*(?:kg)?', fish_size_str.lower())
    if plus_match:
        kg_value = float(plus_match.group(1))
        lbs_value = kg_value * 2.20462
        return f"{lbs_value:.1f}+"
    
    # Pattern for single number with or without "kg": "5 kg" or "5" or "0.5"
    single_match = re.match(r'(\d+\.?\d*)\s*(?:kg)?$', fish_size_str.lower())
    if single_match:
        kg_value = float(single_match.group(1))
        lbs_value = kg_value * 2.20462
        return f"{lbs_value:.1f}"
    
    # If no pattern matches, return original
    return fish_size_str


def convert_vendor_price_to_buyer_price(estimate: dict) -> dict:
    """
    Convert vendor prices from KG to LBS for buyer pricing display.
    Vendor quotes are submitted in KG, but buyer pricing is displayed in LBS.
    """
    # Convert fish_price from per KG to per LB
    fish_price_kg = Decimal(str(estimate.get('fish_price', 0)))
    fish_price_lb = fish_price_kg / KG_TO_LBS
    
    # Convert freight_price from per KG to per LB
    freight_price_kg = Decimal(str(estimate.get('freight_price', 0)))
    freight_price_lb = freight_price_kg / KG_TO_LBS
    
    # Convert margin from per KG to per LB
    margin_kg = Decimal(str(estimate.get('margin', 0)))
    margin_lb = margin_kg / KG_TO_LBS
    
    # Convert offer_quantity from KG to LBS
    offer_quantity_kg = Decimal(str(estimate.get('offer_quantity', 0)))
    offer_quantity_lb = offer_quantity_kg * KG_TO_LBS
    
    # Convert fish_size from kg to lbs/oz
    fish_size_lbs = convert_fish_size_to_lbs(estimate.get('fish_size'))
    
    # Return updated estimate with LB prices
    return {
        **estimate,
        'offer_quantity': float(offer_quantity_lb),
        'fish_price': float(fish_price_lb),
        'freight_price': float(freight_price_lb),
        'margin': float(margin_lb),
        'fish_size': fish_size_lbs
    }


class EstimateItem(BaseModel):
    quote_id: Optional[int]
    quote_date: Optional[str]
    vendor_name: str
    port: str
    common_name: str
    scientific_name: str
    cut: str
    grade: str
    fish_size: Optional[str] = None  # Weight range from vendor quote
    fish_price: Decimal  # Per LB for buyer pricing
    freight_price: Decimal  # Per LB for buyer pricing
    tariff_percent: Decimal
    margin: Decimal  # Per LB for buyer pricing
    tariff_amount: float  # Per LB
    base_cost: float  # Per LB
    total_price: float  # Per LB


class CreateEstimateRequest(BaseModel):
    buyer_ids: List[int]
    vendor_ids: List[int]
    port_codes: List[str]
    date_range: str  # e.g., "This Week", "Last Week", "This Month"


@router.post("/search")
async def search_estimates(request: CreateEstimateRequest):
    """Search vendor quotes based on selected buyers, vendors, and ports"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build dynamic query
            query = """
                SELECT 
                    q.id as quote_id,
                    q.created_at::date as quote_date,
                    v.id as vendor_id,
                    v.name as vendor_name,
                    d.code as port,
                    f.id as fish_species_id,
                    f.common_name,
                    f.scientific_name,
                    fc.id as cut_id,
                    fc.name as cut,
                    fg.id as grade_id,
                    fg.name as grade,
                    qp.weight_range as fish_size,
                    qp.quantity as offer_quantity,
                    qp.price_per_kg as fish_price,
                    qd.airfreight_per_kg as freight_price,
                    COALESCE(t.reciprocal_tariff + t.secondary_tariff, 0) as tariff_percent,
                    0 as margin,
                    0 as clearing_charges
                FROM quote q
                JOIN vendors v ON q.vendor_id = v.id
                LEFT JOIN tariff t ON v.country = t.country AND t.active = true
                JOIN quote_destination qd ON q.id = qd.quote_id
                JOIN dictionary d ON qd.destination_id = d.id
                JOIN quote_product qp ON q.id = qp.quote_id
                JOIN fish_species f ON qp.fish_id = f.id
                JOIN fish_cut fc ON qp.cut = fc.id
                JOIN fish_grade fg ON qp.grade = fg.id
                WHERE 1=1
            """
            
            params = []
            
            # Add vendor filter
            if request.vendor_ids:
                query += " AND v.id = ANY(%s)"
                params.append(request.vendor_ids)
            
            # Add port filter
            if request.port_codes:
                query += " AND d.code = ANY(%s)"
                params.append(request.port_codes)
            
            # Add date range filter
            if request.date_range:
                if request.date_range == "This Week":
                    # This Week: Sunday to Saturday of current week
                    # dow 0 = Sunday, so we calculate the start of the week (Sunday)
                    query += """ 
                        AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                        AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day' + INTERVAL '7 days'
                    """
                elif request.date_range == "Last Week":
                    # Last Week: Sunday to Saturday of previous week
                    query += """
                        AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '8 days'
                        AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                    """
                elif request.date_range == "This Month":
                    query += " AND q.created_at >= DATE_TRUNC('month', CURRENT_DATE)"
            
            query += " ORDER BY q.id DESC, q.created_at DESC, d.code, f.common_name, qp.weight_range"
            
            cur.execute(query, params)
            results = cur.fetchall()
            
            # Convert vendor prices from KG to LBS for buyer pricing
            estimates_in_lbs = [convert_vendor_price_to_buyer_price(dict(row)) for row in results]
            
            # Calculate totals for each estimate (now in LBS)
            estimates_with_totals = [calculate_estimate_totals(estimate) for estimate in estimates_in_lbs]
            
            return {
                "success": True,
                "count": len(estimates_with_totals),
                "estimates": estimates_with_totals
            }
            
    except Exception as e:
        logger.error(f"Error searching estimates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching estimates: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/buyers/{buyer_id}/estimates")
async def get_buyer_estimates(buyer_id: int, date_range: Optional[str] = "This Week"):
    """Get estimates for a specific buyer based on their company's ports"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get buyer's company ports
            cur.execute("""
                SELECT d.code
                FROM buyers b
                JOIN company_ports cp ON b.company_id = cp.company_id
                JOIN dictionary d ON cp.port_id = d.id
                WHERE b.id = %s
            """, (buyer_id,))
            
            port_codes = [row['code'] for row in cur.fetchall()]
            
            if not port_codes:
                return {
                    "success": True,
                    "count": 0,
                    "estimates": []
                }
            
            # Search estimates for these ports
            query = """
                SELECT 
                    q.id as quote_id,
                    q.created_at::date as quote_date,
                    d.code as port,
                    f.common_name,
                    fc.name as cut,
                    fg.name as grade,
                    qp.weight_range as fish_size,
                    qp.price_per_kg as fish_price,
                    qd.airfreight_per_kg as freight_price,
                    0 as tariff_percent,
                    0 as margin
                FROM quote q
                JOIN quote_destination qd ON q.id = qd.quote_id
                JOIN dictionary d ON qd.destination_id = d.id
                JOIN quote_product qp ON q.id = qp.quote_id
                JOIN fish f ON qp.fish_id = f.id
                JOIN fish_cut fc ON qp.cut_id = fc.id
                JOIN fish_grade fg ON qp.grade_id = fg.id
                WHERE d.code = ANY(%s)
            """
            
            params = [port_codes]
            
            # Add date range (Week = Sunday to Saturday)
            if date_range == "This Week":
                # This Week: Sunday to Saturday of current week
                query += """ 
                    AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                    AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day' + INTERVAL '7 days'
                """
            elif date_range == "Last Week":
                # Last Week: Sunday to Saturday of previous week
                query += """
                    AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '8 days'
                    AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                """
            elif date_range == "This Month":
                query += " AND q.created_at >= DATE_TRUNC('month', CURRENT_DATE)"
            
            query += " ORDER BY q.id DESC, q.created_at DESC, d.code, f.common_name, qp.weight_range"
            
            cur.execute(query, params)
            results = cur.fetchall()
            
            # Convert vendor prices from KG to LBS for buyer pricing
            estimates_in_lbs = [convert_vendor_price_to_buyer_price(dict(row)) for row in results]
            
            return {
                "success": True,
                "count": len(estimates_in_lbs),
                "buyer_id": buyer_id,
                "port_codes": port_codes,
                "estimates": estimates_in_lbs
            }
            
    except Exception as e:
        logger.error(f"Error getting estimates for buyer {buyer_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting estimates: {str(e)}")
    finally:
        release_connection(conn)
