"""
TikTok Competitor Analysis – FastAPI Router

GET /api/v1/tiktok/competitor/{username}
  → Triggers Apify scrape, returns parsed TikTokCompetitorResponse.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Path

from schemas.tiktok_competitor import TikTokCompetitorResponse
from services.tiktok_competitor_service import scrape_competitor

logger = logging.getLogger("tiktok.competitor_router")

router = APIRouter(prefix="/api/v1/tiktok", tags=["tiktok-competitor"])

USERNAME_RE = re.compile(r"^[\w.]{1,50}$")


@router.get(
    "/competitor/{username}",
    response_model=TikTokCompetitorResponse,
    summary="Scrape full TikTok competitor profile and videos",
)
async def get_competitor(
    username: str = Path(
        ...,
        description="TikTok username to analyze (without @)",
        examples=["khaby.lame"],
    ),
):
    """
    Triggers an Apify actor run to scrape the given TikTok profile,
    waits for completion, and returns expanded profile metadata plus
    the full video list returned by the dataset.

    Typical response time: 5-30 seconds depending on Apify queue and data size.
    """
    clean = username.lstrip("@").strip()
    if not USERNAME_RE.match(clean):
        raise HTTPException(400, "Invalid TikTok username format.")

    return await scrape_competitor(clean)
