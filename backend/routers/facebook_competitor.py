"""
Facebook Competitor Analysis Router
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from schemas.facebook_competitor import FacebookCompetitorResponse
from services.facebook_competitor_service import FacebookCompetitorService

router = APIRouter(prefix="/api/v1/facebook", tags=["facebook-competitor"])
service = FacebookCompetitorService()

@router.get(
    "/competitor/{query:path}",
    response_model=FacebookCompetitorResponse,
    summary="Analyze a Facebook competitor page",
)
async def get_facebook_competitor(
    query: str = Path(..., description="Facebook page username/name/id/url", examples=["nike"]),
):
    clean = query.strip()
    if len(clean) < 2:
        raise HTTPException(400, "Invalid Facebook page query format.")
    return await service.scrape_competitor(clean)
