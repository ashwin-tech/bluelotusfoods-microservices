from fastapi import APIRouter, HTTPException
from app.db.db import get_connection, release_connection
from app.db.queries import DatabaseQueries
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import List

router = APIRouter()

class Destination(BaseModel):
    destination: str
    airfreight_per_kg: float
    arrival_date: str
    min_weight: float
    max_weight: float

class Product(BaseModel):
    fish_common_name: str
    weight_range: str
    cut_name: str
    grade_name: str
    price_per_kg: float
    quantity: int
class Quote(BaseModel):
    id: int
    vendor_name: str
    quote_valid_till: str
    notes: str
    price_negotiable: bool
    exclusive_offer: bool
    destinations: List[Destination]
    products: List[Product]

@router.post("/")
def create_quote(quote: Quote):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Look up vendor_id based on vendor name
            cur.execute(DatabaseQueries.VENDORS['get_by_name'], (quote.vendor_name,))
            vendor = cur.fetchone()
            if not vendor:
                raise HTTPException(status_code=404, detail="Vendor not found")
            vendor_id = vendor["id"]

            # Insert into quote table using the provided Quote ID
            cur.execute(
                DatabaseQueries.QUOTES['insert'],
                (quote.id, vendor_id, quote.quote_valid_till, quote.notes, quote.price_negotiable, quote.exclusive_offer)
            )

            # Insert into quote_destination table
            for destination in quote.destinations:
                # Extract the destination code (e.g., BOS from "Boston (BOS)")
                destination_code = destination.destination.split("(")[-1].strip(")")

                # Look up destination_id based on the code
                cur.execute(DatabaseQueries.DICTIONARY['get_by_code'], (destination_code,))
                destination_row = cur.fetchone()
                if not destination_row:
                    raise HTTPException(status_code=404, detail=f"Destination not found: {destination.destination_id}")
                destination_id = destination_row["id"]

                cur.execute(
                    DatabaseQueries.QUOTES['insert_destination'],
                    (quote.id, destination_id, destination.airfreight_per_kg, destination.arrival_date, destination.min_weight, destination.max_weight)
                )

            # Insert into quote_product table
            for product in quote.products:
                # Look up fish_id based on common_name
                cur.execute(DatabaseQueries.FISH['get_by_name'], (product.fish_common_name,))
                fish = cur.fetchone()
                if not fish:
                    raise HTTPException(status_code=404, detail=f"Fish not found: {product.fish_common_name}")
                fish_id = fish["id"]

                # Look up cut_id based on cut name
                cur.execute(DatabaseQueries.FISH['get_cut_by_name'], (product.cut_name,))
                cut = cur.fetchone()
                if not cut:
                    raise HTTPException(status_code=404, detail=f"Cut not found: {product.cut_name}")
                cut_id = cut["id"]

                # Look up grade_id based on grade name
                cur.execute(DatabaseQueries.FISH['get_grade_by_name'], (product.grade_name,))
                grade = cur.fetchone()
                if not grade:
                    raise HTTPException(status_code=404, detail=f"Grade not found: {product.grade_name}")
                grade_id = grade["id"]

                cur.execute(
                    DatabaseQueries.QUOTES['insert_product'],
                    (quote.id, fish_id, product.weight_range, cut_id, grade_id, product.price_per_kg, product.quantity)
                )

            conn.commit()
            return {"message": "Quote created successfully", "quote_id": quote.id, "id": quote.id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating quote: {str(e)}")
    finally:
        release_connection(conn)