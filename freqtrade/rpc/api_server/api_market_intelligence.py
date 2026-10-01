from fastapi import APIRouter, Depends

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.market_intelligence import (
    MarketIntelligenceResponse,
    build_market_intelligence,
)


router = APIRouter()


@router.get(
    "/market_intelligence",
    response_model=MarketIntelligenceResponse,
    tags=["Market intelligence"],
)
def market_intelligence(config=Depends(get_config)):
    """Return normalized market intelligence without claiming unavailable providers are live."""
    return build_market_intelligence(config)
