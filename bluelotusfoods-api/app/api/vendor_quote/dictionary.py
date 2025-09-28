from fastapi import APIRouter, Depends, HTTPException
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor

router = APIRouter()

@router.get("/{category}")
def get_dictionary(category: str):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.DICTIONARY['get_by_category'], (category.upper(),))
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Destination not found")
            return rows
    finally:
        release_connection(conn)
