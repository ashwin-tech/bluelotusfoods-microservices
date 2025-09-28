from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor

router = APIRouter()

@router.get("/{vendor_code}")
def get_vendor(vendor_code: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.VENDORS['get_by_code'], (vendor_code,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row
    finally:
        release_connection(conn)
