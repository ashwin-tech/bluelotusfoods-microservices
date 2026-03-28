"""
Pricing calculation utilities for buyer pricing estimates.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
import re

# Canonical conversion factor: 1 kg = 2.205 lbs
KG_TO_LBS = Decimal('2.205')


def kg_to_lbs(kg: Decimal) -> Decimal:
    """Convert kilograms to pounds."""
    return kg * KG_TO_LBS


def lbs_to_kg(lbs: Decimal) -> Decimal:
    """Convert pounds to kilograms."""
    return lbs / KG_TO_LBS


def convert_fish_size_to_lbs(fish_size: Optional[str]) -> Optional[str]:
    """
    Convert a fish size string from kg to lbs (no unit suffix in output).
    Examples:
      "2-3 kg" -> "4.4-6.6"
      "0.5 kg" -> "1.1"
      "45"     -> "99.2"
      "5+ kg"  -> "11.0+"
    """
    if not fish_size:
        return None

    s = str(fish_size).strip()

    range_match = re.match(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(?:kg)?', s.lower())
    if range_match:
        min_lbs = float(range_match.group(1)) * float(KG_TO_LBS)
        max_lbs = float(range_match.group(2)) * float(KG_TO_LBS)
        return f"{min_lbs:.1f}-{max_lbs:.1f}"

    plus_match = re.match(r'(\d+\.?\d*)\s*\+\s*(?:kg)?', s.lower())
    if plus_match:
        lbs = float(plus_match.group(1)) * float(KG_TO_LBS)
        return f"{lbs:.1f}+"

    single_match = re.match(r'(\d+\.?\d*)\s*(?:kg)?$', s.lower())
    if single_match:
        lbs = float(single_match.group(1)) * float(KG_TO_LBS)
        return f"{lbs:.1f}"

    return s


def _dec(config: Dict[str, Any], key: str) -> Decimal:
    """Convert a config value to Decimal safely."""
    return Decimal(str(config.get(key, 0)))


def calculate_tariff_amount(fish_price: Decimal, tariff_percent: Decimal) -> Decimal:
    """
    Calculate the tariff amount based on fish price and tariff percentage.
    Tariff is always calculated on fish_price only (not on margin).

    Args:
        fish_price: Price per lb of fish
        tariff_percent: Tariff percentage (e.g., 50 for 50%)

    Returns:
        Tariff amount in dollars
    """
    return (fish_price * tariff_percent) / Decimal('100')


def calculate_fish_price_with_tariff(fish_price: Decimal, tariff_percent: Decimal) -> Decimal:
    """
    Calculate Fish Price + Tariff Amount.

    Args:
        fish_price: Price per lb of fish
        tariff_percent: Tariff percentage

    Returns:
        fish_price_with_tariff = fish_price + tariff_amount
    """
    return fish_price + calculate_tariff_amount(fish_price, tariff_percent)


def calculate_total_price(
    fish_price: Decimal,
    freight_price: Decimal,
    tariff_percent: Decimal,
    margin: Decimal
) -> Decimal:
    """
    Calculate the total price per lb.
    Formula: total = fish_price_with_tariff + margin + freight_price

    Args:
        fish_price: Price per lb of fish
        freight_price: Freight/shipping price per lb
        tariff_percent: Tariff percentage
        margin: Margin amount (added after tariff)

    Returns:
        Total price per lb
    """
    fish_price_with_tariff = calculate_fish_price_with_tariff(fish_price, tariff_percent)
    total = fish_price_with_tariff + margin + freight_price
    return total


def calculate_estimate_totals(estimate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate all pricing fields for an estimate.

    Args:
        estimate: Dictionary containing fish_price, freight_price, tariff_percent, margin

    Returns:
        Dictionary with calculated fields added:
        - tariff_amount: The dollar amount of tariff
        - base_cost: fish_price_with_tariff (fish price + tariff)
        - total_price: fish_price_with_tariff + margin + freight_price
    """
    fish_price = Decimal(str(estimate.get('fish_price', 0)))
    freight_price = Decimal(str(estimate.get('freight_price', 0)))
    tariff_percent = Decimal(str(estimate.get('tariff_percent', 0)))
    margin = Decimal(str(estimate.get('margin', 0)))

    tariff_amount = calculate_tariff_amount(fish_price, tariff_percent)
    fish_price_with_tariff = fish_price + tariff_amount
    total = fish_price_with_tariff + margin + freight_price

    return {
        **estimate,
        'tariff_amount': float(tariff_amount),
        'base_cost': float(fish_price_with_tariff),
        'total_price': float(total)
    }


def round_to_nearest_hundred(value: Decimal) -> Decimal:
    """
    Round a value to the nearest 100 using Excel-style logic.
    Formula: IF(MOD(ROUND(value,0),100)>=50, ROUNDUP(ROUND(value,0),-2), ROUNDDOWN(ROUND(value,0),-2))

    This checks if the remainder when dividing by 100 is >= 50, then rounds up or down accordingly.
    Used for rounding pounds (lbs) in buyer pricing calculations.
    """
    rounded = value.quantize(Decimal('1'))
    remainder = rounded % Decimal('100')

    if remainder >= Decimal('50'):
        return rounded + (Decimal('100') - remainder)
    else:
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
    - fish_price_with_tariff = Fish Price + Tariff Amount (tariff on fish only, not on margin)
    - total = fish_price_with_tariff + Margin + Freight Price (price per LB before clearing)
    - For each tier ($10k, $20k, $30k):
      - Raw quantity = Invoice Value / total (in LBS)
      - Offer Quantity = Round to nearest 100 LBS, minimum 1200 LBS
      - Fixed Clearing = Custom Entry + Airline Service + Prior Notice + Food Drug + Tariff Filing + (SIMP if applicable)
      - Customs Tax = Based on actual invoice value tier
      - Total Clearing = Fixed Clearing + Customs Tax
      - Clearing per LB = Total Clearing / Offer Quantity
      - Final Price per LB = total + Clearing per LB

    Args:
        fish_price: Price per LB of fish (from vendor)
        freight_price: Freight price per LB
        tariff_percent: Tariff percentage
        clearing_charges_config: Dict with clearing charge values
        is_simp_applicable: Whether SIMP filing applies to this fish species
        margin: Margin amount (added after tariff)

    Returns:
        Dictionary with three tiers (10k, 20k, 30k) each containing:
        - invoice_value, offer_quantity (in LBS), clearing_per_lb, total_price_per_lb
    """
    # total = fish_price_with_tariff + margin + freight (price per LB before clearing)
    total = calculate_total_price(fish_price, freight_price, tariff_percent, margin)

    # Fixed clearing charges (not dependent on invoice value)
    fixed_clearing = (
        _dec(clearing_charges_config, 'custom_entry_fee') +
        _dec(clearing_charges_config, 'airline_service_fee') +
        _dec(clearing_charges_config, 'prior_notice_pre_fda') +
        _dec(clearing_charges_config, 'food_and_drug_service') +
        _dec(clearing_charges_config, 'tariff_filing')
    )

    if is_simp_applicable:
        fixed_clearing += _dec(clearing_charges_config, 'simp_filing')

    tiers = {}

    tier_definitions = [
        ('tier_10k', Decimal('10000')),
        ('tier_20k', Decimal('20000')),
        ('tier_30k', Decimal('30000')),
    ]

    for tier_name, target_invoice in tier_definitions:
        raw_quantity = target_invoice / total
        offer_quantity = round_to_nearest_hundred(raw_quantity)

        if offer_quantity < Decimal('1200'):
            offer_quantity = Decimal('1200')

        actual_invoice_value = offer_quantity * total

        if actual_invoice_value > Decimal('30000'):
            actual_invoice_value = Decimal('30000')
            offer_quantity = round_to_nearest_hundred(actual_invoice_value / total)

        if actual_invoice_value <= Decimal('10000'):
            customs_tax_key = 'customs_tax_per_10000'
        elif actual_invoice_value <= Decimal('20000'):
            customs_tax_key = 'customs_tax_per_20000'
        else:
            customs_tax_key = 'customs_tax_per_30000'

        customs_tax = _dec(clearing_charges_config, customs_tax_key)
        total_clearing = fixed_clearing + customs_tax
        clearing_per_lb = total_clearing / offer_quantity if offer_quantity > 0 else Decimal('0')

        tiers[tier_name] = {
            'invoice_value': float(actual_invoice_value),
            'offer_quantity_lbs': float(offer_quantity),
            'clearing_charges': float(total_clearing),
            'clearing_per_lb': float(clearing_per_lb),
            'base_price_per_lb': float(total),
            'total_price_per_lb': float(total + clearing_per_lb),
            'customs_tax_tier': customs_tax_key.replace('customs_tax_per_', '$')
        }

    return tiers
