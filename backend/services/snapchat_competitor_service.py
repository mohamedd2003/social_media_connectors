"""
Snapchat Competitor Analysis - Apify Service
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from schemas.snapchat_competitor import LatestSnapPost, SnapchatCompetitorResponse

APIFY_BASE = "https://api.apify.com/v2"
PROFILE_ACTOR_ID = os.getenv("APIFY_SNAPCHAT_PROFILE_ACTOR_ID", "automation-lab~snapchat-scraper")
SPOTLIGHT_ACTOR_ID = os.getenv("APIFY_SNAPCHAT_SPOTLIGHT_ACTOR_ID", "easyapi~snapchat-user-spotlight-scraper")
POLL_INTERVAL = 2
MAX_POLL_ATTEMPTS = 60


class SnapchatCompetitorService:
    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _first_str(sources: list[dict], keys: tuple[str, ...], default: str = "") -> str:
        for src in sources:
            if not isinstance(src, dict):
                continue
            for key in keys:
                val = src.get(key)
                if val is not None and str(val).strip() != "":
                    return str(val)
        return default

    @staticmethod
    def _first_int(sources: list[dict], keys: tuple[str, ...], default: int = 0) -> int:
        for src in sources:
            if not isinstance(src, dict):
                continue
            for key in keys:
                val = src.get(key)
                if val is not None and str(val).strip() != "":
                    try:
                        return int(val)
                    except (TypeError, ValueError):
                        continue
        return default

    async def _get_apify_token(self) -> str:
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
        token = os.getenv("APIFY_API_TOKEN", "")
        if not token:
            raise HTTPException(500, "APIFY_API_TOKEN is not configured on the backend.")
        return token

    async def _start_run(self, client: httpx.AsyncClient, actor_id: str, payload: dict, token: str) -> str:
        run_url = f"{APIFY_BASE}/acts/{actor_id}/runs"
        resp = await client.post(run_url, params={"token": token}, json=payload)
        if resp.status_code != 201:
            raise HTTPException(
                502,
                f"Failed to start Apify Snapchat scraper ({actor_id}): {resp.text[:220]}",
            )

        run_id = resp.json().get("data", {}).get("id")
        if not run_id:
            raise HTTPException(502, f"Apify did not return run ID for actor {actor_id}.")
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
                raise HTTPException(502, f"Apify Snapchat scraper {status.lower()}.")

        raise HTTPException(504, "Apify Snapchat scraper timed out.")

    async def _fetch_dataset_items(self, client: httpx.AsyncClient, dataset_id: str, token: str) -> list[dict]:
        items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
        resp = await client.get(items_url, params={"token": token, "clean": "true", "format": "json"})
        if resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch Apify Snapchat dataset items.")

        items = resp.json()
        if not isinstance(items, list):
            return []
        return [row for row in items if isinstance(row, dict)]

    async def _run_profile_actor(self, client: httpx.AsyncClient, username: str, token: str) -> list[dict]:
        payloads = [
            {"usernames": [username]},
            {"username": username},
            {"profiles": [username]},
        ]
        last_error: Exception | None = None

        for payload in payloads:
            try:
                run_id = await self._start_run(client, PROFILE_ACTOR_ID, payload, token)
                dataset_id = await self._wait_for_run(client, run_id, token)
                items = await self._fetch_dataset_items(client, dataset_id, token)
                if items:
                    return items
            except Exception as exc:
                last_error = exc

        if isinstance(last_error, HTTPException):
            raise last_error
        return []

    async def _run_spotlight_actor(self, client: httpx.AsyncClient, username: str, token: str) -> list[dict]:
        payloads = [
            {"username": username},
            {"usernames": [username]},
        ]
        last_error: Exception | None = None

        for payload in payloads:
            try:
                run_id = await self._start_run(client, SPOTLIGHT_ACTOR_ID, payload, token)
                dataset_id = await self._wait_for_run(client, run_id, token)
                items = await self._fetch_dataset_items(client, dataset_id, token)
                if items:
                    return items
            except Exception as exc:
                last_error = exc

        if isinstance(last_error, HTTPException):
            raise last_error
        return []

    @staticmethod
    def _extract_profile(items: list[dict], username: str) -> dict:
        first = items[0] if items else {}
        user = first.get("user") if isinstance(first.get("user"), dict) else {}
        profile = first.get("profile") if isinstance(first.get("profile"), dict) else {}
        author = first.get("author") if isinstance(first.get("author"), dict) else {}
        sources = [profile, user, author, first]

        resolved_username = SnapchatCompetitorService._first_str(
            sources,
            ("username", "userName", "snapUserName", "handle"),
            username,
        ).lstrip("@")

        return {
            "username": resolved_username,
            "displayName": SnapchatCompetitorService._first_str(
                sources,
                ("displayName", "fullName", "name", "title"),
                resolved_username,
            ),
            "bio": SnapchatCompetitorService._first_str(sources, ("bio", "about", "description"), ""),
            "isVerified": bool(
                SnapchatCompetitorService._first_int(sources, ("isVerified", "verified"), 0)
            ),
            "followersCount": SnapchatCompetitorService._first_int(
                sources,
                ("followersCount", "subscriberCount", "subscribersCount", "subscribers", "followers", "fans"),
                0,
            ),
            "friendsCount": SnapchatCompetitorService._first_int(
                sources,
                ("friendsCount", "followingCount", "following", "friends"),
                0,
            ),
            "snapScore": SnapchatCompetitorService._first_int(sources, ("snapScore", "score"), 0),
            "profilePicture": SnapchatCompetitorService._first_str(
                sources,
                ("profilePictureUrl", "profilePicUrl", "avatar", "avatarUrl", "image"),
                "",
            ),
            "profileUrl": SnapchatCompetitorService._first_str(
                sources,
                ("url", "profileUrl", "publicUrl", "pageUrl"),
                f"https://www.snapchat.com/add/{resolved_username}",
            ),
        }

    def _extract_posts(self, items: list[dict], target_username: str) -> list[LatestSnapPost]:
        posts: list[LatestSnapPost] = []
        target = (target_username or "").strip().lstrip("@").lower()
        for row in items:
            video_meta = row.get("videoMetadata") if isinstance(row.get("videoMetadata"), dict) else {}
            engagement = row.get("engagementStats") if isinstance(row.get("engagementStats"), dict) else {}
            creator = video_meta.get("creator") if isinstance(video_meta.get("creator"), dict) else {}
            person_creator = creator.get("personCreator") if isinstance(creator.get("personCreator"), dict) else {}

            row_username = str(row.get("username") or "").strip().lstrip("@").lower()
            creator_username = str(person_creator.get("username") or "").strip().lstrip("@").lower()
            if target and row_username and row_username != target and creator_username != target:
                continue
            if target and not row_username and creator_username and creator_username != target:
                continue

            media = row.get("media")
            media_image = ""
            media_video = ""
            if isinstance(media, dict):
                media_image = str(media.get("thumbnail") or media.get("imageUrl") or media.get("url") or "")
                media_video = str(media.get("videoUrl") or "")
            elif isinstance(media, list) and media:
                first = media[0]
                if isinstance(first, dict):
                    media_image = str(first.get("thumbnail") or first.get("imageUrl") or first.get("url") or "")
                    media_video = str(first.get("videoUrl") or "")

            post_url = str(
                row.get("deeplink")
                or row.get("url")
                or row.get("postUrl")
                or row.get("storyUrl")
                or person_creator.get("url")
                or ""
            )
            created_time = (
                row.get("createdTime")
                or row.get("timestamp")
                or row.get("time")
                or video_meta.get("uploadDate")
            )

            post = LatestSnapPost(
                id=str(
                    row.get("id")
                    or row.get("postId")
                    or row.get("storyId")
                    or row.get("deeplink")
                    or video_meta.get("contentUrl")
                    or post_url
                    or created_time
                    or ""
                ),
                url=post_url,
                caption=str(
                    row.get("description")
                    or row.get("caption")
                    or row.get("text")
                    or video_meta.get("description")
                    or ""
                ),
                type=str(row.get("type") or row.get("postType") or row.get("mediaType") or "Spotlight"),
                imageUrl=str(
                    row.get("imageUrl")
                    or row.get("thumbnailUrl")
                    or row.get("coverUrl")
                    or video_meta.get("thumbnailUrl")
                    or media_image
                    or ""
                ),
                videoUrl=str(row.get("videoUrl") or video_meta.get("contentUrl") or media_video or ""),
                createdTime=created_time,
                viewCount=self._to_int(
                    row.get("viewCount")
                    or row.get("views")
                    or row.get("playCount")
                    or engagement.get("viewCount")
                    or video_meta.get("viewCount")
                    or 0
                ),
                likeCount=self._to_int(
                    row.get("likeCount")
                    or row.get("likes")
                    or engagement.get("recommendCount")
                    or 0
                ),
                commentCount=self._to_int(
                    row.get("commentCount")
                    or row.get("comments")
                    or engagement.get("commentCount")
                    or 0
                ),
                shareCount=self._to_int(
                    row.get("shareCount")
                    or row.get("shares")
                    or engagement.get("shareCount")
                    or 0
                ),
            )

            has_content = bool(post.id or post.caption or post.imageUrl or post.videoUrl or post.url)
            if has_content:
                posts.append(post)

        return posts[:12]

    async def scrape_competitor(self, username: str) -> SnapchatCompetitorResponse:
        token = await self._get_apify_token()
        clean = username.strip().lstrip("@")

        async with httpx.AsyncClient(timeout=30) as client:
            profile_items = await self._run_profile_actor(client, clean, token)
            spotlight_items = await self._run_spotlight_actor(client, clean, token)

        if not profile_items and not spotlight_items:
            raise HTTPException(404, f"No Snapchat data found for '{clean}'.")

        profile_source = profile_items if profile_items else spotlight_items
        profile = self._extract_profile(profile_source, clean)
        posts = self._extract_posts(spotlight_items, clean)

        return SnapchatCompetitorResponse(
            username=profile["username"],
            displayName=profile["displayName"],
            bio=profile["bio"],
            isVerified=profile["isVerified"],
            followersCount=profile["followersCount"],
            friendsCount=profile["friendsCount"],
            snapScore=profile["snapScore"],
            profilePicture=profile["profilePicture"],
            profileUrl=profile["profileUrl"],
            latestPosts=posts,
        )
