from fastapi import APIRouter, HTTPException
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from app.services.pricing_calculations import (
    calculate_estimate_totals,
    KG_TO_LBS,
    kg_to_lbs,
    lbs_to_kg,
    convert_fish_size_to_lbs,
)
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


def convert_vendor_price_to_buyer_price(estimate: dict) -> dict:
    """
    Convert vendor prices from KG to LBS for buyer pricing display.
    Vendor quotes are submitted in KG, but buyer pricing is displayed in LBS.
    """
    # Convert per-kg prices/quantities to per-lb
    fish_price_lb    = lbs_to_kg(Decimal(str(estimate.get('fish_price', 0))))
    freight_price_lb = lbs_to_kg(Decimal(str(estimate.get('freight_price', 0))))
    margin_lb        = lbs_to_kg(Decimal(str(estimate.get('margin', 0))))
    offer_quantity_lb = kg_to_lbs(Decimal(str(estimate.get('offer_quantity', 0))))
    
    # If fish_size_id is set, fish_size is already the correct lbs/range label from the DB CASE expression.
    # Only run the legacy kg→lbs conversion for old quotes that have no fish_size_id.
    if estimate.get('fish_size_id') is not None:
        fish_size_display = estimate.get('fish_size')
    else:
        fish_size_display = convert_fish_size_to_lbs(estimate.get('fish_size'))

    # Return updated estimate with LB prices
    return {
        **estimate,
        'offer_quantity': float(offer_quantity_lb),
        'fish_price': float(fish_price_lb),
        'freight_price': float(freight_price_lb),
        'margin': float(margin_lb),
        'fish_size': fish_size_display
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
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = DatabaseQueries.ESTIMATES['search_base']
                params = []

                if request.vendor_ids:
                    query += " AND v.id = ANY(%s)"
                    params.append(request.vendor_ids)

                if request.port_codes:
                    query += " AND d.code = ANY(%s)"
                    params.append(request.port_codes)

                if request.date_range:
                    if request.date_range == "This Week":
                        query += """
                            AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                            AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day' + INTERVAL '7 days'
                        """
                    elif request.date_range == "Last Week":
                        query += """
                            AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '8 days'
                            AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                        """
                    elif request.date_range == "This Month":
                        query += " AND q.created_at >= DATE_TRUNC('month', CURRENT_DATE)"

                query += " ORDER BY q.id DESC, q.created_at DESC, d.code, f.common_name, qp.weight_range"

                cur.execute(query, params)
                results = cur.fetchall()

                estimates_in_lbs = [convert_vendor_price_to_buyer_price(dict(row)) for row in results]
                estimates_with_totals = [calculate_estimate_totals(estimate) for estimate in estimates_in_lbs]

                return {
                    "success": True,
                    "count": len(estimates_with_totals),
                    "estimates": estimates_with_totals
                }
        except Exception as e:
            logger.error(f"Error searching estimates: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error searching estimates: {str(e)}")


@router.get("/buyers/{buyer_id}/estimates")
async def get_buyer_estimates(buyer_id: int, date_range: Optional[str] = "This Week"):
    """Get estimates for a specific buyer based on their company's ports"""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(DatabaseQueries.ESTIMATES['buyer_ports'], (buyer_id,))
                port_codes = [row['code'] for row in cur.fetchall()]

                if not port_codes:
                    return {"success": True, "count": 0, "estimates": []}

                query = DatabaseQueries.ESTIMATES['buyer_estimates_base']
                params = [port_codes]

                if date_range == "This Week":
                    query += """
                        AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                        AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day' + INTERVAL '7 days'
                    """
                elif date_range == "Last Week":
                    query += """
                        AND q.created_at >= DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '8 days'
                        AND q.created_at < DATE_TRUNC('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'
                    """
                elif date_range == "This Month":
                    query += " AND q.created_at >= DATE_TRUNC('month', CURRENT_DATE)"

                query += " ORDER BY q.id DESC, q.created_at DESC, d.code, f.common_name, qp.weight_range"

                cur.execute(query, params)
                results = cur.fetchall()

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
