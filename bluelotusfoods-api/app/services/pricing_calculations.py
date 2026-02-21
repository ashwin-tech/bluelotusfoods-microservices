"""
Pricing calculation utilities for buyer pricing estimates.
"""

from decimal import Decimal
from typing import Dict, Any


def calculate_tariff_amount(fish_price: Decimal, tariff_percent: Decimal) -> Decimal:
    """
    Calculate the tariff amount based on fish price and tariff percentage.
    
    Args:
        fish_price: Price per kg of fish
        tariff_percent: Tariff percentage (e.g., 50 for 50%)
    
    Returns:
        Tariff amount in dollars
    """
    return (fish_price * tariff_percent) / Decimal('100')


def calculate_base_cost(fish_price: Decimal, tariff_percent: Decimal) -> Decimal:
    """
    Calculate the base cost (Fish Price + Tariff Amount).
    
    Args:
        fish_price: Price per kg of fish
        tariff_percent: Tariff percentage
    
    Returns:
        Base cost (fish price including tariff)
    """
    tariff_amount = calculate_tariff_amount(fish_price, tariff_percent)
    return fish_price + tariff_amount


def calculate_total_price(
    fish_price: Decimal, 
    freight_price: Decimal,
    tariff_percent: Decimal, 
    margin: Decimal
) -> Decimal:
    """
    Calculate the total price per kg.
    Formula: (Fish Price + Tariff Amount) + Freight Price + Margin
    
    Args:
        fish_price: Price per kg of fish
        freight_price: Freight/shipping price per kg
        tariff_percent: Tariff percentage
        margin: Margin amount to add
    
    Returns:
        Total price per kg
    """
    tariff_amount = calculate_tariff_amount(fish_price, tariff_percent)
    return fish_price + tariff_amount + freight_price + margin


def calculate_estimate_totals(estimate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate all pricing fields for an estimate.
    
    Args:
        estimate: Dictionary containing fish_price, freight_price, tariff_percent, margin
    
    Returns:
        Dictionary with calculated fields added:
        - tariff_amount: The dollar amount of tariff
        - base_cost: Fish price + tariff
        - total_price: (Fish price + tariff) + freight price + margin
    """
    fish_price = Decimal(str(estimate.get('fish_price', 0)))
    freight_price = Decimal(str(estimate.get('freight_price', 0)))
    tariff_percent = Decimal(str(estimate.get('tariff_percent', 0)))
    margin = Decimal(str(estimate.get('margin', 0)))
    
    tariff_amount = calculate_tariff_amount(fish_price, tariff_percent)
    base_cost = calculate_base_cost(fish_price, tariff_percent)
    total_price = calculate_total_price(fish_price, freight_price, tariff_percent, margin)
    
    return {
        **estimate,
        'tariff_amount': float(tariff_amount),
        'base_cost': float(base_cost),
        'total_price': float(total_price)
    }


def round_to_nearest_hundred(value: Decimal) -> Decimal:
    """
    Round a value to the nearest 100 using Excel-style logic.
    Formula: IF(MOD(ROUND(value,0),100)>=50, ROUNDUP(ROUND(value,0),-2), ROUNDDOWN(ROUND(value,0),-2))
    
    This checks if the remainder when dividing by 100 is >= 50, then rounds up or down accordingly.
    Used for rounding pounds (lbs) in buyer pricing calculations.
    """
    # Round to nearest integer first
    rounded = value.quantize(Decimal('1'))
    
    # Get the remainder when divided by 100
    remainder = rounded % Decimal('100')
    
    # If remainder >= 50, round up to next hundred, otherwise round down
    if remainder >= Decimal('50'):
        # Round up: add (100 - remainder)
        return rounded + (Decimal('100') - remainder)
    else:
        # Round down: subtract remainder
        return rounded - remainder


def calculate_clearing_charges_with_quantity(
    fish_price: Decimal,
    freight_price: Decimal,
    tariff_percent: Decimal,
    clearing_charges_config: Dict[str, Any],
    is_simp_applicable: bool = False,
    margin: Decimal = Decimal('0')
) -> Dict[str, Any]:
    """
    Calculate clearing charges and offer quantities for different invoice tiers.
    
    NOTE: All prices are per LB (pound), not per KG. Buyer pricing uses pounds.
    Vendor submissions are in KG and need to be converted to LBS for buyer pricing.
    
    Formula:
    - Fish Price: Price from vendor (per LB)
    - Margin: Markup amount to add to fish price
    - Markup Fish Price: Fish Price + Margin
    - Tariff is calculated on Markup Fish Price
    - Base price (no additional margin) = Markup Fish Price + Tariff Amount + Freight Price (all per LB)
    - For each tier ($10k, $20k, $30k):
      - Raw quantity = Invoice Value / Base Price (in LBS)
      - Offer Quantity = Round to nearest 100 LBS, minimum 1200 LBS
      - Fixed Clearing = Custom Entry + Airline Service + Prior Notice + Food Drug + Tariff Filing + (SIMP if applicable)
      - Customs Tax = Based on actual invoice value tier
      - Total Clearing = Fixed Clearing + Customs Tax
      - Clearing per LB = Total Clearing / Offer Quantity
      - Final Price per LB = Base Price + Clearing per LB
    
    Args:
        fish_price: Price per LB of fish (from vendor)
        freight_price: Freight price per LB
        tariff_percent: Tariff percentage
        clearing_charges_config: Dict with clearing charge values
        is_simp_applicable: Whether SIMP filing applies to this fish species
        margin: Margin amount to add to fish price
    
    Returns:
        Dictionary with three tiers (10k, 20k, 30k) each containing:
        - invoice_value, offer_quantity (in LBS), clearing_per_lb, total_price_per_lb
    """
    # Calculate Markup Fish Price (Fish Price + Margin)
    markup_fish_price = fish_price + margin
    
    # Calculate tariff on Markup Fish Price
    tariff_amount = calculate_tariff_amount(markup_fish_price, tariff_percent)
    
    # Calculate base price using Markup Fish Price
    base_price = markup_fish_price + tariff_amount + freight_price
    
    # Fixed clearing charges (not dependent on invoice value)
    fixed_clearing = (
        Decimal(str(clearing_charges_config.get('custom_entry_fee', 0))) +
        Decimal(str(clearing_charges_config.get('airline_service_fee', 0))) +
        Decimal(str(clearing_charges_config.get('prior_notice_pre_fda', 0))) +
        Decimal(str(clearing_charges_config.get('food_and_drug_service', 0))) +
        Decimal(str(clearing_charges_config.get('tariff_filing', 0)))
    )
    
    # Add SIMP filing if applicable
    if is_simp_applicable:
        fixed_clearing += Decimal(str(clearing_charges_config.get('simp_filing', 0)))
    
    tiers = {}
    
    # Define tier targets with their base customs tax
    # We'll adjust the customs tax based on actual invoice value
    tier_definitions = [
        ('tier_10k', Decimal('10000')),
        ('tier_20k', Decimal('20000')),
        ('tier_30k', Decimal('30000')),
    ]
    
    for tier_name, target_invoice in tier_definitions:
        # Calculate raw quantity needed to reach target invoice (in LBS)
        raw_quantity = target_invoice / base_price
        
        # Round to nearest 100 LBS
        offer_quantity = round_to_nearest_hundred(raw_quantity)
        
        # Cap minimum weight at 1200 LBS
        if offer_quantity < Decimal('1200'):
            offer_quantity = Decimal('1200')
        
        # Calculate actual invoice value based on adjusted quantity
        actual_invoice_value = offer_quantity * base_price
        
        # Cap maximum invoice at $30,000
        if actual_invoice_value > Decimal('30000'):
            actual_invoice_value = Decimal('30000')
            # Recalculate quantity based on capped invoice
            offer_quantity = actual_invoice_value / base_price
            offer_quantity = round_to_nearest_hundred(offer_quantity)
        
        # Select appropriate customs tax based on actual invoice value
        # $0 - $10,000: Use tier 1 customs tax ($10,000)
        # $10,001 - $20,000: Use tier 2 customs tax ($20,000)
        # $20,001 - $30,000: Use tier 3 customs tax ($30,000)
        if actual_invoice_value <= Decimal('10000'):
            customs_tax_key = 'customs_tax_per_10000'
        elif actual_invoice_value <= Decimal('20000'):
            customs_tax_key = 'customs_tax_per_20000'
        else:
            customs_tax_key = 'customs_tax_per_30000'
        
        # Get customs tax for the appropriate tier
        customs_tax = Decimal(str(clearing_charges_config.get(customs_tax_key, 0)))
        
        # Total clearing charges
        total_clearing = fixed_clearing + customs_tax
        
        # Clearing per LB
        clearing_per_lb = total_clearing / offer_quantity if offer_quantity > 0 else Decimal('0')
        
        # Final price per LB
        total_price_per_lb = base_price + clearing_per_lb
        
        tiers[tier_name] = {
            'invoice_value': float(actual_invoice_value),
            'offer_quantity_lbs': float(offer_quantity),
            'clearing_charges': float(total_clearing),
            'clearing_per_lb': float(clearing_per_lb),
            'base_price_per_lb': float(base_price),
            'total_price_per_lb': float(total_price_per_lb),
            'customs_tax_tier': customs_tax_key.replace('customs_tax_per_', '$')
        }
    
    return tiers

