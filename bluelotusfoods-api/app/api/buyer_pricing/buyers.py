from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class Buyer(BaseModel):
    id: int
    name: str
    email: Optional[str]
    company_id: int
    company_name: str
    active: bool


class BuyerWithPorts(BaseModel):
    id: int
    name: str
    email: Optional[str]
    company_id: int
    company_name: str
    active: bool
    ports: List[dict]  # List of {id, code, name}


@router.get("/buyers", response_model=List[Buyer])
async def get_all_buyers():
    """Get all buyers with their company information"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.BUYER_PRICING['get_all_buyers'])
            buyers = cur.fetchall()
            return [dict(row) for row in buyers]
    except Exception as e:
        logger.error(f"Error fetching buyers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching buyers: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/buyers/{buyer_id}", response_model=BuyerWithPorts)
async def get_buyer_with_ports(buyer_id: int):
    """Get a specific buyer with their company's ports"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get buyer info
            cur.execute(DatabaseQueries.BUYER_PRICING['get_buyer_by_id'], (buyer_id,))
            
            buyer = cur.fetchone()
            if not buyer:
                raise HTTPException(status_code=404, detail="Buyer not found")
            
            # Get company's ports
            cur.execute(DatabaseQueries.BUYER_PRICING['get_company_ports'], (buyer['company_id'],))
            
            ports = [dict(row) for row in cur.fetchall()]
            
            result = dict(buyer)
            result['ports'] = ports
            
            return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching buyer {buyer_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching buyer: {str(e)}")
    finally:
        release_connection(conn)


@router.get("/company/{company_id}/buyers", response_model=List[Buyer])
async def get_buyers_by_company(company_id: int):
    """Get all buyers for a specific company"""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.BUYER_PRICING['get_buyers_by_company'], (company_id,))
            
            buyers = cur.fetchall()
            return [dict(row) for row in buyers]
    except Exception as e:
        logger.error(f"Error fetching buyers for company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching buyers: {str(e)}")
    finally:
        release_connection(conn)
