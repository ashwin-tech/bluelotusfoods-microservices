from fastapi import APIRouter

router = APIRouter()

# Import sub-routers
from .buyers import router as buyers_router
from .estimates import router as estimates_router
from .vendors import router as vendors_router
from .clearing_charges import router as clearing_charges_router
from .buyer_estimates import router as buyer_estimates_router
from .clearing_calculator import router as clearing_calculator_router

# Include sub-routers
router.include_router(buyers_router, tags=["buyer-pricing-buyers"])
router.include_router(estimates_router, prefix="/estimates", tags=["buyer-pricing-estimates"])
router.include_router(vendors_router, prefix="/vendors", tags=["buyer-pricing-vendors"])
router.include_router(clearing_charges_router, prefix="/clearing-charges", tags=["buyer-pricing-clearing"])
router.include_router(buyer_estimates_router, prefix="/buyer-estimates", tags=["buyer-pricing-persistence"])
router.include_router(clearing_calculator_router, prefix="/clearing-calculator", tags=["buyer-pricing-calculator"])
