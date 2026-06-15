"""
Instagram Competitor Analysis Router
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response

from schemas.instagram_competitor import InstagramCompetitorResponse
from services.instagram_competitor_service import ApifyInstagramService

router = APIRouter(prefix="/api/v1/instagram", tags=["instagram-competitor"])
service = ApifyInstagramService()

USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
ALLOWED_IMAGE_HOSTS = (
    "cdninstagram.com",
    "fbcdn.net",
    "instagram.com",
)


@router.get("/media/proxy", summary="Proxy Instagram post image")
async def proxy_instagram_media(
    url: str = Query(..., description="Direct Instagram CDN media URL"),
):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not parsed.scheme.startswith("http") or not any(host.endswith(h) for h in ALLOWED_IMAGE_HOSTS):
        raise HTTPException(400, "Invalid media URL host.")

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://www.instagram.com/",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(502, "Failed to fetch Instagram image.")

    media_type = resp.headers.get("Content-Type", "image/jpeg")
    return Response(content=resp.content, media_type=media_type)


@router.get(
    "/competitor/{username}",
    response_model=InstagramCompetitorResponse,
    summary="Scrape an Instagram competitor profile and latest posts",
)
async def get_instagram_competitor(
    username: str = Path(..., description="Instagram username (without @)", examples=["instagram"]),
):
    clean = username.strip().lstrip("@")
    if not USERNAME_RE.match(clean):
        raise HTTPException(400, "Invalid Instagram username format.")

    return await service.scrape_competitor(clean)
