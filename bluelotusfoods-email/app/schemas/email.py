from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Union
from datetime import datetime


class VendorQuoteEmailRequest(BaseModel):
    quote_id: int
    vendor_email: EmailStr
    vendor_name: str
    quote_data: dict  # The quote details from the database


class OwnerNotificationEmailRequest(BaseModel):
    quote_id: int
    owner_email: EmailStr
    vendor_name: str
    quote_data: dict  # The quote details from the database
    

class EmailResponse(BaseModel):
    success: bool
    message: str
    email_id: Optional[str] = None


class QuoteDestination(BaseModel):
    destination: str
    airfreight_per_kg: Union[str, float, int]  # Accept various numeric types
    arrival_date: str
    min_weight: Union[str, float, int]
    max_weight: Union[str, float, int]


class QuoteSize(BaseModel):
    fish_type: str
    cut_name: str  # Changed from 'cut' to 'cut_name'
    grade_name: str  # Changed from 'grade' to 'grade_name'
    weight_range: Union[str, float, int]  # Accept various numeric types
    price_per_kg: Union[str, float, int]  # Accept various numeric types
    quantity: Union[str, float, int]


class VendorQuoteData(BaseModel):
    quote_id: int
    vendor_name: str
    vendor_code: str
    country_of_origin: str
    quote_valid_till: datetime
    fish_type: str
    destinations: List[QuoteDestination]
    sizes: List[QuoteSize]
    notes: Optional[str] = None
    price_negotiable: bool = False
    exclusive_offer: bool = False
    created_at: datetime