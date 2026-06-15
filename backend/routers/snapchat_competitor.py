"""
Snapchat Competitor Analysis Router
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Path

from schemas.snapchat_competitor import SnapchatCompetitorResponse
from services.snapchat_competitor_service import SnapchatCompetitorService

router = APIRouter(prefix="/api/v1/snapchat", tags=["snapchat-competitor"])
service = SnapchatCompetitorService()

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,50}$")


@router.get(
    "/competitor/{username}",
    response_model=SnapchatCompetitorResponse,
    summary="Analyze a Snapchat competitor profile",
)
async def get_snapchat_competitor(
    username: str = Path(..., description="Snapchat username (without @)", examples=["snapchat"]),
):
    clean = username.strip().lstrip("@")
    if not USERNAME_RE.match(clean):
        raise HTTPException(400, "Invalid Snapchat username format.")

    return await service.scrape_competitor(clean)
