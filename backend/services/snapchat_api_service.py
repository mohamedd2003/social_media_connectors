"""
Snapchat API Service – Production-Grade Async HTTPX Client

Stateless service class for calling the Public Profile API (businessapi.snapchat.com)
and the Ads/Marketing API (adsapi.snapchat.com).

Architecture:
  SnapchatAPIService  ← stateless, takes access_token per-call
  ├─ fetch_profile_insights(profile_id, access_token, ...)
  │    → GET businessapi/v1/public_profiles/{id}             (metadata + subscriber_count)
  │    → GET businessapi/v1/public_profiles/{id}/stats       (reach, views, shares — 403/gRPC fallback)
  │    → GET businessapi/v1/public_profiles/{id}/organic/stories     (gRPC-only, graceful skip)
  │    → GET businessapi/v1/public_profiles/{id}/organic/spotlights  (gRPC-only, graceful skip)
  │
  └─ fetch_ads_reporting(ad_account_id, access_token, start_date, end_date)
       → GET adsapi/v1/adaccounts/{id}
       → GET adsapi/v1/adaccounts/{id}/campaigns
       → For each campaign:
           → GET adsapi/v1/campaigns/{id}/stats?granularity=DAY
           → GET adsapi/v1/campaigns/{id}/adsquads
           → For each ad_squad:
               → GET adsapi/v1/adsquads/{id}/stats?granularity=TOTAL

Gotchas handled:
  1. Array Payload Trap — stats come as timeseries_stats[0].timeseries_stat.timeseries[*].stats
  2. subscriber_count only from profile metadata, NOT from stats endpoint
  3. Micro-currency → real currency (÷ 1,000,000)
  4. Organic endpoints use gRPC (return 415) — graceful skip with 5s timeout
  5. DNS workaround via _ensure_dns / _api / _profile_api helpers
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from connectors.snapchat import (
    _ensure_dns,
    _api,
    _profile_api,
    _make_headers,
    _make_profile_headers,
    _snap_verify,
    _snap_profile_verify,
)
from schemas.snapchat_v2 import (
    AdEntityStats,
    AdsReportingResponse,
    CampaignReportDetail,
    DailyReportingRow,
    OrganicStoryStats,
    ProfileInfo,
    ProfileInsightsResponse,
    ProfileMetrics,
    SpotlightMetadata,
    SpotlightStats,
    StoryMetadata,
)

logger = logging.getLogger("snapchat.api_service")

# ═══════════════════════════════════════════════════════════════════════════════
# Safe extraction helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_int(val: Any, default: int = 0) -> int:
    """Coerce a value to int, returning default on None/error."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Coerce a value to float, returning default on None/error."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _micro_to_real(micro: Any) -> float:
    """Convert Snapchat micro-currency (int × 10^6) to real currency."""
    return _safe_int(micro) / 1_000_000


def _extract_timeseries_stats(raw: dict) -> dict:
    """
    Safely dig into Snapchat's nested timeseries_stats array.

    Snapchat wraps stats like:
      { "timeseries_stats": [
          { "timeseries_stat": {
              "timeseries": [
                { "start_time": "...", "stats": { "impressions": 42, ... } }
              ]
          }}
      ]}

    Returns the inner "stats" dict, or {} if anything is missing.
    """
    ts_list = raw.get("timeseries_stats", [])
    if not ts_list:
        return {}
    ts_stat = ts_list[0].get("timeseries_stat", ts_list[0])
    timeseries = ts_stat.get("timeseries", [])
    if not timeseries:
        return {}
    return timeseries[0].get("stats", {})


def _extract_timeseries_points(raw: dict) -> list[dict]:
    """
    Extract all time-series data points from the nested response.

    Returns list of {"start_time": ..., "stats": {...}} dicts.
    """
    ts_list = raw.get("timeseries_stats", [])
    if not ts_list:
        return []
    ts_stat = ts_list[0].get("timeseries_stat", ts_list[0])
    return ts_stat.get("timeseries", [])


def _unwrap_profile(raw: dict) -> dict:
    """
    Unwrap Snapchat's nested profile response.

    Handles both shapes:
      {"public_profile": {...}}
      {"public_profiles": [{"sub_request_status": "SUCCESS", "public_profile": {...}}]}
    """
    if "public_profile" in raw and isinstance(raw["public_profile"], dict):
        return raw["public_profile"]
    pp_list = raw.get("public_profiles", [])
    if pp_list:
        first = pp_list[0]
        return first.get("public_profile", first)
    return raw


# ═══════════════════════════════════════════════════════════════════════════════
# Error classification
# ═══════════════════════════════════════════════════════════════════════════════


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Translate Snapchat API errors into FastAPI HTTPExceptions."""
    if resp.status_code == 200:
        return

    status = resp.status_code
    body = resp.text[:500]

    if status == 401:
        raise HTTPException(
            401,
            f"Snapchat token expired or invalid ({context}). "
            "Re-authenticate via /snap/auth/login.",
        )
    if status == 403:
        raise HTTPException(
            403,
            f"Forbidden: missing required scope for {context}. "
            f"Response: {body}",
        )
    if status == 429:
        retry_after = resp.headers.get("Retry-After", "60")
        raise HTTPException(
            429,
            f"Rate limited by Snapchat ({context}). "
            f"Retry after {retry_after}s.",
        )
    if status == 404:
        raise HTTPException(
            404,
            f"Resource not found ({context}). Response: {body}",
        )
    if status >= 500:
        raise HTTPException(
            502,
            f"Snapchat server error {status} ({context}). Response: {body}",
        )
    raise HTTPException(status, f"Snapchat API error {status} ({context}): {body}")


def _handle_network_error(e: Exception, context: str) -> None:
    """Translate DNS/connection errors to 502."""
    msg = str(e)
    if any(s in msg for s in ("getaddrinfo", "ConnectError", "NameResolutionError")):
        raise HTTPException(
            502,
            f"DNS lookup failed ({context}). "
            "Check DNS or switch to 8.8.8.8 / 1.1.1.1.",
        )
    raise HTTPException(500, f"Network error ({context}): {msg}")


# ═══════════════════════════════════════════════════════════════════════════════
# Date helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _default_date_range(
    start_date: str | None,
    end_date: str | None,
    window_days: int = 28,
) -> tuple[str, str]:
    """
    Return (start_date, end_date) as YYYY-MM-DD strings.
    Defaults to the last `window_days` days if not provided.
    """
    now = datetime.now(timezone.utc)
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
    return start_date, end_date


# ═══════════════════════════════════════════════════════════════════════════════
# SnapchatAPIService
# ═══════════════════════════════════════════════════════════════════════════════


class SnapchatAPIService:
    """
    Stateless async service for Snapchat Marketing & Public Profile APIs.

    Each method accepts an access_token and returns a typed Pydantic model.
    Token management (refresh, storage) is handled upstream.

    Hosts:
      - Profile data  → businessapi.snapchat.com  (via _profile_api)
      - Ads data       → adsapi.snapchat.com       (via _api)
    """

    # ── Public Profile API ────────────────────────────────────────────────

    async def fetch_profile_insights(
        self,
        profile_id: str,
        access_token: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ProfileInsightsResponse:
        """
        Fetch organic insights for a Public Profile.

        Chains two required requests:
          1. GET /v1/public_profiles/{profile_id}       → metadata + subscriber_count
          2. GET /v1/public_profiles/{profile_id}/stats  → reach, views, shares, screenshots

        IMPORTANT: subscriber_count (Followers) comes ONLY from the metadata
        endpoint (#1), NOT from stats (#2). The service merges both.

        Plus two optional requests (gRPC-only, graceful skip):
          3. GET /v1/public_profiles/{profile_id}/organic/stories
          4. GET /v1/public_profiles/{profile_id}/organic/spotlights

        Handles the Array Payload Trap: stats may arrive as
        timeseries_stats[0].timeseries_stat.timeseries[*].stats
        or as a flat profile_stats dict.
        """
        await _ensure_dns()

        start_date, end_date = _default_date_range(start_date, end_date)
        start_time = f"{start_date}T00:00:00.000Z"
        end_time = f"{end_date}T23:59:59.000Z"
        headers = _make_profile_headers(access_token)

        profile_info = ProfileInfo(id=profile_id)
        metrics = ProfileMetrics(profile_id=profile_id)
        stories: list[StoryMetadata] = []
        spotlights: list[SpotlightMetadata] = []
        api_available = False
        error_msg: str | None = None

        try:
            # ── 1. Profile metadata (subscriber_count lives HERE) ────────
            async with httpx.AsyncClient(
                timeout=15.0, verify=_snap_profile_verify
            ) as client:
                meta_resp = await client.get(
                    _profile_api(f"/v1/public_profiles/{profile_id}"),
                    headers=headers,
                )

                if meta_resp.status_code == 200:
                    pp = _unwrap_profile(meta_resp.json())
                    logo_urls = pp.get("logo_urls") or {}
                    profile_info = ProfileInfo(
                        id=pp.get("id", profile_id),
                        name=pp.get("display_name", pp.get("name", "")),
                        snap_user_name=pp.get("snap_user_name"),
                        profile_picture_url=logo_urls.get("original_logo_url"),
                        bio=pp.get("bio"),
                        tier=pp.get("profile_tier"),
                        category=pp.get("internal_profile_category"),
                        subscriber_count=_safe_int(pp.get("subscriber_count")),
                        organization_id=pp.get("organization_id"),
                        website_url=pp.get("website_url"),
                        logo_urls=logo_urls or None,
                    )
                    api_available = True
                elif meta_resp.status_code in (401, 429):
                    _raise_for_status(meta_resp, "profile metadata")
                else:
                    logger.warning(
                        "Profile metadata returned %s for %s",
                        meta_resp.status_code, profile_id,
                    )

            # ── 2. Profile stats (reach, views, shares) ─────────────────
            #
            # This endpoint may return 403 or 415 (gRPC-only) for accounts
            # that haven't been fully allowlisted. We attempt with a short
            # timeout and merge whatever we get.
            #
            # CRITICAL: subscriber_count is NOT in this response.
            # It was already fetched from the metadata endpoint above.
            #
            async with httpx.AsyncClient(
                timeout=5.0, verify=_snap_profile_verify
            ) as client:
                try:
                    stats_resp = await client.get(
                        _profile_api(f"/v1/public_profiles/{profile_id}/stats"),
                        headers=headers,
                        params={"start_time": start_time, "end_time": end_time},
                    )

                    if stats_resp.status_code == 200:
                        raw_stats = stats_resp.json()
                        ps = raw_stats.get("profile_stats", raw_stats)

                        # ── Handle the Array Payload Trap ────────────────
                        # Stats can come as:
                        #   A) {"profile_stats": {"total_reach": 1, ...}}     (flat dict)
                        #   B) {"profile_stats": [{"total_reach": 1, ...}]}   (array of dicts)
                        #   C) {"timeseries_stats": [...nested...]}           (timeseries wrapper)
                        if isinstance(ps, list):
                            ps = ps[0] if ps else {}
                        if not isinstance(ps, dict):
                            ps = _extract_timeseries_stats(raw_stats)

                        metrics = ProfileMetrics(
                            profile_id=profile_id,
                            # Followers from metadata, NOT from stats
                            subscriber_count=_safe_int(profile_info.subscriber_count),
                            subscriber_change=_safe_int(ps.get("subscriber_change")),
                            total_story_views=_safe_int(
                                ps.get("total_story_views")
                                or ps.get("story_views")
                            ),
                            unique_story_viewers=_safe_int(
                                ps.get("unique_story_viewers")
                            ),
                            total_shares=_safe_int(
                                ps.get("total_shares") or ps.get("shares")
                            ),
                            total_screenshots=_safe_int(
                                ps.get("total_screenshots") or ps.get("screenshots")
                            ),
                            total_reach=_safe_int(
                                ps.get("total_reach") or ps.get("reach")
                            ),
                            total_time_viewed_ms=_safe_int(
                                ps.get("total_time_viewed_ms")
                            ),
                            avg_completion_rate=_safe_float(
                                ps.get("avg_completion_rate"), default=0.0
                            ) or None,
                        )
                    elif stats_resp.status_code in (403, 415):
                        logger.debug(
                            "Stats endpoint unavailable (%s) — gRPC-only or not allowlisted",
                            stats_resp.status_code,
                        )
                        # Carry subscriber_count from metadata
                        metrics = ProfileMetrics(
                            profile_id=profile_id,
                            subscriber_count=_safe_int(profile_info.subscriber_count),
                        )
                except httpx.TimeoutException:
                    logger.debug("Stats endpoint timed out for %s", profile_id)
                    metrics = ProfileMetrics(
                        profile_id=profile_id,
                        subscriber_count=_safe_int(profile_info.subscriber_count),
                    )

            # ── 3. Organic stories (gRPC-only, graceful skip) ───────────
            async with httpx.AsyncClient(
                timeout=5.0, verify=_snap_profile_verify
            ) as client:
                try:
                    stories_resp = await client.get(
                        _profile_api(
                            f"/v1/public_profiles/{profile_id}/organic/stories"
                        ),
                        headers=headers,
                    )
                    if stories_resp.status_code == 200:
                        for s in stories_resp.json().get("stories", []):
                            story = s.get("story", s)
                            stories.append(
                                StoryMetadata(
                                    id=story.get("id", ""),
                                    name=story.get("name"),
                                    status=story.get("status"),
                                    snap_count=_safe_int(story.get("snap_count")),
                                    created_at=story.get("created_at"),
                                    expires_at=story.get("expires_at"),
                                    media_url=story.get("media_url"),
                                    thumbnail_url=story.get("thumbnail_url"),
                                )
                            )
                    elif stories_resp.status_code in (415, 403):
                        logger.debug("Organic stories: gRPC-only (%s)", stories_resp.status_code)
                except (httpx.TimeoutException, httpx.ConnectError):
                    logger.debug("Organic stories request failed for %s", profile_id)

            # ── 4. Spotlights (gRPC-only, graceful skip) ────────────────
            async with httpx.AsyncClient(
                timeout=5.0, verify=_snap_profile_verify
            ) as client:
                try:
                    spot_resp = await client.get(
                        _profile_api(
                            f"/v1/public_profiles/{profile_id}/organic/spotlights"
                        ),
                        headers=headers,
                    )
                    if spot_resp.status_code == 200:
                        raw_spots = spot_resp.json()
                        for s in raw_spots.get(
                            "spotlights", raw_spots.get("spotlight", [])
                        ):
                            item = s.get("spotlight", s)
                            spotlights.append(
                                SpotlightMetadata(
                                    id=item.get("id", ""),
                                    name=item.get("name"),
                                    status=item.get("status"),
                                    created_at=item.get("created_at"),
                                    media_url=item.get("media_url"),
                                    thumbnail_url=item.get("thumbnail_url"),
                                    duration_ms=_safe_int(item.get("duration_ms"))
                                    or None,
                                )
                            )
                    elif spot_resp.status_code in (415, 403):
                        logger.debug("Spotlights: gRPC-only (%s)", spot_resp.status_code)
                except (httpx.TimeoutException, httpx.ConnectError):
                    logger.debug("Spotlights request failed for %s", profile_id)

            # ── Build response ──────────────────────────────────────────
            if not api_available:
                error_msg = (
                    "Profile API returned no data. "
                    "Re-authenticate with both scopes "
                    "(snapchat-marketing-api + snapchat-profile-api)."
                )
            elif not stories and not spotlights:
                error_msg = (
                    "Profile connected. Organic content endpoints use gRPC — "
                    "stories/stats may need manual entry from profile.snapchat.com."
                )

            return ProfileInsightsResponse(
                profile=profile_info,
                metrics=metrics,
                stories=stories,
                spotlight=spotlights,
                api_available=api_available,
                error=error_msg,
            )

        except HTTPException:
            raise
        except Exception as e:
            _handle_network_error(e, "fetch_profile_insights")
            raise  # unreachable — _handle_network_error always raises

    # ── Per-Story Stats ──────────────────────────────────────────────────

    async def fetch_story_stats(
        self,
        profile_id: str,
        story_id: str,
        access_token: str,
    ) -> OrganicStoryStats:
        """
        Fetch per-story organic metrics.
          GET businessapi/v1/public_profiles/{profile_id}/organic/stories/{story_id}/stats

        Note: This endpoint is gRPC-only for most accounts.
        """
        await _ensure_dns()
        headers = _make_profile_headers(access_token)

        try:
            async with httpx.AsyncClient(
                timeout=10.0, verify=_snap_profile_verify
            ) as client:
                resp = await client.get(
                    _profile_api(
                        f"/v1/public_profiles/{profile_id}"
                        f"/organic/stories/{story_id}/stats"
                    ),
                    headers=headers,
                )
                _raise_for_status(resp, f"story stats for {story_id}")

                raw = resp.json()
                ss = raw.get("story_stats", raw)

                # Handle array wrapping
                if isinstance(ss, list) and ss:
                    ss = ss[0]
                if not isinstance(ss, dict):
                    ss = _extract_timeseries_stats(raw)

                return OrganicStoryStats(
                    story_id=story_id,
                    total_views=_safe_int(ss.get("total_views")),
                    unique_viewers=_safe_int(ss.get("unique_viewers")),
                    screenshots=_safe_int(ss.get("screenshots")),
                    shares=_safe_int(ss.get("shares")),
                    total_time_viewed_ms=_safe_int(ss.get("total_time_viewed_ms")),
                    completion_rate=_safe_float(ss.get("completion_rate")) or None,
                    subscribers_gained=_safe_int(ss.get("subscribers_gained")),
                    subscribers_lost=_safe_int(ss.get("subscribers_lost")),
                )
        except HTTPException:
            raise
        except Exception as e:
            _handle_network_error(e, "fetch_story_stats")
            raise

    # ── Ads API – Campaign Reporting ─────────────────────────────────────

    async def fetch_ads_reporting(
        self,
        ad_account_id: str,
        access_token: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AdsReportingResponse:
        """
        Fetch campaign-level ad performance for the given date range.

        Walks:
          1. GET adsapi/v1/adaccounts/{id}               → account metadata
          2. GET adsapi/v1/adaccounts/{id}/campaigns      → campaign list
          3. For each campaign:
             GET adsapi/v1/campaigns/{id}/stats?granularity=DAY
          4. GET adsapi/v1/campaigns/{id}/adsquads → ad squad details
             GET adsapi/v1/adsquads/{id}/stats?granularity=TOTAL

        Handles:
          - Micro-currency conversion (spend_micro ÷ 1,000,000 = spend)
          - Safe array extraction from timeseries_stats[]
          - Default 28-day date range when start/end not provided
        """
        await _ensure_dns()
        headers = _make_headers(access_token)

        start_date, end_date = _default_date_range(start_date, end_date)
        start_time = f"{start_date}T00:00:00.000Z"
        end_time = f"{end_date}T23:59:59.000Z"

        try:
            async with httpx.AsyncClient(
                timeout=60.0, verify=_snap_verify
            ) as client:

                # ── 1. Ad Account metadata ───────────────────────────────
                acct_resp = await client.get(
                    _api(f"/adaccounts/{ad_account_id}"),
                    headers=headers,
                )
                _raise_for_status(acct_resp, "fetch ad account")

                acct_data = acct_resp.json().get("adaccounts", [{}])
                acct = (
                    acct_data[0].get("adaccount", acct_data[0])
                    if acct_data
                    else {}
                )
                acct_name = acct.get("name", "")
                currency = acct.get("currency", "USD")

                # ── 2. Campaign list ─────────────────────────────────────
                camp_resp = await client.get(
                    _api(f"/adaccounts/{ad_account_id}/campaigns"),
                    headers=headers,
                )
                _raise_for_status(camp_resp, "fetch campaigns")

                campaigns_raw = camp_resp.json().get("campaigns", [])

                campaign_reports: list[CampaignReportDetail] = []
                grand_impressions = 0
                grand_spend_micro = 0
                grand_swipes = 0
                grand_conversions = 0

                for camp_wrapper in campaigns_raw:
                    camp = camp_wrapper.get("campaign", camp_wrapper)
                    camp_id = camp.get("id")
                    if not camp_id:
                        continue

                    camp_name = camp.get("name", "")
                    camp_status = camp.get("status")
                    camp_objective = camp.get("objective")

                    # ── 3. Campaign stats (daily granularity) ────────────
                    stats_resp = await client.get(
                        _api(f"/campaigns/{camp_id}/stats"),
                        headers=headers,
                        params={
                            "granularity": "DAY",
                            "start_time": start_time,
                            "end_time": end_time,
                            "fields": (
                                "impressions,swipes,spend,video_views,"
                                "video_views_15s,screen_time_millis,"
                                "quartile_1,quartile_2,quartile_3,view_completion,"
                                "saves,shares,story_opens,"
                                "conversion_purchases,conversion_purchases_value"
                            ),
                        },
                    )

                    # Accumulate totals + build daily rows
                    camp_impressions = 0
                    camp_swipes = 0
                    camp_spend_micro = 0
                    camp_video_views = 0
                    camp_conversions = 0
                    daily_rows: list[DailyReportingRow] = []

                    if stats_resp.status_code == 200:
                        for point in _extract_timeseries_points(stats_resp.json()):
                            ds = point.get("stats", {})

                            d_imp = _safe_int(ds.get("impressions"))
                            d_swp = _safe_int(ds.get("swipes"))
                            d_spd = _safe_int(ds.get("spend"))
                            d_vv = _safe_int(ds.get("video_views"))
                            d_conv = _safe_int(ds.get("conversion_purchases"))

                            camp_impressions += d_imp
                            camp_swipes += d_swp
                            camp_spend_micro += d_spd
                            camp_video_views += d_vv
                            camp_conversions += d_conv

                            day_date = (point.get("start_time") or "")[:10]
                            if day_date:
                                daily_rows.append(
                                    DailyReportingRow(
                                        date=day_date,
                                        impressions=d_imp,
                                        swipes=d_swp,
                                        spend_micro=d_spd,
                                        spend=_micro_to_real(d_spd),
                                        video_views=d_vv,
                                        conversion_purchases=d_conv,
                                    )
                                )

                    swipe_rate = (
                        round((camp_swipes / camp_impressions) * 100, 4)
                        if camp_impressions > 0
                        else None
                    )

                    camp_totals = AdEntityStats(
                        entity_id=camp_id,
                        entity_name=camp_name,
                        entity_type="campaign",
                        status=camp_status,
                        impressions=camp_impressions,
                        swipes=camp_swipes,
                        spend_micro=camp_spend_micro,
                        spend=_micro_to_real(camp_spend_micro),
                        video_views=camp_video_views,
                        conversion_purchases=camp_conversions,
                        swipe_up_pct=swipe_rate,
                    )

                    # ── 4. Ad Squad-level stats ──────────────────────────
                    squad_stats: list[AdEntityStats] = []
                    sq_resp = await client.get(
                        _api(f"/campaigns/{camp_id}/adsquads"),
                        headers=headers,
                    )
                    if sq_resp.status_code == 200:
                        for sq_wrapper in sq_resp.json().get("adsquads", []):
                            sq = sq_wrapper.get("adsquad", sq_wrapper)
                            sq_id = sq.get("id")
                            if not sq_id:
                                continue

                            sq_stats_resp = await client.get(
                                _api(f"/adsquads/{sq_id}/stats"),
                                headers=headers,
                                params={
                                    "granularity": "TOTAL",
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "fields": (
                                        "impressions,swipes,spend,"
                                        "video_views,conversion_purchases"
                                    ),
                                },
                            )

                            sq_totals = _extract_timeseries_stats(
                                sq_stats_resp.json()
                                if sq_stats_resp.status_code == 200
                                else {}
                            )

                            sq_spend = _safe_int(sq_totals.get("spend"))
                            squad_stats.append(
                                AdEntityStats(
                                    entity_id=sq_id,
                                    entity_name=sq.get("name", ""),
                                    entity_type="adsquad",
                                    status=sq.get("status"),
                                    impressions=_safe_int(
                                        sq_totals.get("impressions")
                                    ),
                                    swipes=_safe_int(sq_totals.get("swipes")),
                                    spend_micro=sq_spend,
                                    spend=_micro_to_real(sq_spend),
                                    video_views=_safe_int(
                                        sq_totals.get("video_views")
                                    ),
                                    conversion_purchases=_safe_int(
                                        sq_totals.get("conversion_purchases")
                                    ),
                                )
                            )

                    campaign_reports.append(
                        CampaignReportDetail(
                            campaign_id=camp_id,
                            campaign_name=camp_name,
                            status=camp_status,
                            objective=camp_objective,
                            daily_budget_micro=_safe_int(
                                camp.get("daily_budget_micro")
                            )
                            or None,
                            start_time=camp.get("start_time"),
                            end_time=camp.get("end_time"),
                            totals=camp_totals,
                            daily_breakdown=daily_rows,
                            ad_squads=squad_stats,
                        )
                    )

                    grand_impressions += camp_impressions
                    grand_spend_micro += camp_spend_micro
                    grand_swipes += camp_swipes
                    grand_conversions += camp_conversions

                return AdsReportingResponse(
                    ad_account_id=ad_account_id,
                    ad_account_name=acct_name,
                    currency=currency,
                    start_date=start_date,
                    end_date=end_date,
                    total_impressions=grand_impressions,
                    total_spend=_micro_to_real(grand_spend_micro),
                    total_swipes=grand_swipes,
                    total_conversions=grand_conversions,
                    campaigns=campaign_reports,
                )

        except HTTPException:
            raise
        except Exception as e:
            _handle_network_error(e, "fetch_ads_reporting")
            raise  # unreachable
