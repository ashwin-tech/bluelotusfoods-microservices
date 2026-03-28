from fastapi import APIRouter
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor

router = APIRouter()

@router.get("/")
def get_all_vendors():
    """Get all active vendors for buyer pricing"""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.BUYER_PRICING['get_all_vendors'])
            return cur.fetchall()
