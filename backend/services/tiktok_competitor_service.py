"""
TikTok Competitor Analysis – Async Apify Scraper Service

Triggers a run of clockworks/tiktok-scraper on Apify, polls until the run
succeeds, then fetches and parses the dataset into our Pydantic models.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

from schemas.tiktok_competitor import LatestVideo, TikTokCompetitorResponse

logger = logging.getLogger("tiktok.competitor_service")

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "clockworks~tiktok-scraper"

POLL_INTERVAL = 2        # seconds between status checks
MAX_POLL_ATTEMPTS = 60   # give up after ~2 minutes
DATASET_PAGE_SIZE = 1000


def _to_int(value: object, default: int = 0) -> int:
    """Best-effort integer conversion for inconsistent scraper field types."""
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


async def scrape_competitor(username: str) -> TikTokCompetitorResponse:
    """
    End-to-end: start Apify actor run → poll → fetch dataset → parse.

    Raises HTTPException on timeout, actor failure, or empty results.
    """
    # Reload .env so token updates take effect without full app restart.
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
    apify_token = os.getenv("APIFY_API_TOKEN", "")

    if not apify_token:
        raise HTTPException(500, "APIFY_API_TOKEN is not configured on the backend.")

    async with httpx.AsyncClient(timeout=30) as client:
        # ── 1. Start the actor run ───────────────────────────────
        run_url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs"
        payload = {"profiles": [username], "resultsPerPage": 100}

        resp = await client.post(
            run_url,
            params={"token": apify_token},
            json=payload,
        )
        if resp.status_code != 201:
            logger.error("Apify run start failed: %s %s", resp.status_code, resp.text[:300])
            raise HTTPException(502, f"Failed to start Apify scraper: {resp.text[:200]}")

        run_data = resp.json().get("data", {})
        run_id = run_data.get("id")
        if not run_id:
            raise HTTPException(502, "Apify returned no run ID.")

        logger.info("Apify run started: %s for @%s", run_id, username)

        # ── 2. Poll until SUCCEEDED / FAILED ─────────────────────
        status_url = f"{APIFY_BASE}/actor-runs/{run_id}"
        dataset_id: str | None = None

        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            await asyncio.sleep(POLL_INTERVAL)

            poll = await client.get(status_url, params={"token": apify_token})
            if poll.status_code != 200:
                logger.warning("Poll attempt %d failed: %s", attempt, poll.status_code)
                continue

            poll_data = poll.json().get("data", {})
            status = poll_data.get("status")
            logger.debug("Poll %d – status: %s", attempt, status)

            if status == "SUCCEEDED":
                dataset_id = poll_data.get("defaultDatasetId")
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise HTTPException(
                    502,
                    f"Apify scraper {status.lower()} for @{username}.",
                )
        else:
            raise HTTPException(
                504,
                f"Apify scraper timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s "
                f"for @{username}.",
            )

        if not dataset_id:
            raise HTTPException(502, "Apify run succeeded but returned no dataset ID.")

        # ── 3. Fetch all dataset items (pagination-safe) ─────────
        items = await _fetch_all_dataset_items(client, dataset_id, apify_token)
        if not items:
            raise HTTPException(
                404,
                f"No data found for TikTok user @{username}. "
                "The profile may not exist or is private.",
            )

        # ── 4. Parse into our schema ─────────────────────────────
        return _parse_apify_result(items, username)


async def _fetch_all_dataset_items(
    client: httpx.AsyncClient,
    dataset_id: str,
    apify_token: str,
) -> list[dict]:
    """Read every dataset row using offset/limit paging."""
    items_url = f"{APIFY_BASE}/datasets/{dataset_id}/items"
    offset = 0
    all_items: list[dict] = []

    while True:
        resp = await client.get(
            items_url,
            params={
                "token": apify_token,
                "offset": offset,
                "limit": DATASET_PAGE_SIZE,
                "clean": "true",
                "format": "json",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch Apify dataset items.")

        batch = resp.json()
        if not isinstance(batch, list) or not batch:
            break

        all_items.extend(batch)
        if len(batch) < DATASET_PAGE_SIZE:
            break
        offset += len(batch)

    return all_items


def _parse_apify_result(
    items: list[dict],
    username: str,
) -> TikTokCompetitorResponse:
    """
    Map raw Apify dataset items into our response model.

    The scraper returns one item per video plus author metadata on each.
    We pull the profile info from the first item and collect all videos.
    """
    first = items[0]

    # Author metadata lives at the top level of each item.
    author = first.get("authorMeta", first.get("author", {}))
    signature = author.get("signature", first.get("authorSignature", ""))

    profile = TikTokCompetitorResponse(
        username=author.get("name", username),
        displayName=author.get("nickName", author.get("nickname", "")),
        followers=_to_int(author.get("fans", author.get("followers", 0))),
        following=_to_int(author.get("following", 0)),
        totalLikes=_to_int(author.get("heart", author.get("likes", 0))),
        bio=signature or first.get("signature", ""),
        isVerified=bool(author.get("verified", first.get("authorVerified", False))),
        region=author.get("region", first.get("authorRegion", "")),
        language=author.get("language", first.get("language", "")),
        avatar=author.get("avatar", author.get("avatarThumb", "")),
        latestVideos=[],
    )

    for item in items:
        video_meta = item.get("videoMeta", {}) if isinstance(item.get("videoMeta"), dict) else {}
        music_meta = item.get("musicMeta", {}) if isinstance(item.get("musicMeta"), dict) else {}

        video = LatestVideo(
            videoUrl=item.get("webVideoUrl", item.get("videoUrl", "")),
            description=item.get("text", item.get("desc", "")),
            viewCount=_to_int(item.get("playCount", item.get("views", 0))),
            likeCount=_to_int(item.get("diggCount", item.get("likes", 0))),
            commentCount=_to_int(item.get("commentCount", item.get("comments", 0))),
            shareCount=_to_int(item.get("shareCount", item.get("shares", 0))),
            downloadCount=_to_int(item.get("downloadCount", 0)),
            duration=_to_int(video_meta.get("duration", item.get("videoDuration", 0))),
            format=str(video_meta.get("format", item.get("videoFormat", "")) or ""),
            coverUrl=(
                video_meta.get("coverUrl")
                or item.get("imageUrl")
                or item.get("videoCover")
                or ""
            ),
            musicTitle=str(
                music_meta.get("musicName")
                or music_meta.get("title")
                or item.get("musicTitle")
                or ""
            ),
            musicAuthor=str(
                music_meta.get("musicAuthor")
                or music_meta.get("authorName")
                or item.get("musicAuthor")
                or ""
            ),
            createdAt=item.get("createTimeISO", item.get("createTime", None)),
        )
        profile.latestVideos.append(video)

    return profile
