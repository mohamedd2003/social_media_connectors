"""
Instagram Competitor Analysis – Async Apify Service
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from schemas.instagram_competitor import InstagramCompetitorResponse, LatestPost

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "apify~instagram-scraper"
POLL_INTERVAL = 2
MAX_POLL_ATTEMPTS = 60


class ApifyInstagramService:
    """Service for scraping Instagram competitor data through Apify."""

    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _post_type(item: dict) -> str:
        typename = str(item.get("type", item.get("__typename", ""))).lower()
        if "video" in typename or item.get("isVideo"):
            return "Video"
        if "sidecar" in typename or item.get("sidecarChildren"):
            return "Sidecar"
        return "Image"

    @staticmethod
    def _extract_display_url(item: dict) -> str:
        direct = (
            item.get("displayUrl")
            or item.get("display_url")
            or item.get("thumbnailUrl")
            or item.get("imageUrl")
        )
        if direct:
            return str(direct)

        images = item.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str) and first:
                return first
            if isinstance(first, dict):
                return str(
                    first.get("url")
                    or first.get("displayUrl")
                    or first.get("display_url")
                    or ""
                )

        child_posts = item.get("childPosts")
        if isinstance(child_posts, list) and child_posts:
            first_child = child_posts[0]
            if isinstance(first_child, dict):
                return str(
                    first_child.get("displayUrl")
                    or first_child.get("display_url")
                    or first_child.get("thumbnailUrl")
                    or ""
                )

        return ""

    async def scrape_competitor(self, username: str) -> InstagramCompetitorResponse:
        """Run scraper, poll until finished, then parse profile and posts."""
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
        apify_token = os.getenv("APIFY_API_TOKEN", "")
        if not apify_token:
            raise HTTPException(500, "APIFY_API_TOKEN is not configured on the backend.")

        async with httpx.AsyncClient(timeout=30) as client:
            # Required run shape from request: username + resultsLimit + enhanceUserSearchWithId
            posts_items = await self._run_posts_with_fallback(client, username, apify_token)
            profile_items = await self._run_profile_details(client, username, apify_token)

        if not posts_items and not profile_items:
            raise HTTPException(
                404,
                f"No data found for Instagram user @{username}. The profile may not exist.",
            )

        return self._parse_items(profile_items, posts_items, username)

    async def _run_posts_with_fallback(
        self,
        client: httpx.AsyncClient,
        username: str,
        token: str,
    ) -> list[dict]:
        # First attempt: required payload structure
        primary_payload = {
            "username": [username],
            "resultsLimit": 12,
            "enhanceUserSearchWithId": True,
        }
        run_id = await self._start_run(client, primary_payload, token)
        dataset_id = await self._wait_for_run(client, run_id, token, username)
        items = await self._fetch_dataset_items(client, dataset_id, token)
        if self._is_no_items(items):
            # Fallback: direct profile URL is much more reliable for this actor.
            fallback_payload = {
                "directUrls": [f"https://www.instagram.com/{username}/"],
                "resultsLimit": 12,
            }
            run_id = await self._start_run(client, fallback_payload, token)
            dataset_id = await self._wait_for_run(client, run_id, token, username)
            items = await self._fetch_dataset_items(client, dataset_id, token)

        if self._is_no_items(items):
            return []
        return items

    async def _run_profile_details(
        self,
        client: httpx.AsyncClient,
        username: str,
        token: str,
    ) -> list[dict]:
        payload = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "details",
            "resultsLimit": 1,
        }
        run_id = await self._start_run(client, payload, token)
        dataset_id = await self._wait_for_run(client, run_id, token, username)
        items = await self._fetch_dataset_items(client, dataset_id, token)
        if self._is_no_items(items):
            return []
        return items

    async def _start_run(self, client: httpx.AsyncClient, payload: dict, token: str) -> str:
        run_url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs"

        resp = await client.post(run_url, params={"token": token}, json=payload)
        if resp.status_code != 201:
            raise HTTPException(502, f"Failed to start Apify Instagram scraper: {resp.text[:220]}")

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            raise HTTPException(502, "Apify did not return a run ID for Instagram scraper.")
        return run_id

    async def _wait_for_run(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        token: str,
        username: str,
    ) -> str:
        status_url = f"{APIFY_BASE}/actor-runs/{run_id}"

        for _ in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)
            poll = await client.get(status_url, params={"token": token})
            if poll.status_code != 200:
                continue

            data = poll.json().get("data", {})
            status = data.get("status")
            if status == "SUCCEEDED":
                dataset_id = data.get("defaultDatasetId")
                if not dataset_id:
                    raise HTTPException(502, "Apify run succeeded but dataset ID is missing.")
                return dataset_id
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise HTTPException(502, f"Apify Instagram scraper {status.lower()} for @{username}.")

        raise HTTPException(
            504,
            f"Apify Instagram scraper timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s.",
        )

    async def _fetch_dataset_items(
        self,
        client: httpx.AsyncClient,
        dataset_id: str,
        token: str,
    ) -> list[dict]:
        items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        resp = await client.get(items_url, params={"token": token, "clean": "true", "format": "json"})
        if resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch Instagram dataset items from Apify.")

        items = resp.json()
        if not isinstance(items, list):
            return []
        return items

    @staticmethod
    def _is_no_items(items: list[dict]) -> bool:
        return (
            len(items) == 1
            and isinstance(items[0], dict)
            and items[0].get("error") == "no_items"
        )

    def _parse_items(
        self,
        profile_items: list[dict],
        post_items: list[dict],
        username: str,
    ) -> InstagramCompetitorResponse:
        # Profile details run has the richest account-level metrics.
        profile_source = profile_items[0] if profile_items else {}
        profile = profile_source if isinstance(profile_source, dict) else {}

        # Posts run often returns one item per post; details run may also include latestPosts.
        candidate_posts: list[dict] = []
        if post_items and isinstance(post_items[0], dict) and "id" in post_items[0]:
            candidate_posts = [p for p in post_items if isinstance(p, dict)]
        elif isinstance(profile.get("latestPosts"), list):
            candidate_posts = [p for p in profile.get("latestPosts", []) if isinstance(p, dict)]

        parsed = InstagramCompetitorResponse(
            username=str(profile.get("username") or username),
            fullName=str(profile.get("fullName") or profile.get("full_name") or ""),
            biography=str(profile.get("biography") or ""),
            followersCount=self._to_int(profile.get("followersCount", profile.get("followers", 0))),
            followsCount=self._to_int(profile.get("followsCount", profile.get("following", 0))),
            postsCount=self._to_int(profile.get("postsCount", profile.get("posts", 0))),
            profilePicUrl=str(profile.get("profilePicUrl") or profile.get("profile_pic_url") or ""),
            isVerified=bool(profile.get("isVerified", profile.get("verified", profile.get("is_verified", False)))),
            latestPosts=[],
        )

        for item in candidate_posts:
            if not isinstance(item, dict):
                continue

            post_id = str(item.get("id") or item.get("shortCode") or item.get("shortcode") or "")
            shortcode = str(item.get("shortCode") or item.get("shortcode") or "")
            post_url = str(item.get("url") or item.get("postUrl") or "")
            if not post_url and shortcode:
                post_url = f"https://www.instagram.com/p/{shortcode}/"

            display_url = self._extract_display_url(item)
            view_count_val = item.get("videoViewCount", item.get("video_play_count"))
            video_view_count = self._to_int(view_count_val) if view_count_val is not None else None

            parsed.latestPosts.append(
                LatestPost(
                    id=post_id,
                    url=post_url,
                    caption=str(item.get("caption") or item.get("text") or ""),
                    type=self._post_type(item),
                    displayUrl=display_url,
                    likeCount=self._to_int(item.get("likesCount", item.get("likes", 0))),
                    commentCount=self._to_int(item.get("commentsCount", item.get("comments", 0))),
                    videoViewCount=video_view_count if self._post_type(item) == "Video" else None,
                    timestamp=str(item.get("timestamp") or item.get("takenAt") or "") or None,
                )
            )

        return parsed
