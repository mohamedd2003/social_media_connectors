import os
import uuid
import httpx
import aiofiles
from fastapi import HTTPException
from .base import BaseConnector

SNAP_ADS_API = "https://adsapi.snapchat.com/v1"


class SnapchatConnector(BaseConnector):
    """Snapchat Marketing API connector – mirrors the FB/IG connector pattern."""

    # ── Insights ─────────────────────────────────────────────────────────

    async def get_insights(self, account_id: str, access_token: str):
        """
        Fetch ad-level stats for a Snapchat Ad Account.
        Returns a list shaped identically to the FB/IG connector output.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # 1. Get campaigns under this ad account
            campaigns_resp = await client.get(
                f"{SNAP_ADS_API}/adaccounts/{account_id}/campaigns",
                headers=headers,
            )
            if campaigns_resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch Snap campaigns: {campaigns_resp.text}")

            campaigns = campaigns_resp.json().get("campaigns", [])
            results = []

            for camp_wrapper in campaigns:
                camp = camp_wrapper.get("campaign", {})
                camp_id = camp.get("id")
                if not camp_id:
                    continue

                # 2. Get ad squads under each campaign
                squads_resp = await client.get(
                    f"{SNAP_ADS_API}/campaigns/{camp_id}/adsquads",
                    headers=headers,
                )
                if squads_resp.status_code != 200:
                    continue

                squads = squads_resp.json().get("adsquads", [])
                for sq_wrapper in squads:
                    squad = sq_wrapper.get("adsquad", {})
                    squad_id = squad.get("id")
                    if not squad_id:
                        continue

                    # 3. Get ads under each ad squad
                    ads_resp = await client.get(
                        f"{SNAP_ADS_API}/adsquads/{squad_id}/ads",
                        headers=headers,
                    )
                    if ads_resp.status_code != 200:
                        continue

                    ads = ads_resp.json().get("ads", [])
                    for ad_wrapper in ads:
                        ad = ad_wrapper.get("ad", {})
                        ad_id = ad.get("id")
                        if not ad_id:
                            continue

                        # 4. Get stats for this ad
                        stats_resp = await client.get(
                            f"{SNAP_ADS_API}/ads/{ad_id}/stats",
                            headers=headers,
                            params={
                                "granularity": "TOTAL",
                                "fields": "impressions,swipes,spend,conversion_purchases",
                            },
                        )
                        impressions = 0
                        swipes = 0
                        spend = 0
                        conversions = 0

                        if stats_resp.status_code == 200:
                            timeseries = stats_resp.json().get("timeseries_stats", [])
                            if timeseries:
                                ts = timeseries[0].get("timeseries_stat", {})
                                totals = ts.get("stats", {})
                                impressions = totals.get("impressions", 0)
                                swipes = totals.get("swipes", 0)
                                spend_micro = totals.get("spend", 0)
                                spend = spend_micro / 1_000_000  # micro-currency → currency
                                conversions = totals.get("conversion_purchases", 0)

                        eng_rate = None
                        if impressions:
                            eng_rate = round((swipes / impressions) * 100, 2)

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
                            "spend": spend,
                            "conversions": conversions,
                            "engagement_rate": eng_rate,
                            "platform": "snapchat",
                        })

            return results

    # ── Publish (Paid Ad Creation) ───────────────────────────────────────

    async def publish_post(self, account_id: str, access_token: str, message: str, images: list = None, **kwargs):
        """
        Programmatic paid-ad creation flow:
        1. Upload media → 2. Create Creative → 3. Create Ad Squad → 4. Create Ad
        Requires campaign_id and ad_account_id in kwargs.
        """
        campaign_id = kwargs.get("campaign_id")
        ad_account_id = kwargs.get("ad_account_id", account_id)
        base_url = kwargs.get("base_url", "http://localhost:8000/")

        if not campaign_id:
            raise HTTPException(400, "campaign_id is required for Snapchat ad creation")

        valid_images = [img for img in (images or []) if img and img.filename]
        if not valid_images:
            raise HTTPException(400, "Snapchat ads require at least one media file.")

        headers = {"Authorization": f"Bearer {access_token}"}
        saved_filepaths = []

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # ── Step 1: Upload media ─────────────────────────────────
                image = valid_images[0]
                image_data = await image.read()

                # 1a. Create media entity
                media_payload = {
                    "media": [
                        {
                            "name": message[:255] or image.filename,
                            "type": "IMAGE",
                            "ad_account_id": ad_account_id,
                        }
                    ]
                }
                media_resp = await client.post(
                    f"{SNAP_ADS_API}/adaccounts/{ad_account_id}/media",
                    headers=headers,
                    json=media_payload,
                )
                if media_resp.status_code not in (200, 201):
                    raise HTTPException(400, f"Failed to create Snap media entity: {media_resp.text}")

                media_list = media_resp.json().get("media", [])
                if not media_list:
                    raise HTTPException(400, "No media entity returned from Snapchat")
                media_obj = media_list[0].get("media", {})
                media_id = media_obj.get("id")

                # 1b. Upload the actual file bytes
                upload_resp = await client.post(
                    f"{SNAP_ADS_API}/media/{media_id}/upload",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                    files={"file": (image.filename, image_data, image.content_type)},
                )
                if upload_resp.status_code not in (200, 201):
                    raise HTTPException(400, f"Failed to upload Snap media: {upload_resp.text}")

                # ── Step 2: Create Creative ──────────────────────────────
                creative_payload = {
                    "creatives": [
                        {
                            "ad_account_id": ad_account_id,
                            "name": message[:255] or "Auto Creative",
                            "type": "SNAP_AD",
                            "top_snap_media_id": media_id,
                            "headline": message[:34] if message else "Check this out",
                            "shareable": True,
                        }
                    ]
                }
                creative_resp = await client.post(
                    f"{SNAP_ADS_API}/adaccounts/{ad_account_id}/creatives",
                    headers=headers,
                    json=creative_payload,
                )
                if creative_resp.status_code not in (200, 201):
                    raise HTTPException(400, f"Failed to create Snap creative: {creative_resp.text}")

                creatives = creative_resp.json().get("creatives", [])
                if not creatives:
                    raise HTTPException(400, "No creative returned from Snapchat")
                creative_id = creatives[0].get("creative", {}).get("id")

                # ── Step 3: Create Ad Squad ──────────────────────────────
                ad_squad_payload = {
                    "adsquads": [
                        {
                            "campaign_id": campaign_id,
                            "name": f"AdSquad - {message[:50]}" if message else "Auto AdSquad",
                            "type": "SNAP_ADS",
                            "placement_v2": {
                                "config": "AUTOMATIC",
                            },
                            "optimization_goal": "IMPRESSIONS",
                            "bid_micro": 1_000_000,  # $1.00 default bid
                            "daily_budget_micro": 20_000_000,  # $20.00 daily budget
                            "billing_event": "IMPRESSION",
                            "targeting": {
                                "geos": [{"country_code": "US"}],
                            },
                            "status": "PAUSED",
                        }
                    ]
                }
                squad_resp = await client.post(
                    f"{SNAP_ADS_API}/campaigns/{campaign_id}/adsquads",
                    headers=headers,
                    json=ad_squad_payload,
                )
                if squad_resp.status_code not in (200, 201):
                    raise HTTPException(400, f"Failed to create Snap ad squad: {squad_resp.text}")

                squads_data = squad_resp.json().get("adsquads", [])
                if not squads_data:
                    raise HTTPException(400, "No ad squad returned from Snapchat")
                squad_id = squads_data[0].get("adsquad", {}).get("id")

                # ── Step 4: Create Ad (linking creative → ad squad) ──────
                ad_payload = {
                    "ads": [
                        {
                            "ad_squad_id": squad_id,
                            "creative_id": creative_id,
                            "name": message[:255] or "Auto Ad",
                            "type": "SNAP_AD",
                            "status": "PAUSED",
                        }
                    ]
                }
                ad_resp = await client.post(
                    f"{SNAP_ADS_API}/adsquads/{squad_id}/ads",
                    headers=headers,
                    json=ad_payload,
                )
                if ad_resp.status_code not in (200, 201):
                    raise HTTPException(400, f"Failed to create Snap ad: {ad_resp.text}")

                return ad_resp.json()

        finally:
            for fp in saved_filepaths:
                try:
                    os.remove(fp)
                except OSError:
                    pass

    # ── Comments (not supported for Snap ads – return empty) ─────────────

    async def get_comments(self, post_id: str, access_token: str):
        """Snapchat ads do not have a public comments API."""
        return []

    # ── Helpers exposed to the router layer ──────────────────────────────

    async def get_organizations(self, access_token: str):
        """Fetch all Snapchat organizations the user has access to."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SNAP_ADS_API}/me/organizations",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch Snap orgs: {resp.text}")
            orgs = resp.json().get("organizations", [])
            return [
                {
                    "id": o.get("organization", {}).get("id"),
                    "name": o.get("organization", {}).get("name"),
                }
                for o in orgs
            ]

    async def get_ad_accounts(self, org_id: str, access_token: str):
        """Fetch ad accounts under a Snapchat organization."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SNAP_ADS_API}/organizations/{org_id}/adaccounts",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch Snap ad accounts: {resp.text}")
            accounts = resp.json().get("adaccounts", [])
            return [
                {
                    "id": a.get("adaccount", {}).get("id"),
                    "name": a.get("adaccount", {}).get("name"),
                    "status": a.get("adaccount", {}).get("status"),
                    "currency": a.get("adaccount", {}).get("currency"),
                }
                for a in accounts
            ]

    async def get_campaigns(self, ad_account_id: str, access_token: str):
        """Fetch campaigns under a Snapchat ad account."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SNAP_ADS_API}/adaccounts/{ad_account_id}/campaigns",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch Snap campaigns: {resp.text}")
            campaigns = resp.json().get("campaigns", [])
            return [
                {
                    "id": c.get("campaign", {}).get("id"),
                    "name": c.get("campaign", {}).get("name"),
                    "status": c.get("campaign", {}).get("status"),
                    "daily_budget_micro": c.get("campaign", {}).get("daily_budget_micro"),
                }
                for c in campaigns
            ]

    async def get_ad_squads(self, campaign_id: str, access_token: str):
        """Fetch ad squads under a Snapchat campaign."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SNAP_ADS_API}/campaigns/{campaign_id}/adsquads",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                raise HTTPException(400, f"Failed to fetch Snap ad squads: {resp.text}")
            squads = resp.json().get("adsquads", [])
            return [
                {
                    "id": s.get("adsquad", {}).get("id"),
                    "name": s.get("adsquad", {}).get("name"),
                    "status": s.get("adsquad", {}).get("status"),
                    "optimization_goal": s.get("adsquad", {}).get("optimization_goal"),
                }
                for s in squads
            ]
