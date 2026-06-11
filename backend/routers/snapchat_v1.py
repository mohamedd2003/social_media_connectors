"""
Snapchat Analytics API Router  —  /api/v1/snapchat/*

Production-ready endpoints for the Snapchat dashboard:
  • GET /api/v1/snapchat/profile-insights/{profile_id}
  • GET /api/v1/snapchat/profile-insights/{profile_id}/stories/{story_id}/stats
  • GET /api/v1/snapchat/ads-insights/{ad_account_id}

Uses the SnapchatAPIService (async httpx) to call the Snapchat Marketing
& Public Profile APIs.  Token refresh is handled by ensure_fresh_token().

Error handling:
  401 → Expired/invalid token (re-auth required)
  403 → Missing scope (enable at kit.snapchat.com)
  429 → Rate limited (Retry-After)
  404 → Resource not found
  502 → DNS blocked or Snapchat server error
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database import get_account
from schemas.snapchat_v2 import (
    AdsReportingResponse,
    OrganicStoryStats,
    ProfileInsightsResponse,
)
from services.snapchat_api_service import SnapchatAPIService
from services.snapchat_service import ensure_fresh_token

logger = logging.getLogger("snapchat.v1_router")

router = APIRouter(prefix="/api/v1/snapchat", tags=["snapchat-v1"])

# Single shared service instance (stateless, no constructor state)
_service = SnapchatAPIService()


# ═══════════════════════════════════════════════════════════════════════════════
# Dependency: resolve account + auto-refresh token
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_fresh_token(account_id: str) -> str:
    """
    Validate the Snapchat account exists, then return a fresh access_token.

    ensure_fresh_token() proactively refreshes the token if a refresh_token
    is available (Snapchat access tokens expire every ~30 min).
    """
    account = get_account(account_id)
    if not account or account.get("type") != "snapchat":
        raise HTTPException(404, "Snapchat account not found in database")
    return await ensure_fresh_token(account_id)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/snapchat/profile-insights/{profile_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/profile-insights/{profile_id}",
    response_model=ProfileInsightsResponse,
    summary="Organic profile metrics & content",
    description=(
        "Fetches organic insights for a Snapchat Public Profile: "
        "subscriber count, story views, reach, shares, screenshots, "
        "plus lists of active stories and spotlight content. "
        "Requires the `snapchat-profiles-api` OAuth scope."
    ),
)
async def get_profile_insights(
    profile_id: str,
    account_id: str = Query(
        ...,
        description="Snapchat account ID stored in the database (used to retrieve access_token)",
    ),
) -> ProfileInsightsResponse:
    """
    Public Profile API → organic metrics.

    Internally calls:
      - GET /v1/public_profiles/{profile_id}
      - GET /v1/public_profiles/{profile_id}/stats
      - GET /v1/public_profiles/{profile_id}/organic/stories
      - GET /v1/public_profiles/{profile_id}/organic/spotlights
    """
    access_token = await _get_fresh_token(account_id)
    return await _service.fetch_profile_insights(profile_id, access_token)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/snapchat/profile-insights/{profile_id}/stories/{story_id}/stats
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/profile-insights/{profile_id}/stories/{story_id}/stats",
    response_model=OrganicStoryStats,
    summary="Per-story organic stats",
    description="Fetch detailed view/engagement metrics for a single organic story.",
)
async def get_story_stats(
    profile_id: str,
    story_id: str,
    account_id: str = Query(...),
) -> OrganicStoryStats:
    """
    Public Profile API → per-story metrics.

    Internally calls:
      - GET /v1/public_profiles/{profile_id}/organic/stories/{story_id}/stats
    """
    access_token = await _get_fresh_token(account_id)
    return await _service.fetch_story_stats(profile_id, story_id, access_token)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/v1/snapchat/ads-insights/{ad_account_id}
# ═══════════════════════════════════════════════════════════════════════════════


@router.get(
    "/ads-insights/{ad_account_id}",
    response_model=AdsReportingResponse,
    summary="Paid ads campaign reporting",
    description=(
        "Fetches paid-ad performance for a Snapchat Ad Account over a date range. "
        "Returns per-campaign totals + daily breakdown + optional ad-squad drilldown. "
        "Requires the `snapchat-marketing-api` OAuth scope."
    ),
)
async def get_ads_insights(
    ad_account_id: str,
    account_id: str = Query(
        ...,
        description="Snapchat account ID from the database (used to retrieve access_token)",
    ),
    start_date: str = Query(
        default=None,
        description="Start date in YYYY-MM-DD format. Defaults to 28 days ago.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
    end_date: str = Query(
        default=None,
        description="End date in YYYY-MM-DD format. Defaults to today.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
) -> AdsReportingResponse:
    """
    Ads API → campaign performance reporting.

    Internally calls:
      - GET /v1/adaccounts/{ad_account_id}
      - GET /v1/adaccounts/{ad_account_id}/campaigns
      - GET /v1/campaigns/{id}/stats?granularity=DAY
      - GET /v1/campaigns/{id}/adsquads
      - GET /v1/adsquads/{id}/stats?granularity=TOTAL
    """
    # Default date range: last 28 days
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (now - timedelta(days=28)).strftime("%Y-%m-%d")

    access_token = await _get_fresh_token(account_id)
    return await _service.fetch_ads_reporting(
        ad_account_id, access_token, start_date, end_date,
    )
