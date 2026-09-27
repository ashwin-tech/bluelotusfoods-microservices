from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from typing import Optional

router = APIRouter()


class DictionaryIn(BaseModel):
    category: str
    code: str
    name: str
    description: Optional[str] = None


class FishSizeIn(BaseModel):
    fish_species_id: int
    cut_id: Optional[int] = None
    kg_label: float
    kg_max: Optional[float] = None
    lbs_label: float
    lbs_max: Optional[float] = None
    sort_order: int = 0


@router.post("/")
def add_dictionary_entry(body: DictionaryIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.DICTIONARY['insert'],
                            (body.category.strip().upper(), body.code.strip().upper(),
                             body.name.strip(), body.description))
                row = cur.fetchone()
                conn.commit()
                return row
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.delete("/fish-sizes/{size_id}")
def deactivate_fish_size(size_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['deactivate_size'], (size_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Fish size not found")
            conn.commit()
            return {"success": True}


@router.delete("/{entry_id}")
def deactivate_dictionary_entry(entry_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.DICTIONARY['deactivate'], (entry_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Entry not found")
            conn.commit()
            return {"success": True}


@router.put("/fish-sizes/{size_id}")
def update_fish_size(size_id: int, body: FishSizeIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['update_size'], (
                    body.fish_species_id, body.cut_id,
                    body.kg_label, body.kg_max,
                    body.lbs_label, body.lbs_max,
                    body.sort_order, size_id,
                ))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Fish size not found")
                conn.commit()
                return row
            except HTTPException:
                raise
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.put("/{entry_id}")
def update_dictionary_entry(entry_id: int, body: DictionaryIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.DICTIONARY['update'],
                            (body.code.strip().upper(), body.name.strip(), body.description, entry_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Entry not found")
                conn.commit()
                return row
            except HTTPException:
                raise
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.post("/fish-sizes")
def add_fish_size(body: FishSizeIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['insert_size'], (
                    body.fish_species_id, body.cut_id,
                    body.kg_label, body.kg_max,
                    body.lbs_label, body.lbs_max,
                    body.sort_order,
                ))
                row = cur.fetchone()
                conn.commit()
                return row
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


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
