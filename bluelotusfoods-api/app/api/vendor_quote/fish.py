from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.db import get_conn
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor

router = APIRouter()


class FishSpeciesIn(BaseModel):
    common_name: str
    scientific_name: str


class FishCutIn(BaseModel):
    code: str
    name: str


class FishGradeIn(BaseModel):
    code: str
    name: str


@router.get("/types")
def get_fish_types():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_types'])
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No fish species found")
            return rows


@router.post("/types")
def add_fish_species(body: FishSpeciesIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['insert_species'],
                            (body.common_name.strip(), body.scientific_name.strip()))
                row = cur.fetchone()
                conn.commit()
                return row
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.delete("/types/{species_id}")
def deactivate_fish_species(species_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['deactivate_species'], (species_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Species not found")
            conn.commit()
            return {"success": True}


@router.put("/types/{species_id}")
def update_fish_species(species_id: int, body: FishSpeciesIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['update_species'],
                            (body.common_name.strip(), body.scientific_name.strip(), species_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Species not found")
                conn.commit()
                return row
            except HTTPException:
                raise
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.get("/cut")
def get_fish_cuts():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_cuts'])
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No cuts found")
            return rows


@router.post("/cut")
def add_fish_cut(body: FishCutIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['insert_cut'],
                            (body.code.strip().upper(), body.name.strip()))
                row = cur.fetchone()
                conn.commit()
                return row
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.delete("/cut/{cut_id}")
def delete_fish_cut(cut_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['delete_cut'], (cut_id,))
                conn.commit()
                return {"success": True}
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail="Cannot delete — cut is still referenced by existing quotes or sizes")


@router.put("/cut/{cut_id}")
def update_fish_cut(cut_id: int, body: FishCutIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['update_cut'],
                            (body.code.strip().upper(), body.name.strip(), cut_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Cut not found")
                conn.commit()
                return row
            except HTTPException:
                raise
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.get("/grade")
def get_fish_grades():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(DatabaseQueries.FISH['get_grades'])
            rows = cur.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No grades found")
            return rows


@router.post("/grade")
def add_fish_grade(body: FishGradeIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['insert_grade'],
                            (body.code.strip().upper(), body.name.strip()))
                row = cur.fetchone()
                conn.commit()
                return row
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))


@router.delete("/grade/{grade_id}")
def delete_fish_grade(grade_id: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['delete_grade'], (grade_id,))
                conn.commit()
                return {"success": True}
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail="Cannot delete — grade is still referenced by existing quotes")


@router.put("/grade/{grade_id}")
def update_fish_grade(grade_id: int, body: FishGradeIn):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                cur.execute(DatabaseQueries.FISH['update_grade'],
                            (body.code.strip().upper(), body.name.strip(), grade_id))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Grade not found")
                conn.commit()
                return row
            except HTTPException:
                raise
            except Exception as e:
                conn.rollback()
                raise HTTPException(status_code=400, detail=str(e))
