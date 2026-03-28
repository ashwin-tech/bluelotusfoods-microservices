from fastapi import APIRouter, HTTPException
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor

router = APIRouter()

@router.get("/types")
def get_vendor():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_types'])
            row = cur.fetchall()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row

@router.get("/cut")
def get_vendor():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_cuts'])
            row = cur.fetchall()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row

@router.get("/grade")
def get_vendor():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_grades'])
            row = cur.fetchall()
            if not row:
                raise HTTPException(status_code=404, detail="Vendor not found")
            return row
