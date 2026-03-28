from fastapi import APIRouter, Depends, HTTPException
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from typing import Optional

router = APIRouter()


@router.get("/fish-sizes")
def get_fish_sizes(fish_species_id: Optional[int] = None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if fish_species_id is not None:
                cur.execute("""
                    SELECT fs.*, sp.common_name as species_name, fc.name as cut_name
                    FROM fish_size fs
                    JOIN fish_species sp ON fs.fish_species_id = sp.id
                    LEFT JOIN fish_cut fc ON fs.cut_id = fc.id
                    WHERE fs.active = TRUE AND fs.fish_species_id = %s
                    ORDER BY fs.sort_order
                """, (fish_species_id,))
            else:
                cur.execute("""
                    SELECT fs.*, sp.common_name as species_name, fc.name as cut_name
                    FROM fish_size fs
                    JOIN fish_species sp ON fs.fish_species_id = sp.id
                    LEFT JOIN fish_cut fc ON fs.cut_id = fc.id
                    WHERE fs.active = TRUE
                    ORDER BY sp.common_name, fs.sort_order
                """)
            return cur.fetchall()


@router.get("/{category}")
def get_dictionary(category: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.DICTIONARY['get_by_category'], (category.upper(),))
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="Destination not found")
            return rows
