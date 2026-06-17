"""
Manual Scrape Router – POST /api/manual-scrape + GET /api/proxy-image

Accepts platform + username/URL and returns scraped profile data.
Includes an image proxy to bypass CDN hotlinking restrictions.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.manual_scrape_service import manual_scrape, ScrapeResult

logger = logging.getLogger("manual_scrape_router")

router = APIRouter(prefix="/api", tags=["manual-scrape"])


class ManualScrapeRequest(BaseModel):
    platform: str = Field(..., description="Platform: tiktok, instagram, or facebook")
    username: str = Field(..., description="Username or full profile URL")


@router.post(
    "/manual-scrape",
    response_model=ScrapeResult,
    summary="Scrape a public profile using Playwright (manual alternative to Apify)",
)
async def post_manual_scrape(req: ManualScrapeRequest):
    """
    Launches a headless Playwright browser to scrape public profile data.

    Returns profile metrics (followers, likes, etc.) and recent posts/videos.
    If the platform shows a captcha or login wall, returns status='blocked_by_challenge'.
    """
    platform = req.platform.lower().strip()
    if platform not in ("tiktok", "instagram", "facebook"):
        raise HTTPException(400, f"Unsupported platform: {platform}. Use tiktok, instagram, or facebook.")

    if not req.username.strip():
        raise HTTPException(400, "Username or URL is required.")

    result = await manual_scrape(platform, req.username)
    return result


# Allowed CDN hosts for the image proxy (prevent open-redirect / SSRF)
_ALLOWED_HOSTS = (
    "instagram", "cdninstagram", "fbcdn", "scontent",
    "tiktokcdn", "tiktok", "p16-sign", "p77-sign", "p19-sign",
    "p16-common", "p16-amd", "tiktokcdn-us",
)

# 1x1 transparent PNG to return on failure so the browser doesn't show broken icon
_FALLBACK_PIXEL = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@router.get("/proxy-image", summary="Proxy an image from a social CDN")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")):
    """
    Fetches an image server-side to bypass CDN hotlinking / CORS restrictions.
    Only allows known social media CDN domains.
    Returns a transparent pixel on any failure so the frontend doesn't break.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""

    if not any(allowed in host for allowed in _ALLOWED_HOSTS):
        raise HTTPException(403, "Domain not allowed for proxying.")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Invalid URL scheme.")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "image/*,*/*;q=0.8",
                "Referer": f"{parsed.scheme}://{parsed.hostname}/",
            })

            if resp.status_code != 200:
                # Return transparent pixel instead of error so UI degrades gracefully
                return Response(
                    content=_FALLBACK_PIXEL,
                    media_type="image/png",
                    headers={"Cache-Control": "no-cache"},
                )

            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except (httpx.HTTPError, Exception) as e:
        logger.warning("Proxy image fetch failed for %s: %s", host, e)
        return Response(
            content=_FALLBACK_PIXEL,
            media_type="image/png",
            headers={"Cache-Control": "no-cache"},
        )
