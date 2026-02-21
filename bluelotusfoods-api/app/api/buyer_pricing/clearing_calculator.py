from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.services.pricing_calculations import calculate_clearing_charges_with_quantity
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class CalculateClearingRequest(BaseModel):
    """
    All prices must be in LBS (pounds) for buyer pricing.
    If converting from vendor quotes (which are in KG), divide by 2.20462.
    """
    fish_price: Decimal  # Per LB (from vendor)
    freight_price: Decimal  # Per LB
    tariff_percent: Decimal
    fish_species_id: int
    margin: Decimal = Decimal('0')  # Margin to add to fish price


@router.post("/calculate")
async def calculate_clearing_charges(request: CalculateClearingRequest):
    """
    Calculate clearing charges and offer quantities for $10k, $20k, $30k invoice tiers.
    
    NOTE: All prices must be in LBS (pounds), not KG.
    Returns rounded quantities (in LBS) and clearing charges per LB for each tier.
    Minimum quantity: 1200 LBS, rounded to nearest 100 LBS.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get active clearing charges
            cur.execute("""
                SELECT 
                    custom_entry_fee,
                    airline_service_fee,
                    prior_notice_pre_fda,
                    food_and_drug_service,
                    simp_filing,
                    tariff_filing,
                    customs_tax_per_10000,
                    customs_tax_per_20000,
                    customs_tax_per_30000
                FROM clearing_charges
                WHERE is_active = true
                LIMIT 1
            """)
            
            clearing_config = cur.fetchone()
            if not clearing_config:
                raise HTTPException(status_code=404, detail="No active clearing charges found")
            
            # Check if SIMP filing applies to this fish species
            cur.execute("""
                SELECT is_simp_applicable
                FROM fish_species_simp_applicable
                WHERE fish_species_id = %s
            """, (request.fish_species_id,))
            
            simp_result = cur.fetchone()
            is_simp_applicable = simp_result['is_simp_applicable'] if simp_result else False
            
            # Calculate clearing charges for all tiers
            tiers = calculate_clearing_charges_with_quantity(
                fish_price=request.fish_price,
                freight_price=request.freight_price,
                tariff_percent=request.tariff_percent,
                clearing_charges_config=dict(clearing_config),
                is_simp_applicable=is_simp_applicable,
                margin=request.margin
            )
            
            return {
                "success": True,
                "tiers": tiers,
                "is_simp_applicable": is_simp_applicable
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating clearing charges: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating clearing charges: {str(e)}")
    finally:
        release_connection(conn)
