from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class ClearingCharges(BaseModel):
    id: Optional[int] = None
    custom_entry_fee: Decimal
    airline_service_fee: Decimal
    prior_notice_pre_fda: Decimal
    food_and_drug_service: Decimal
    simp_filing: Decimal
    tariff_filing: Decimal
    customs_tax_per_10000: Decimal
    customs_tax_per_20000: Decimal
    customs_tax_per_30000: Decimal
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    is_active: Optional[bool] = None


class SaveClearingChargesRequest(BaseModel):
    custom_entry_fee: Decimal
    airline_service_fee: Decimal
    prior_notice_pre_fda: Decimal
    food_and_drug_service: Decimal
    simp_filing: Decimal
    tariff_filing: Decimal
    customs_tax_per_10000: Decimal
    customs_tax_per_20000: Decimal
    customs_tax_per_30000: Decimal


@router.get("/active")
async def get_active_clearing_charges():
    """Get the currently active clearing charges"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    id,
                    custom_entry_fee,
                    airline_service_fee,
                    prior_notice_pre_fda,
                    food_and_drug_service,
                    simp_filing,
                    tariff_filing,
                    customs_tax_per_10000,
                    customs_tax_per_20000,
                    customs_tax_per_30000,
                    valid_from,
                    valid_to,
                    is_active
                FROM clearing_charges
                WHERE is_active = true
                LIMIT 1
            """)
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="No active clearing charges found")
            
            return dict(result)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching active clearing charges: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching clearing charges: {str(e)}")
    finally:
        release_connection(conn)


@router.post("/save")
async def save_clearing_charges(request: SaveClearingChargesRequest):
    """
    Save new clearing charges. This will:
    1. Set valid_to on the current active record
    2. Insert new record with current timestamp
    3. Mark new record as active
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Start transaction
            cur.execute("BEGIN")
            
            # Update the current active record's valid_to and set is_active to false
            cur.execute("""
                UPDATE clearing_charges
                SET valid_to = NOW(),
                    is_active = false
                WHERE is_active = true
            """)
            
            # Insert new record
            cur.execute("""
                INSERT INTO clearing_charges (
                    custom_entry_fee,
                    airline_service_fee,
                    prior_notice_pre_fda,
                    food_and_drug_service,
                    simp_filing,
                    tariff_filing,
                    customs_tax_per_10000,
                    customs_tax_per_20000,
                    customs_tax_per_30000,
                    valid_from,
                    is_active
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), true
                )
                RETURNING id, valid_from
            """, (
                request.custom_entry_fee,
                request.airline_service_fee,
                request.prior_notice_pre_fda,
                request.food_and_drug_service,
                request.simp_filing,
                request.tariff_filing,
                request.customs_tax_per_10000,
                request.customs_tax_per_20000,
                request.customs_tax_per_30000
            ))
            
            result = cur.fetchone()
            conn.commit()
            
            return {
                "success": True,
                "message": "Clearing charges saved successfully",
                "id": result['id'],
                "valid_from": result['valid_from'].isoformat()
            }
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving clearing charges: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving clearing charges: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/history")
async def get_clearing_charges_history():
    """Get all clearing charges history"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    id,
                    custom_entry_fee,
                    airline_service_fee,
                    prior_notice_pre_fda,
                    food_and_drug_service,
                    simp_filing,
                    tariff_filing,
                    customs_tax_per_10000,
                    customs_tax_per_20000,
                    customs_tax_per_30000,
                    valid_from,
                    valid_to,
                    is_active
                FROM clearing_charges
                ORDER BY valid_from DESC
            """)
            results = cur.fetchall()
            
            return {
                "success": True,
                "history": [dict(row) for row in results]
            }
            
    except Exception as e:
        logger.error(f"Error fetching clearing charges history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching history: {str(e)}")
    finally:
        release_connection(conn)
