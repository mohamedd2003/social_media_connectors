"""
Snapchat Marketing API Connector

Async HTTP client for:
  - Ads API:           adsapi.snapchat.com/v1/       (campaigns, ad accounts, media, stats)
  - Public Profile API: businessapi.snapchat.com/     (profiles, stories, spotlight, metrics)
    • Public endpoints:     /public/v1/public_profiles/...
    • Authorized endpoints: /v1/public_profiles/...

Uses httpx for non-blocking HTTP calls.

Architecture:
- Module-level DNS workaround (resolves via Google DoH if local DNS blocks the API)
- Module-level helpers: _api(), _profile_api(), _make_headers(), _ensure_dns()
- SnapchatConnector class with methods for each API resource
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Optional

import httpx
from fastapi import HTTPException

from .base import BaseConnector

logger = logging.getLogger("snapchat.connector")

SNAP_ADS_API = "https://adsapi.snapchat.com/v1"
SNAP_ADS_HOST = "adsapi.snapchat.com"

# Public Profile API uses a different host
SNAP_PROFILE_API = "https://businessapi.snapchat.com"
SNAP_PROFILE_HOST = "businessapi.snapchat.com"


# ═══════════════════════════════════════════════════════════════════════════════
# DNS Workaround (for ad-blocked / DNS-filtered environments)
# ═══════════════════════════════════════════════════════════════════════════════

_snap_api_base: Optional[str] = None
_snap_profile_api_base: Optional[str] = None
_snap_extra_headers: dict = {}
_snap_profile_extra_headers: dict = {}
_snap_verify: bool = True
_snap_profile_verify: bool = True


async def _resolve_host_ip(host: str) -> str:
    """Resolve a hostname via Google DNS-over-HTTPS, bypassing local DNS."""
    async with httpx.AsyncClient(timeout=10.0) as dns_client:
        r = await dns_client.get(
            "https://dns.google/resolve",
            params={"name": host, "type": "A"},
        )
        data = r.json()
        for ans in data.get("Answer", []):
            if ans.get("type") == 1:
                return ans["data"]
    raise RuntimeError(f"Could not resolve {host} via Google DNS")


async def _ensure_dns() -> None:
    """
    If local DNS blocks adsapi.snapchat.com or businessapi.snapchat.com,
    resolve via Google DoH and configure requests to use the real IP directly.
    Called once on first API request, result is cached globally.
    """
    global _snap_api_base, _snap_extra_headers, _snap_verify
    global _snap_profile_api_base, _snap_profile_extra_headers, _snap_profile_verify

    # ── Ads API (adsapi.snapchat.com) ──
    if _snap_api_base is None:
        try:
            info = socket.getaddrinfo(SNAP_ADS_HOST, 443, socket.AF_INET)
            ip = info[0][4][0] if info else None
            if ip and ip not in ("0.0.0.0", "127.0.0.1"):
                _snap_api_base = SNAP_ADS_API
            else:
                raise socket.gaierror("blocked")
        except socket.gaierror:
            real_ip = await _resolve_host_ip(SNAP_ADS_HOST)
            _snap_api_base = f"https://{real_ip}/v1"
            _snap_extra_headers = {"Host": SNAP_ADS_HOST}
            _snap_verify = False
            logger.warning("DNS blocked for %s, using IP %s", SNAP_ADS_HOST, real_ip)

    # ── Profile API (businessapi.snapchat.com) ──
    if _snap_profile_api_base is None:
        try:
            info = socket.getaddrinfo(SNAP_PROFILE_HOST, 443, socket.AF_INET)
            ip = info[0][4][0] if info else None
            if ip and ip not in ("0.0.0.0", "127.0.0.1"):
                _snap_profile_api_base = SNAP_PROFILE_API
            else:
                raise socket.gaierror("blocked")
        except socket.gaierror:
            try:
                real_ip = await _resolve_host_ip(SNAP_PROFILE_HOST)
                _snap_profile_api_base = f"https://{real_ip}"
                _snap_profile_extra_headers = {"Host": SNAP_PROFILE_HOST}
                _snap_profile_verify = False
                logger.warning("DNS blocked for %s, using IP %s", SNAP_PROFILE_HOST, real_ip)
            except Exception:
                # Fallback: use adsapi host for profile calls (may not work)
                _snap_profile_api_base = SNAP_PROFILE_API
                logger.warning("Could not resolve %s, using hostname directly", SNAP_PROFILE_HOST)


def _api(path: str) -> str:
    """Build a full Ads API URL (adsapi.snapchat.com/v1/...)."""
    return f"{_snap_api_base}{path}"


def _profile_api(path: str) -> str:
    """Build a full Profile API URL (businessapi.snapchat.com/...)."""
    return f"{_snap_profile_api_base}{path}"


def _make_headers(access_token: str) -> dict:
    """Build Authorization header + any DNS-bypass Host header for Ads API."""
    h = {"Authorization": f"Bearer {access_token}"}
    h.update(_snap_extra_headers)
    return h


def _make_profile_headers(access_token: str) -> dict:
    """Build Authorization header + any DNS-bypass Host header for Profile API."""
    h = {"Authorization": f"Bearer {access_token}"}
    h.update(_snap_profile_extra_headers)
    return h


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: try primary endpoint, fallback to legacy
# ═══════════════════════════════════════════════════════════════════════════════


async def _get_with_fallback(
    client: httpx.AsyncClient,
    headers: dict,
    primary: str,
    fallback: str,
    use_profile_api: bool = False,
) -> httpx.Response:
    """Try primary endpoint first; if non-200, try fallback.
    When use_profile_api=True, uses businessapi.snapchat.com instead of adsapi."""
    url_fn = _profile_api if use_profile_api else _api
    resp = await client.get(url_fn(primary), headers=headers)
    if resp.status_code != 200 and fallback:
        resp = await client.get(url_fn(fallback), headers=headers)
    return resp


# ═══════════════════════════════════════════════════════════════════════════════
# SnapchatConnector
# ═══════════════════════════════════════════════════════════════════════════════


class SnapchatConnector(BaseConnector):
    """Snapchat Marketing API connector – mirrors the FB/IG connector pattern."""

    # ── Ad-Level Insights ────────────────────────────────────────────────

    async def get_insights(self, account_id: str, access_token: str) -> list[dict]:
        """
        Fetch ad-level stats for a Snapchat Ad Account.

        Walks: ad_account → campaigns → ad_squads → ads → stats
        Returns a list shaped identically to the FB/IG connector output.
        """
        await _ensure_dns()
        headers = _make_headers(access_token)
        results: list[dict] = []

        async with httpx.AsyncClient(timeout=60.0, verify=_snap_verify) as client:
            # 1. Campaigns
            camp_resp = await client.get(
                _api(f"/adaccounts/{account_id}/campaigns"), headers=headers
            )
            if camp_resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch campaigns: {camp_resp.text}")

            for camp_wrapper in camp_resp.json().get("campaigns", []):
                camp = camp_wrapper.get("campaign", {})
                camp_id = camp.get("id")
                if not camp_id:
                    continue

                # 2. Ad Squads
                sq_resp = await client.get(
                    _api(f"/campaigns/{camp_id}/adsquads"), headers=headers
                )
                if sq_resp.status_code != 200:
                    continue

                for sq_wrapper in sq_resp.json().get("adsquads", []):
                    squad_id = sq_wrapper.get("adsquad", {}).get("id")
                    if not squad_id:
                        continue

                    # 3. Ads
                    ads_resp = await client.get(
                        _api(f"/adsquads/{squad_id}/ads"), headers=headers
                    )
                    if ads_resp.status_code != 200:
                        continue

                    for ad_wrapper in ads_resp.json().get("ads", []):
                        ad = ad_wrapper.get("ad", {})
                        ad_id = ad.get("id")
                        if not ad_id:
                            continue

                        # 4. Stats
                        stats_resp = await client.get(
                            _api(f"/ads/{ad_id}/stats"),
                            headers=headers,
                            params={
                                "granularity": "TOTAL",
                                "fields": "impressions,swipes,spend,conversion_purchases",
                            },
                        )

                        impressions = swipes = spend_micro = conversions = 0
                        if stats_resp.status_code == 200:
                            ts = stats_resp.json().get("timeseries_stats", [])
                            if ts:
                                totals = ts[0].get("timeseries_stat", {}).get("stats", {})
                                impressions = totals.get("impressions", 0)
                                swipes = totals.get("swipes", 0)
                                spend_micro = totals.get("spend", 0)
                                conversions = totals.get("conversion_purchases", 0)

                        eng_rate = round((swipes / impressions) * 100, 2) if impressions else None
                        results.append({
                            "id": ad_id,
                            "caption": ad.get("name", ""),
                            "created_time": ad.get("created_at"),
                            "likes": 0,
                            "comments": 0,
                            "shares": 0,
                            "saves": 0,
                            "impressions": impressions,
                            "reach": None,
                            "swipes": swipes,
                            "spend": spend_micro / 1_000_000,
                            "conversions": conversions,
                            "engagement_rate": eng_rate,
                            "platform": "snapchat",
                        })
        return results

    # ── Publish (Paid Ad Creation) ───────────────────────────────────────

    async def publish_post(
        self,
        account_id: str,
        access_token: str,
        message: str,
        images: list = None,
        **kwargs,
    ) -> dict:
        """
        Full paid-ad creation pipeline:
        1. Upload media → 2. Create Creative → 3. Create Ad Squad → 4. Create Ad
        """
        campaign_id = kwargs.get("campaign_id")
        ad_account_id = kwargs.get("ad_account_id", account_id)

        if not campaign_id:
            raise HTTPException(400, "campaign_id is required for Snapchat ad creation")

        valid_images = [img for img in (images or []) if img and img.filename]
        if not valid_images:
            raise HTTPException(400, "Snapchat ads require at least one media file.")

        await _ensure_dns()
        headers = _make_headers(access_token)

        async with httpx.AsyncClient(timeout=120.0, verify=_snap_verify) as client:
            image = valid_images[0]
            image_data = await image.read()

            # Step 1: Create media entity
            media_resp = await client.post(
                _api(f"/adaccounts/{ad_account_id}/media"),
                headers=headers,
                json={"media": [{"name": message[:255] or image.filename, "type": "IMAGE", "ad_account_id": ad_account_id}]},
            )
            if media_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to create media entity: {media_resp.text}")

            media_list = media_resp.json().get("media", [])
            if not media_list:
                raise HTTPException(400, "No media entity returned from Snapchat")
            media_id = media_list[0].get("media", {}).get("id")

            # Step 2: Upload file bytes
            upload_resp = await client.post(
                _api(f"/media/{media_id}/upload"),
                headers=_make_headers(access_token),
                files={"file": (image.filename, image_data, image.content_type)},
            )
            if upload_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to upload media: {upload_resp.text}")

            # Step 3: Create Creative
            creative_resp = await client.post(
                _api(f"/adaccounts/{ad_account_id}/creatives"),
                headers=headers,
                json={"creatives": [{
                    "ad_account_id": ad_account_id,
                    "name": message[:255] or "Auto Creative",
                    "type": "SNAP_AD",
                    "top_snap_media_id": media_id,
                    "headline": message[:34] if message else "Check this out",
                    "shareable": True,
                }]},
            )
            if creative_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to create creative: {creative_resp.text}")

            creatives = creative_resp.json().get("creatives", [])
            if not creatives:
                raise HTTPException(400, "No creative returned")
            creative_id = creatives[0].get("creative", {}).get("id")

            # Step 4: Create Ad Squad
            squad_resp = await client.post(
                _api(f"/campaigns/{campaign_id}/adsquads"),
                headers=headers,
                json={"adsquads": [{
                    "campaign_id": campaign_id,
                    "name": f"AdSquad - {message[:50]}" if message else "Auto AdSquad",
                    "type": "SNAP_ADS",
                    "placement_v2": {"config": "AUTOMATIC"},
                    "optimization_goal": "IMPRESSIONS",
                    "bid_micro": 1_000_000,
                    "daily_budget_micro": 20_000_000,
                    "billing_event": "IMPRESSION",
                    "targeting": {"geos": [{"country_code": "US"}]},
                    "status": "PAUSED",
                }]},
            )
            if squad_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to create ad squad: {squad_resp.text}")

            squads = squad_resp.json().get("adsquads", [])
            if not squads:
                raise HTTPException(400, "No ad squad returned")
            squad_id = squads[0].get("adsquad", {}).get("id")

            # Step 5: Create Ad
            ad_resp = await client.post(
                _api(f"/adsquads/{squad_id}/ads"),
                headers=headers,
                json={"ads": [{
                    "ad_squad_id": squad_id,
                    "creative_id": creative_id,
                    "name": message[:255] or "Auto Ad",
                    "type": "SNAP_AD",
                    "status": "PAUSED",
                }]},
            )
            if ad_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to create ad: {ad_resp.text}")
            return ad_resp.json()

    # ── Comments (not supported) ─────────────────────────────────────────

    async def get_comments(self, post_id: str, access_token: str) -> list:
        return []

    # ── Organizations ────────────────────────────────────────────────────

    async def get_organizations(self, access_token: str) -> list[dict]:
        """GET /v1/me/organizations"""
        await _ensure_dns()
        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.get(_api("/me/organizations"), headers=_make_headers(access_token))
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch orgs: {resp.text}")
            return [
                {"id": o.get("organization", {}).get("id"), "name": o.get("organization", {}).get("name")}
                for o in resp.json().get("organizations", [])
            ]

    # ── Ad Accounts ──────────────────────────────────────────────────────

    async def get_ad_accounts(self, org_id: str, access_token: str) -> list[dict]:
        """GET /v1/organizations/{org_id}/adaccounts"""
        await _ensure_dns()
        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.get(
                _api(f"/organizations/{org_id}/adaccounts"), headers=_make_headers(access_token)
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch ad accounts: {resp.text}")
            return [
                {
                    "id": a.get("adaccount", {}).get("id"),
                    "name": a.get("adaccount", {}).get("name"),
                    "status": a.get("adaccount", {}).get("status"),
                    "currency": a.get("adaccount", {}).get("currency"),
                }
                for a in resp.json().get("adaccounts", [])
            ]

    # ── Campaigns ────────────────────────────────────────────────────────

    async def get_campaigns(self, ad_account_id: str, access_token: str) -> list[dict]:
        """GET /v1/adaccounts/{ad_account_id}/campaigns"""
        await _ensure_dns()
        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.get(
                _api(f"/adaccounts/{ad_account_id}/campaigns"), headers=_make_headers(access_token)
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch campaigns: {resp.text}")
            return [
                {
                    "id": c.get("campaign", {}).get("id"),
                    "name": c.get("campaign", {}).get("name"),
                    "status": c.get("campaign", {}).get("status"),
                    "daily_budget_micro": c.get("campaign", {}).get("daily_budget_micro"),
                }
                for c in resp.json().get("campaigns", [])
            ]

    # ── Ad Squads ────────────────────────────────────────────────────────

    async def get_ad_squads(self, campaign_id: str, access_token: str) -> list[dict]:
        """GET /v1/campaigns/{campaign_id}/adsquads"""
        await _ensure_dns()
        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.get(
                _api(f"/campaigns/{campaign_id}/adsquads"), headers=_make_headers(access_token)
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch ad squads: {resp.text}")
            return [
                {
                    "id": s.get("adsquad", {}).get("id"),
                    "name": s.get("adsquad", {}).get("name"),
                    "status": s.get("adsquad", {}).get("status"),
                    "optimization_goal": s.get("adsquad", {}).get("optimization_goal"),
                }
                for s in resp.json().get("adsquads", [])
            ]

    # ── Create Campaign ──────────────────────────────────────────────────

    async def create_campaign(
        self,
        ad_account_id: str,
        access_token: str,
        name: str,
        status: str = "PAUSED",
        daily_budget_micro: int = 20_000_000,
        start_time: Optional[str] = None,
    ) -> dict:
        """POST /v1/adaccounts/{ad_account_id}/campaigns"""
        await _ensure_dns()
        from datetime import datetime, timezone

        if not start_time:
            start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        payload = {"campaigns": [{
            "name": name,
            "ad_account_id": ad_account_id,
            "status": status,
            "daily_budget_micro": daily_budget_micro,
            "start_time": start_time,
        }]}

        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.post(
                _api(f"/adaccounts/{ad_account_id}/campaigns"),
                headers=_make_headers(access_token),
                json=payload,
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to create campaign: {resp.text}")

            campaigns = resp.json().get("campaigns", [])
            if not campaigns:
                raise HTTPException(400, "No campaign returned")
            camp = campaigns[0]
            if camp.get("sub_request_status") == "ERROR":
                raise HTTPException(400, camp.get("sub_request_error_reason", "Campaign creation failed"))
            if isinstance(camp, dict) and "campaign" in camp:
                camp = camp["campaign"]
            return {"id": camp.get("id"), "name": camp.get("name"), "status": camp.get("status")}

    # ── Delete Media ─────────────────────────────────────────────────────

    async def delete_media(self, media_id: str, access_token: str) -> dict:
        """DELETE /v1/media/{media_id}"""
        await _ensure_dns()
        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.delete(_api(f"/media/{media_id}"), headers=_make_headers(access_token))
            if resp.status_code not in (200, 204):
                raise HTTPException(400, f"Failed to delete media: {resp.text}")
            return {"status": "ok", "message": "Media deleted successfully"}

    # ═══════════════════════════════════════════════════════════════════════
    # Public Profile Endpoints
    # Uses businessapi.snapchat.com for profile data
    # Public endpoints:     /public/v1/public_profiles/...
    # Authorized endpoints: /v1/public_profiles/...
    # Fallback: adsapi.snapchat.com /v1/organizations/{org_id}/public_profiles
    # ═══════════════════════════════════════════════════════════════════════

    async def get_public_profiles(self, org_id: str, access_token: str) -> list[dict]:
        """
        Fetch public profile data from businessapi.snapchat.com.
        Priority:
        1. /v1/public_profiles/{id} (direct lookup, needs profile scope)
        2. /v1/organizations/{org_id}/public_profiles (org listing, needs profile scope)
        3. SNAP_PROFILE_ID env var as stub fallback
        """
        await _ensure_dns()

        from dotenv import load_dotenv
        load_dotenv(override=True)
        env_profile_id = os.getenv("SNAP_PROFILE_ID")
        headers = _make_profile_headers(access_token)

        # 1. Direct profile lookup via businessapi
        if env_profile_id:
            try:
                async with httpx.AsyncClient(timeout=15.0, verify=_snap_profile_verify) as client:
                    resp = await client.get(
                        _profile_api(f"/v1/public_profiles/{env_profile_id}"),
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        raw = resp.json()
                        pp_list = raw.get("public_profiles", [])
                        if pp_list:
                            pp = pp_list[0].get("public_profile", pp_list[0])
                            return [{
                                "id": pp.get("id", env_profile_id),
                                "name": pp.get("display_name", pp.get("name", "")),
                                "snap_user_name": pp.get("snap_user_name"),
                                "profile_picture_url": (pp.get("logo_urls") or {}).get("original_logo_url"),
                                "subscriber_count": pp.get("subscriber_count"),
                                "profile_tier": pp.get("profile_tier"),
                                "internal_profile_category": pp.get("internal_profile_category"),
                                "logo_urls": pp.get("logo_urls"),
                            }]
                    else:
                        logger.debug("Direct profile lookup returned %s", resp.status_code)
            except Exception as e:
                logger.debug("businessapi direct profile lookup failed: %s", e)

        # 2. Org-level listing via businessapi
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=_snap_profile_verify) as client:
                resp = await client.get(
                    _profile_api(f"/v1/organizations/{org_id}/public_profiles"),
                    headers={**headers, "Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    profiles = []
                    for p in resp.json().get("public_profiles", []):
                        pp = p.get("public_profile", p)
                        profiles.append({
                            "id": pp.get("id"),
                            "name": pp.get("display_name", pp.get("name", "")),
                            "snap_user_name": pp.get("snap_user_name"),
                            "profile_picture_url": (pp.get("logo_urls") or {}).get("original_logo_url"),
                            "subscriber_count": pp.get("subscriber_count"),
                            "profile_tier": pp.get("profile_tier"),
                            "internal_profile_category": pp.get("internal_profile_category"),
                            "logo_urls": pp.get("logo_urls"),
                        })
                    if profiles:
                        return profiles
        except Exception as e:
            logger.debug("businessapi org profile listing failed: %s", e)

        # 3. Final fallback: use SNAP_PROFILE_ID from .env as stub
        if env_profile_id:
            logger.info("Using SNAP_PROFILE_ID from .env: %s", env_profile_id)
            return [{"id": env_profile_id, "name": "mohamed miraf", "profile_picture_url": None}]
        return []

    async def get_profile_stories(self, org_id: str, access_token: str) -> dict:
        """Fetch stories via businessapi.snapchat.com.
        
        Note: The /organic/stories endpoint uses gRPC internally (returns 415 for
        REST requests). Until a gRPC client is implemented, this returns empty.
        """
        await _ensure_dns()
        profiles = await self.get_public_profiles(org_id, access_token)
        if not profiles:
            return {"profiles": [], "stories": [], "error": "No Public Profile linked to this organization."}

        headers = _make_profile_headers(access_token)
        all_stories: list[dict] = []

        # The organic/stories endpoint is gRPC-only (returns 415 for REST).
        # Try with a short timeout; if it fails, return empty gracefully.
        async with httpx.AsyncClient(timeout=5.0, verify=_snap_profile_verify) as client:
            for profile in profiles:
                pid = profile.get("id")
                if not pid:
                    continue
                try:
                    resp = await client.get(
                        _profile_api(f"/v1/public_profiles/{pid}/organic/stories"),
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        for s in resp.json().get("stories", []):
                            story = s.get("story", s)
                            all_stories.append({
                                "id": story.get("id"),
                                "name": story.get("name", ""),
                                "status": story.get("status"),
                                "created_at": story.get("created_at"),
                                "expires_at": story.get("expires_at"),
                                "media_url": story.get("media_url"),
                                "thumbnail_url": story.get("thumbnail_url"),
                                "profile_id": pid,
                                "profile_name": profile.get("name"),
                            })
                    elif resp.status_code in (415, 403):
                        logger.debug("Organic stories endpoint not available (gRPC-only): %s", resp.status_code)
                        break
                except Exception as e:
                    logger.debug("get_profile_stories failed: %s", e)
                    break
        return {"profiles": profiles, "stories": all_stories}

    async def get_profile_spotlight(self, org_id: str, access_token: str) -> dict:
        """Fetch spotlight via businessapi.snapchat.com.
        
        Note: The /organic/spotlights endpoint uses gRPC internally (returns 415).
        """
        await _ensure_dns()
        profiles = await self.get_public_profiles(org_id, access_token)
        if not profiles:
            return {"profiles": [], "spotlight": [], "error": "No Public Profile linked."}

        headers = _make_profile_headers(access_token)
        all_spotlight: list[dict] = []

        async with httpx.AsyncClient(timeout=5.0, verify=_snap_profile_verify) as client:
            for profile in profiles:
                pid = profile.get("id")
                if not pid:
                    continue
                try:
                    resp = await client.get(
                        _profile_api(f"/v1/public_profiles/{pid}/organic/spotlights"),
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        raw = resp.json().get("spotlights", resp.json().get("spotlight", []))
                        for s in raw:
                            item = s.get("spotlight", s)
                            all_spotlight.append({
                                "id": item.get("id"),
                                "name": item.get("name", ""),
                                "status": item.get("status"),
                                "created_at": item.get("created_at"),
                                "media_url": item.get("media_url"),
                                "thumbnail_url": item.get("thumbnail_url"),
                                "view_count": item.get("view_count"),
                                "profile_id": pid,
                            })
                    elif resp.status_code in (415, 403):
                        logger.debug("Spotlight endpoint not available (gRPC-only): %s", resp.status_code)
                        break
                except Exception as e:
                    logger.debug("get_profile_spotlight failed: %s", e)
                    break
        return {"profiles": profiles, "spotlight": all_spotlight}

    async def get_profile_promotions(self, org_id: str, ad_account_id: str, access_token: str) -> list[dict]:
        """Fetch campaigns as promotions."""
        await _ensure_dns()
        headers = _make_headers(access_token)
        promotions: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            resp = await client.get(
                _api(f"/adaccounts/{ad_account_id}/campaigns"), headers=headers
            )
            if resp.status_code == 200:
                for c in resp.json().get("campaigns", []):
                    camp = c.get("campaign", c)
                    promotions.append({
                        "id": camp.get("id"),
                        "name": camp.get("name", ""),
                        "status": camp.get("status"),
                        "objective": camp.get("objective"),
                        "created_at": camp.get("created_at"),
                        "start_time": camp.get("start_time"),
                        "end_time": camp.get("end_time"),
                        "daily_budget_micro": camp.get("daily_budget_micro"),
                    })
        return promotions

    async def get_profile_insights(self, org_id: str, access_token: str) -> dict:
        """Fetch profile-level insights via businessapi.snapchat.com."""
        await _ensure_dns()
        profiles = await self.get_public_profiles(org_id, access_token)
        if not profiles:
            return {"profiles": [], "insights": {}, "error": "No Public Profile linked."}

        headers = _make_profile_headers(access_token)
        insights: dict = {}

        async with httpx.AsyncClient(timeout=30.0, verify=_snap_profile_verify) as client:
            for profile in profiles:
                pid = profile.get("id")
                if not pid:
                    continue

                # Stories count
                story_resp = await _get_with_fallback(
                    client, headers,
                    primary=f"/v1/public_profiles/{pid}/organic/stories",
                    fallback=f"/public/v1/public_profiles/{pid}/stories",
                    use_profile_api=True,
                )
                story_count = len(story_resp.json().get("stories", [])) if story_resp.status_code == 200 else 0

                # Spotlight count
                spot_resp = await _get_with_fallback(
                    client, headers,
                    primary=f"/v1/public_profiles/{pid}/organic/spotlights",
                    fallback=f"/public/v1/public_profiles/{pid}/spotlights",
                    use_profile_api=True,
                )
                spot_count = 0
                if spot_resp.status_code == 200:
                    data = spot_resp.json()
                    spot_count = len(data.get("spotlights", data.get("spotlight", [])))

                # Profile stats
                stat_resp = await _get_with_fallback(
                    client, headers,
                    primary=f"/public/v1/public_profiles/{pid}/stats",
                    fallback=f"/v1/public_profiles/{pid}/stats",
                    use_profile_api=True,
                )
                stats = stat_resp.json() if stat_resp.status_code == 200 else {}

                insights[pid] = {
                    "profile_name": profile.get("name"),
                    "story_count": story_count,
                    "spotlight_count": spot_count,
                    "stats": stats,
                }
        return {"profiles": profiles, "insights": insights}

    # ── Stories (combined: public profile + ad account media) ─────────────

    async def get_stories(self, org_id: str, ad_account_id: str, access_token: str) -> list[dict]:
        """Fetch organic stories + ad account media."""
        await _ensure_dns()
        headers = _make_headers(access_token)
        stories: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
            # Public Profile stories (via businessapi.snapchat.com)
            profiles = await self.get_public_profiles(org_id, access_token)
            async with httpx.AsyncClient(timeout=30.0, verify=_snap_profile_verify) as profile_client:
                for profile in profiles:
                    pid = profile.get("id")
                    if not pid:
                        continue
                    resp = await _get_with_fallback(
                        profile_client, _make_profile_headers(access_token),
                        primary=f"/v1/public_profiles/{pid}/organic/stories",
                        fallback=f"/public/v1/public_profiles/{pid}/stories",
                        use_profile_api=True,
                    )
                    if resp.status_code == 200:
                        for s in resp.json().get("stories", []):
                            story = s.get("story", s)
                            stories.append({
                                "id": story.get("id"),
                                "name": story.get("name", ""),
                                "status": story.get("status"),
                                "created_at": story.get("created_at"),
                                "expires_at": story.get("expires_at"),
                                "profile_id": pid,
                                "profile_name": profile.get("name"),
                            })

            # Ad account media (via adsapi.snapchat.com)
            media_resp = await client.get(
                _api(f"/adaccounts/{ad_account_id}/media"), headers=headers
            )
            if media_resp.status_code == 200:
                for m in media_resp.json().get("media", []):
                    media = m.get("media", m)
                    image_meta = media.get("image_metadata") or {}
                    stories.append({
                        "id": media.get("id"),
                        "name": media.get("name", ""),
                        "type": media.get("type", ""),
                        "status": media.get("media_status"),
                        "created_at": media.get("created_at"),
                        "download_link": media.get("download_link"),
                        "file_name": media.get("file_name"),
                        "file_size_in_bytes": media.get("file_size_in_bytes"),
                        "width_px": image_meta.get("width_px"),
                        "height_px": image_meta.get("height_px"),
                        "image_format": image_meta.get("image_format"),
                        "visibility": media.get("visibility"),
                        "media_usages": media.get("media_usages", []),
                        "source": "media",
                    })
        return stories

    async def create_story(
        self,
        org_id: str,
        ad_account_id: str,
        access_token: str,
        caption: str,
        image_data: bytes,
        filename: str,
        content_type: str,
    ) -> dict:
        """Upload media to ad account, then try to post story on Public Profile."""
        await _ensure_dns()
        headers = _make_headers(access_token)

        async with httpx.AsyncClient(timeout=120.0, verify=_snap_verify) as client:
            media_type = "IMAGE" if "image" in content_type else "VIDEO"
            media_resp = await client.post(
                _api(f"/adaccounts/{ad_account_id}/media"),
                headers=headers,
                json={"media": [{"name": caption[:255] or filename, "type": media_type, "ad_account_id": ad_account_id}]},
            )
            if media_resp.status_code not in (200, 201):
                err = media_resp.text
                if "E0001" in err or "not supported" in err:
                    raise HTTPException(400, "Cannot upload — ad account is PENDING. Complete billing at business.snapchat.com.")
                raise HTTPException(400, f"Failed to create media: {err}")

            media_list = media_resp.json().get("media", [])
            if not media_list:
                raise HTTPException(400, "No media entity returned")
            media_obj = media_list[0].get("media", media_list[0])
            media_id = media_obj.get("id")

            # Upload bytes
            upload_resp = await client.post(
                _api(f"/media/{media_id}/upload"),
                headers=_make_headers(access_token),
                files={"file": (filename, image_data, content_type)},
            )
            if upload_resp.status_code not in (200, 201):
                raise HTTPException(400, f"Failed to upload media: {upload_resp.text}")

            # Try posting to Public Profile
            profiles = await self.get_public_profiles(org_id, access_token)
            if profiles:
                pid = profiles[0]["id"]
                story_resp = await client.post(
                    _api(f"/public_profiles/{pid}/organic/stories"),
                    headers=headers,
                    json={"stories": [{"name": caption[:255] or "Story", "media_id": media_id}]},
                )
                if story_resp.status_code in (200, 201):
                    return {"status": "ok", "message": "Story posted to Public Profile!", "media_id": media_id, "response": story_resp.json()}

            return {"status": "ok", "message": "Media uploaded. No linked Public Profile for story posting.", "media_id": media_id}

    # ── Profile Overview (Dashboard Aggregation) ─────────────────────────

    async def get_profile_overview(
        self,
        org_id: str,
        ad_account_id: str,
        access_token: str,
        me_info: dict,
    ) -> dict:
        """
        Single aggregated call for the dashboard.
        Returns: profile details, overview metrics, stories, spotlight, counts.

        Endpoints used:
        - /organizations/{org_id}         → org name
        - /organizations/{org_id}/public_profiles → profile check
        - /profiles/{profile_id}/stories  → public stories
        - /profiles/{profile_id}/spotlights → spotlight
        - /profiles/{profile_id}/stats    → followers, reach, views
        - /adaccounts/{id}/media          → saved stories (ad media)
        - /adaccounts/{id}/campaigns      → campaign count
        """
        await _ensure_dns()
        headers = _make_headers(access_token)

        # Profile details from /me
        profile = {
            "user_id": me_info.get("id"),
            "display_name": me_info.get("display_name"),
            "username": me_info.get("email", "").split("@")[0] if me_info.get("email") else None,
            "email": me_info.get("email"),
            "organization_id": org_id,
            "profile_type": "Organization Admin",
            "avatar_url": None,
            "public_profile_id": None,
            "public_profile_name": None,
        }

        # Org name
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=_snap_verify) as client:
                org_resp = await client.get(_api(f"/organizations/{org_id}"), headers=headers)
                if org_resp.status_code == 200:
                    org_data = org_resp.json().get("organizations", [])
                    if org_data:
                        org = org_data[0].get("organization", org_data[0])
                        profile["organization_name"] = org.get("name")
        except Exception:
            pass

        # Public Profile check
        api_available = False
        public_stories: list[dict] = []
        spotlight_items: list[dict] = []
        profiles = await self.get_public_profiles(org_id, access_token)
        if profiles:
            profile["public_profile_id"] = profiles[0].get("id")
            profile["public_profile_name"] = profiles[0].get("name")
            profile["avatar_url"] = profiles[0].get("profile_picture_url")
            profile["snap_user_name"] = profiles[0].get("snap_user_name")
            profile["profile_tier"] = profiles[0].get("profile_tier")
            profile["logo_urls"] = profiles[0].get("logo_urls")

            stories_data = await self.get_profile_stories(org_id, access_token)
            public_stories = stories_data.get("stories", [])

            spot_data = await self.get_profile_spotlight(org_id, access_token)
            spotlight_items = spot_data.get("spotlight", [])

            # Mark api_available if we got real profile data from the API
            # (snap_user_name is only set when the API returns real data, not env fallback)
            got_real_profile = bool(profiles[0].get("snap_user_name") or profiles[0].get("logo_urls"))
            api_available = got_real_profile or bool(public_stories or spotlight_items)

        # Ad account media (saved stories) + campaign count
        saved_stories: list[dict] = []
        campaigns_count = 0
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
                media_resp = await client.get(_api(f"/adaccounts/{ad_account_id}/media"), headers=headers)
                if media_resp.status_code == 200:
                    for m in media_resp.json().get("media", []):
                        media = m.get("media", m)
                        image_meta = media.get("image_metadata") or {}
                        saved_stories.append({
                            "id": media.get("id"),
                            "name": media.get("name", ""),
                            "type": media.get("type", ""),
                            "status": media.get("media_status"),
                            "created_at": media.get("created_at"),
                            "download_link": media.get("download_link"),
                            "file_name": media.get("file_name"),
                            "file_size_in_bytes": media.get("file_size_in_bytes"),
                            "width_px": image_meta.get("width_px"),
                            "height_px": image_meta.get("height_px"),
                            "image_format": image_meta.get("image_format"),
                            "visibility": media.get("visibility"),
                            "source": "media",
                        })

                camp_resp = await client.get(_api(f"/adaccounts/{ad_account_id}/campaigns"), headers=headers)
                if camp_resp.status_code == 200:
                    campaigns_count = len(camp_resp.json().get("campaigns", []))
        except Exception:
            pass

        # Overview metrics via businessapi.snapchat.com
        metrics = {
            "total_followers": {"current": 0, "previous_28d": 0, "change_pct": None},
            "total_reach": {"current": 0, "previous_28d": 0, "change_pct": None},
            "profile_views": {"current": 0, "previous_28d": 0, "change_pct": None},
        }
        if profiles:
            pid = profiles[0].get("id")
            # Use subscriber_count from profile discovery if available
            sub_count = profiles[0].get("subscriber_count")
            if sub_count:
                metrics["total_followers"]["current"] = int(sub_count)
            try:
                async with httpx.AsyncClient(timeout=5.0, verify=_snap_profile_verify) as client:
                    # Try the stats endpoint — may return 415 (gRPC) or 403
                    stat_resp = await client.get(
                        _profile_api(f"/v1/public_profiles/{pid}/stats"),
                        headers=_make_profile_headers(access_token),
                    )
                    if stat_resp.status_code == 200:
                        ps = stat_resp.json().get("profile_stats", stat_resp.json())
                        metrics["total_followers"]["current"] = (
                            int(ps.get("subscriber_count", 0) or ps.get("followers", 0) or ps.get("total_followers", 0))
                        )
                        metrics["total_reach"]["current"] = ps.get("reach", 0) or ps.get("total_reach", 0)
                        metrics["profile_views"]["current"] = (
                            ps.get("views", 0) or ps.get("profile_views", 0) or ps.get("story_views", 0)
                        )
            except Exception:
                pass

        error_msg = None
        if not api_available:
            error_msg = (
                "Profile API returned no data. "
                "Re-authenticate with both scopes (snapchat-marketing-api + snapchat-profile-api) "
                "by clicking the Re-authenticate button above."
            )
        elif not public_stories and not spotlight_items:
            # Profile metadata works but organic content endpoints use gRPC (not yet supported)
            error_msg = (
                "Profile connected. Organic stories/stats endpoints use gRPC — "
                "metrics may need manual entry. Use Edit Manual Metrics to enter values from profile.snapchat.com."
            )

        return {
            "profile": profile,
            "metrics": metrics,
            "public_stories": public_stories,
            "saved_stories": saved_stories,
            "spotlight": spotlight_items,
            "campaigns_count": campaigns_count,
            "media_count": len(saved_stories),
            "api_available": api_available,
            "error": error_msg,
        }
