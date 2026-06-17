"""
Facebook Competitor Analysis - Apify Service
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from schemas.facebook_competitor import FacebookCompetitorResponse, LatestFacebookPost

APIFY_BASE = "https://api.apify.com/v2"
PAGES_ACTOR_ID = "apify~facebook-pages-scraper"
POSTS_ACTOR_ID = "apify~facebook-posts-scraper"
POLL_INTERVAL = 2
MAX_POLL_ATTEMPTS = 120


class FacebookCompetitorService:
    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _extract_post_type(post: dict) -> str:
        if not isinstance(post, dict):
            return "Post"

        if bool(post.get("isVideo")):
            return "Video"

        url = str(post.get("url") or post.get("postUrl") or post.get("permalink") or "").lower()
        if "/reel/" in url or "/videos/" in url:
            return "Video"

        media = post.get("media")
        if isinstance(media, list) and media:
            first_media = media[0]
            if isinstance(first_media, dict):
                typename = str(first_media.get("__typename") or "").lower()
                if "video" in typename:
                    return "Video"
                if "photo" in typename or "image" in typename:
                    return "Image"

        has_image = bool(
            post.get("full_picture")
            or post.get("fullPicture")
            or post.get("image")
            or post.get("imageUrl")
            or post.get("photo")
            or post.get("photoUrl")
            or post.get("picture")
        )
        if has_image:
            return "Image"

        message = str(post.get("text") or post.get("message") or post.get("caption") or "").strip()
        if message:
            return "Text"

        return "Post"

    async def _get_apify_token(self) -> str:
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
        token = os.getenv("APIFY_API_TOKEN", "")
        if not token:
            raise HTTPException(500, "APIFY_API_TOKEN is not configured on the backend.")
        return token

    async def _normalize_to_page_url(self, client: httpx.AsyncClient, query: str) -> str:
        """Accept username, page id, or Facebook URL/share URL and return a page URL."""
        clean = (query or "").strip()
        if not clean:
            return clean

        if not clean.startswith("http"):
            clean = clean.replace("@", "")
            return f"https://www.facebook.com/{clean}"

        final_url = clean
        try:
            resp = await client.get(clean, follow_redirects=True)
            final_url = str(resp.url)
        except Exception:
            pass

        parsed = urlparse(final_url)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0] not in {"share", "groups", "watch", "profile.php", "pages", "permalink.php"}:
            return f"https://www.facebook.com/{parts[0]}"
        if parts and parts[0] == "profile.php":
            query_pairs = dict(kv.split("=", 1) for kv in parsed.query.split("&") if "=" in kv)
            profile_id = query_pairs.get("id")
            if profile_id:
                return f"https://www.facebook.com/{profile_id}"
        return final_url

    async def _start_run(self, client: httpx.AsyncClient, actor_id: str, payload: dict, token: str) -> str:
        run_url = f"{APIFY_BASE}/acts/{actor_id}/runs"
        resp = await client.post(run_url, params={"token": token}, json=payload)
        if resp.status_code != 201:
            raise HTTPException(502, f"Failed to start Apify Facebook scraper: {resp.text[:220]}")

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            raise HTTPException(502, "Apify did not return run ID for Facebook scraper.")
        return run_id

    async def _wait_for_run(self, client: httpx.AsyncClient, run_id: str, token: str) -> str:
        status_url = f"{APIFY_BASE}/actor-runs/{run_id}"
        for _ in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)
            resp = await client.get(status_url, params={"token": token})
            if resp.status_code != 200:
                continue

            data = resp.json().get("data", {})
            status = data.get("status")
            if status == "SUCCEEDED":
                dataset_id = data.get("defaultDatasetId")
                if dataset_id:
                    return dataset_id
                raise HTTPException(502, "Apify run succeeded but dataset id is missing.")
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise HTTPException(502, f"Apify Facebook scraper {status.lower()}.")

        raise HTTPException(504, "Apify Facebook scraper timed out.")

    async def _fetch_dataset_items(self, client: httpx.AsyncClient, dataset_id: str, token: str) -> list[dict]:
        items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        resp = await client.get(items_url, params={"token": token, "clean": "true", "format": "json"})
        if resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch Apify Facebook dataset items.")

        items = resp.json()
        if not isinstance(items, list):
            return []
        return items

    @staticmethod
    def _extract_profile(items: list[dict], page_url: str) -> dict:
        first = items[0] if items else {}
        return {
            "pageId": str(first.get("pageId") or first.get("facebookId") or first.get("id") or ""),
            "name": str(first.get("title") or first.get("pageName") or first.get("name") or ""),
            "username": str(first.get("pageUsername") or first.get("username") or ""),
            "category": str(first.get("pageCategory") or first.get("category") or ""),
            "about": str(first.get("pageAbout") or first.get("about") or ""),
            "description": str(first.get("pageDescription") or first.get("description") or ""),
            "followersCount": first.get("followers") or first.get("followersCount") or first.get("pageFollowers") or 0,
            "fanCount": first.get("likes") or first.get("fanCount") or first.get("pageLikes") or 0,
            "isVerified": bool(first.get("isVerified") or first.get("pageVerified") or False),
            "profilePicture": str(first.get("profilePictureUrl") or first.get("pageProfilePicture") or first.get("profilePicture") or ""),
            "pageUrl": str(first.get("pageUrl") or page_url),
        }

    @staticmethod
    def _extract_profile_from_posts(items: list[dict], page_url: str) -> dict:
        first = items[0] if items else {}
        user = first.get("user") if isinstance(first.get("user"), dict) else {}
        return {
            "pageId": str(first.get("facebookId") or user.get("id") or ""),
            "name": str(user.get("name") or first.get("pageName") or ""),
            "username": str(first.get("pageName") or ""),
            "category": "",
            "about": "",
            "description": "",
            "followersCount": 0,
            "fanCount": 0,
            "isVerified": False,
            "profilePicture": str(user.get("profilePic") or ""),
            "pageUrl": str(first.get("facebookUrl") or page_url),
        }

    async def scrape_competitor(self, query: str) -> FacebookCompetitorResponse:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_apify_token()
            page_url = await self._normalize_to_page_url(client, query)
            pages_payload = {"startUrls": [{"url": page_url}], "resultsLimit": 1}
            posts_payload = {"startUrls": [{"url": page_url}], "resultsLimit": 12}

            page_items: list[dict] = []
            try:
                page_run_id = await self._start_run(client, PAGES_ACTOR_ID, pages_payload, token)
                page_dataset_id = await self._wait_for_run(client, page_run_id, token)
                page_items = await self._fetch_dataset_items(client, page_dataset_id, token)
            except HTTPException:
                # The page actor occasionally times out on busy queues; posts actor still works.
                page_items = []

            posts_run_id = await self._start_run(client, POSTS_ACTOR_ID, posts_payload, token)
            posts_dataset_id = await self._wait_for_run(client, posts_run_id, token)
            posts_items = await self._fetch_dataset_items(client, posts_dataset_id, token)

        if not page_items and not posts_items:
            raise HTTPException(404, f"No Facebook data found for '{query}'.")

        profile = self._extract_profile(page_items, page_url) if page_items else self._extract_profile_from_posts(posts_items, page_url)

        parsed_posts: list[LatestFacebookPost] = []
        for post in posts_items:
            if not isinstance(post, dict):
                continue

            media = post.get("media")
            media_image = ""
            if isinstance(media, list) and media:
                first_media = media[0]
                if isinstance(first_media, dict):
                    thumbnail_img = first_media.get("thumbnailImage")
                    thumbnail_uri = thumbnail_img.get("uri", "") if isinstance(thumbnail_img, dict) else ""
                    photo_image = first_media.get("photo_image")
                    photo_image_uri = photo_image.get("uri", "") if isinstance(photo_image, dict) else ""
                    full_image = first_media.get("full_image")
                    full_image_uri = full_image.get("uri", "") if isinstance(full_image, dict) else ""
                    original_image = first_media.get("original_image")
                    original_image_uri = original_image.get("uri", "") if isinstance(original_image, dict) else ""
                    media_image = str(
                        first_media.get("thumbnail")
                        or thumbnail_uri
                        or original_image_uri
                        or full_image_uri
                        or photo_image_uri
                        or first_media.get("photo")
                        or first_media.get("image")
                        or first_media.get("url")
                        or ""
                    )
                elif isinstance(first_media, str):
                    media_image = first_media

            # Fallback: check attachments structure (Graph API style)
            if not media_image:
                attachments = post.get("attachments")
                if isinstance(attachments, dict):
                    att_data = attachments.get("data") or []
                elif isinstance(attachments, list):
                    att_data = attachments
                else:
                    att_data = []
                for att in att_data:
                    if not isinstance(att, dict):
                        continue
                    att_media = att.get("media")
                    if isinstance(att_media, dict):
                        img = att_media.get("image") or att_media.get("source")
                        if isinstance(img, dict):
                            media_image = img.get("src") or img.get("uri") or img.get("url") or ""
                        elif isinstance(img, str):
                            media_image = img
                    if media_image:
                        break

            parsed_posts.append(
                LatestFacebookPost(
                    id=str(post.get("postId") or post.get("id") or ""),
                    url=str(post.get("url") or post.get("postUrl") or post.get("permalink") or ""),
                    message=str(post.get("text") or post.get("message") or post.get("caption") or ""),
                    postType=self._extract_post_type(post),
                    imageUrl=str(
                        post.get("full_picture")
                        or post.get("fullPicture")
                        or post.get("image")
                        or post.get("imageUrl")
                        or post.get("photo")
                        or post.get("photoUrl")
                        or post.get("picture")
                        or media_image
                    ),
                    createdTime=post.get("time") or post.get("timestamp") or post.get("created_time"),
                    likeCount=self._to_int(post.get("likes") or post.get("likeCount") or 0),
                    commentCount=self._to_int(post.get("comments") or post.get("commentCount") or 0),
                    shareCount=self._to_int(post.get("shares") or post.get("shareCount") or 0),
                    reactionCount=self._to_int(
                        post.get("reactions")
                        or post.get("reactionCount")
                        or post.get("likes")
                        or 0
                    ),
                )
            )

        return FacebookCompetitorResponse(
            pageId=str(profile.get("pageId", "")),
            name=str(profile.get("name", "")),
            username=str(profile.get("username", "")),
            category=str(profile.get("category", "")),
            about=str(profile.get("about", "")),
            description=str(profile.get("description", "")),
            followersCount=self._to_int(profile.get("followersCount", 0)),
            fanCount=self._to_int(profile.get("fanCount", 0)),
            isVerified=bool(profile.get("isVerified", False)),
            profilePicture=str(profile.get("profilePicture", "")),
            pageUrl=str(profile.get("pageUrl", "")),
            latestPosts=parsed_posts,
        )

    async def scrape_competitor_debug(self, query: str) -> dict:
        """Return raw Apify data for debugging field names."""
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._get_apify_token()
            page_url = await self._normalize_to_page_url(client, query)
            posts_payload = {"startUrls": [{"url": page_url}], "resultsLimit": 3}

            posts_run_id = await self._start_run(client, POSTS_ACTOR_ID, posts_payload, token)
            posts_dataset_id = await self._wait_for_run(client, posts_run_id, token)
            posts_items = await self._fetch_dataset_items(client, posts_dataset_id, token)

        return {"raw_posts": posts_items}
