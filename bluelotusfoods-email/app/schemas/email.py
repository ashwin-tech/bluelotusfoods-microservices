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

class BuyerEstimateItem(BaseModel):
    vendor_name: str
    common_name: str
    scientific_name: Optional[str] = None
    cut: str
    grade: str
    fish_size: Optional[str] = None
    port: str
    offer_quantity: float  # Weight in LBS
    fish_price: float
    margin: float
    freight_price: float
    tariff_percent: float
    clearing_charges: float  # Clearing charges
    total_price: float
    fish_species_id: int
    cut_id: int
    grade_id: int


class BuyerPricingEmailRequest(BaseModel):
    buyer_emails: List[EmailStr]
    buyer_name: str
    company_name: str
    estimate_number: str
    items: List[BuyerEstimateItem]
    delivery_date_from: Optional[str] = None
    delivery_date_to: Optional[str] = None
    notes: Optional[str] = None


class OwnerEstimateNotificationRequest(BaseModel):
    owner_email: EmailStr
    company_name: str
    estimate_number: str
    items: List[BuyerEstimateItem]
    delivery_date_from: Optional[str] = None
    delivery_date_to: Optional[str] = None


# ─── BPL Email Schemas ───────────────────────────────

class BPLPiece(BaseModel):
    piece_number: int
    weight_kg: float

class BPLBox(BaseModel):
    box_number: int
    num_pieces: int
    net_weight_kg: float
    pieces: List[BPLPiece] = []
    weight_range_from_kg: Optional[float] = None
    weight_range_to_kg: Optional[float] = None

class BPLItem(BaseModel):
    """One PO line item with its boxes"""
    fish_name: str
    cut_name: str
    grade_name: str
    fish_size: Optional[str] = None
    order_weight_kg: float
    boxes: List[BPLBox] = []

class SendBPLEmailRequest(BaseModel):
    owner_email: str
    vendor_email: str
    vendor_name: str
    vendor_country: Optional[str] = None
    po_number: str
    port_code: str
    invoice_number: Optional[str] = None
    air_way_bill: Optional[str] = None
    packed_date: Optional[str] = None
    expiry_date: Optional[str] = None
    total_boxes: int = 0
    notes: Optional[str] = None
    items: List[BPLItem]


class SendBPLUploadedEmailRequest(BaseModel):
    """For vendors who upload a document instead of entering box data manually."""
    owner_email: str
    vendor_email: str
    vendor_name: str
    vendor_country: Optional[str] = None
    po_number: str
    port_code: str
    invoice_number: Optional[str] = None
    air_way_bill: Optional[str] = None
    packed_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    attachment_bytes: str       # base64-encoded file content
    attachment_filename: str
