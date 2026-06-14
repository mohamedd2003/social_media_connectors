"""
TikTok API Service – Production-Grade Async HTTPX Client

Stateless service class for calling TikTok's Content Posting API and
User Info / Video List endpoints.

Architecture:
  TikTokAPIService  ← stateless, takes access_token per-call
  ├─ get_auth_url()                              → builds OAuth2 authorize URL
  ├─ get_tokens(code)                            → POST /v2/oauth/token/
  ├─ refresh_tokens(refresh_token)               → POST /v2/oauth/token/ (refresh)
  ├─ fetch_user_info(access_token)               → GET  /v2/user/info/
  ├─ fetch_video_list(access_token)              → POST /v2/video/list/
  ├─ publish_video(access_token, title, url)     → POST /v2/post/publish/video/init/
  ├─ check_publish_status(access_token, pub_id)  → POST /v2/post/publish/status/fetch/
  └─ fetch_profile_analytics(access_token)       → aggregated profile + video metrics

Error handling:
  - 401 → re-auth prompt
  - 403 → missing scope
  - 429 → rate limited (Retry-After header)
  - 5xx → upstream error (502)
"""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from schemas.tiktok import (
    TikTokProfileInsightsResponse,
    TikTokProfileMetrics,
    TikTokPublishResponse,
    TikTokPublishStatus,
    TikTokPublishStatusResponse,
    TikTokUserProfile,
    TikTokVideoItem,
)

logger = logging.getLogger("tiktok.api_service")

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

TIKTOK_AUTH_BASE = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_API_BASE = "https://open.tiktokapis.com"

# Required scopes for our integration
TIKTOK_SCOPES = "user.info.basic,video.publish,video.list"


# ═══════════════════════════════════════════════════════════════════════════════
# Error handling helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    """Translate TikTok API errors into FastAPI HTTPExceptions."""
    if resp.status_code == 200:
        return

    status = resp.status_code
    body = resp.text[:500]

    if status == 401:
        raise HTTPException(
            401,
            f"TikTok token expired or invalid ({context}). "
            "Re-authenticate via /tiktok/auth/login.",
        )
    if status == 403:
        raise HTTPException(
            403,
            f"Forbidden: missing required TikTok scope for {context}. "
            f"Response: {body}",
        )
    if status == 429:
        retry_after = resp.headers.get("Retry-After", "60")
        raise HTTPException(
            429,
            f"Rate limited by TikTok ({context}). "
            f"Retry after {retry_after}s.",
        )
    if status == 404:
        raise HTTPException(
            404,
            f"TikTok resource not found ({context}). Response: {body}",
        )
    if status >= 500:
        raise HTTPException(
            502,
            f"TikTok server error {status} ({context}). Response: {body}",
        )
    raise HTTPException(status, f"TikTok API error {status} ({context}): {body}")


def _check_tiktok_error(data: dict, context: str) -> None:
    """
    TikTok often returns 200 with an error object in the body.
    Check the nested error structure and raise if present.
    """
    error = data.get("error", {})
    error_code = error.get("code", "ok")
    if error_code != "ok" and error_code != 0:
        msg = error.get("message", "Unknown TikTok error")
        log_id = error.get("log_id", "")
        # Map TikTok error codes to HTTP status codes
        if "token" in msg.lower() or "auth" in msg.lower():
            raise HTTPException(401, f"TikTok auth error ({context}): {msg} [log_id={log_id}]")
        if "scope" in msg.lower() or "permission" in msg.lower():
            raise HTTPException(403, f"TikTok scope error ({context}): {msg} [log_id={log_id}]")
        if "rate" in msg.lower():
            raise HTTPException(429, f"TikTok rate limit ({context}): {msg} [log_id={log_id}]")
        raise HTTPException(400, f"TikTok error ({context}): {msg} [log_id={log_id}]")


def _handle_network_error(e: Exception, context: str) -> None:
    """Translate DNS/connection errors to 502."""
    msg = str(e)
    if any(s in msg for s in ("getaddrinfo", "ConnectError", "NameResolutionError")):
        raise HTTPException(
            502,
            f"Cannot reach TikTok API ({context}). "
            "This may be a DNS or network issue.",
        )
    raise HTTPException(502, f"Network error calling TikTok ({context}): {msg}")


def _safe_int(val: Any, default: int = 0) -> int:
    """Coerce a value to int, returning default on None/error."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════════════════
# TikTok API Service
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokAPIService:
    """
    Stateless async service for TikTok's v2 API.

    All methods accept credentials per-call — no instance state is stored.
    Uses httpx.AsyncClient for non-blocking HTTP.
    """

    def __init__(self) -> None:
        self._client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
        self._client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    # ─── OAuth 2.0 ────────────────────────────────────────────────────────

    def get_auth_url(self, redirect_uri: str) -> str:
        """
        Build the TikTok OAuth2 authorization URL.

        Scopes requested:
          - user.info.basic   → profile data (name, avatar, follower count)
          - video.publish     → post videos on behalf of user
          - video.list        → list user's published videos + metrics

        Returns:
            Full authorization URL to redirect the user to.
        """
        params = urlencode({
            "client_key": self._client_key,
            "redirect_uri": redirect_uri,
            "scope": TIKTOK_SCOPES,
            "response_type": "code",
            "state": "tiktok_oauth",  # CSRF protection (use a random nonce in production)
        })
        url = f"{TIKTOK_AUTH_BASE}?{params}"
        logger.info("Generated TikTok auth URL: %s", url)
        return url

    async def get_tokens(self, code: str, redirect_uri: str) -> dict:
        """
        Exchange authorization code for access + refresh tokens.

        POST https://open.tiktokapis.com/v2/oauth/token/

        Args:
            code: Authorization code from OAuth callback.
            redirect_uri: Must match the redirect_uri used in get_auth_url().

        Returns:
            Dict with access_token, refresh_token, open_id, expires_in, scope.
        """
        payload = {
            "client_key": self._client_key,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    TIKTOK_TOKEN_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception as e:
            _handle_network_error(e, "token exchange")

        _raise_for_status(resp, "token exchange")
        data = resp.json()
        _check_tiktok_error(data, "token exchange")

        logger.info("TikTok token exchange successful, open_id=%s", data.get("open_id", "?"))
        return data

    async def refresh_tokens(self, refresh_token: str) -> dict:
        """
        Refresh an expired access token using the refresh token.

        POST https://open.tiktokapis.com/v2/oauth/token/

        Args:
            refresh_token: The refresh token obtained during initial auth.

        Returns:
            Dict with new access_token, refresh_token, open_id, expires_in.
        """
        payload = {
            "client_key": self._client_key,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    TIKTOK_TOKEN_URL,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except Exception as e:
            _handle_network_error(e, "token refresh")

        _raise_for_status(resp, "token refresh")
        data = resp.json()
        _check_tiktok_error(data, "token refresh")

        logger.info("TikTok token refresh successful")
        return data

    # ─── User Info ────────────────────────────────────────────────────────

    async def fetch_user_info(self, access_token: str) -> TikTokUserProfile:
        """
        Fetch the authenticated user's profile information.

        GET https://open.tiktokapis.com/v2/user/info/
        Required scope: user.info.basic

        Args:
            access_token: Valid TikTok access token.

        Returns:
            TikTokUserProfile with display name, avatar, follower count, etc.
        """
        url = f"{TIKTOK_API_BASE}/v2/user/info/"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        params = {
            "fields": "open_id,union_id,display_name,avatar_url,avatar_url_100,"
                      "bio_description,profile_deep_link,is_verified,"
                      "follower_count,following_count,likes_count,video_count",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers, params=params)
        except Exception as e:
            _handle_network_error(e, "fetch user info")

        _raise_for_status(resp, "fetch user info")
        data = resp.json()
        _check_tiktok_error(data, "fetch user info")

        user_data = data.get("data", {}).get("user", {})
        return TikTokUserProfile(
            open_id=user_data.get("open_id", ""),
            union_id=user_data.get("union_id", ""),
            display_name=user_data.get("display_name", ""),
            avatar_url=user_data.get("avatar_url", ""),
            avatar_url_100=user_data.get("avatar_url_100", ""),
            bio_description=user_data.get("bio_description", ""),
            profile_deep_link=user_data.get("profile_deep_link", ""),
            is_verified=user_data.get("is_verified", False),
            follower_count=_safe_int(user_data.get("follower_count")),
            following_count=_safe_int(user_data.get("following_count")),
            likes_count=_safe_int(user_data.get("likes_count")),
            video_count=_safe_int(user_data.get("video_count")),
        )

    # ─── Video List ───────────────────────────────────────────────────────

    async def fetch_video_list(
        self,
        access_token: str,
        max_count: int = 20,
        cursor: int | None = None,
    ) -> list[TikTokVideoItem]:
        """
        Fetch the user's published videos with metrics.

        POST https://open.tiktokapis.com/v2/video/list/
        Required scope: video.list

        Args:
            access_token: Valid TikTok access token.
            max_count: Number of videos to fetch (max 20).
            cursor: Pagination cursor for subsequent pages.

        Returns:
            List of TikTokVideoItem with view/like/comment/share counts.
        """
        url = f"{TIKTOK_API_BASE}/v2/video/list/"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        params = {
            "fields": "id,title,cover_image_url,share_url,embed_link,"
                      "duration,create_time,view_count,like_count,"
                      "comment_count,share_count",
        }
        body: dict[str, Any] = {"max_count": min(max_count, 20)}
        if cursor is not None:
            body["cursor"] = cursor

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, params=params, json=body)
        except Exception as e:
            _handle_network_error(e, "fetch video list")

        _raise_for_status(resp, "fetch video list")
        data = resp.json()
        _check_tiktok_error(data, "fetch video list")

        videos_raw = data.get("data", {}).get("videos", [])
        videos = []
        for v in videos_raw:
            videos.append(TikTokVideoItem(
                id=v.get("id", ""),
                title=v.get("title", ""),
                cover_image_url=v.get("cover_image_url", ""),
                share_url=v.get("share_url", ""),
                embed_link=v.get("embed_link", ""),
                duration=_safe_int(v.get("duration")),
                create_time=_safe_int(v.get("create_time")),
                view_count=_safe_int(v.get("view_count")),
                like_count=_safe_int(v.get("like_count")),
                comment_count=_safe_int(v.get("comment_count")),
                share_count=_safe_int(v.get("share_count")),
            ))

        logger.info("Fetched %d TikTok videos", len(videos))
        return videos

    # ─── Video Publishing ─────────────────────────────────────────────────

    async def publish_video(
        self,
        access_token: str,
        title: str,
        video_url: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
    ) -> TikTokPublishResponse:
        """
        Publish a video to TikTok using the Direct Post (URL) method.

        POST https://open.tiktokapis.com/v2/post/publish/video/init/
        Required scope: video.publish

        TikTok requires the video to be at a publicly accessible URL.
        The caller must upload the file to S3/Cloud Storage first,
        then pass that URL here.

        Args:
            access_token: Valid TikTok access token.
            title: Video caption (max 150 chars), may include #hashtags.
            video_url: Public URL where TikTok can download the video.
            privacy_level: One of PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS,
                           FOLLOWER_OF_CREATOR, SELF_ONLY.
            disable_duet: If True, prevent others from creating duets.
            disable_stitch: If True, prevent others from stitching.
            disable_comment: If True, disable comments on the video.

        Returns:
            TikTokPublishResponse with publish_id and initial status.
        """
        url = f"{TIKTOK_API_BASE}/v2/post/publish/video/init/"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": disable_duet,
                "disable_stitch": disable_stitch,
                "disable_comment": disable_comment,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": video_url,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except Exception as e:
            _handle_network_error(e, "publish video")

        _raise_for_status(resp, "publish video")
        data = resp.json()
        _check_tiktok_error(data, "publish video")

        pub_data = data.get("data", {})
        result = TikTokPublishResponse(
            publish_id=pub_data.get("publish_id", ""),
            upload_url=pub_data.get("upload_url", ""),
            status=TikTokPublishStatus.PROCESSING_DOWNLOAD,
        )

        logger.info("TikTok publish initiated: publish_id=%s", result.publish_id)
        return result

    # ─── Publish Status Check ─────────────────────────────────────────────

    async def check_publish_status(
        self,
        access_token: str,
        publish_id: str,
    ) -> TikTokPublishStatusResponse:
        """
        Check the status of a previously initiated video publish.

        POST https://open.tiktokapis.com/v2/post/publish/status/fetch/

        Args:
            access_token: Valid TikTok access token.
            publish_id: The publish_id returned from publish_video().

        Returns:
            TikTokPublishStatusResponse with current status.
        """
        url = f"{TIKTOK_API_BASE}/v2/post/publish/status/fetch/"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {"publish_id": publish_id}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except Exception as e:
            _handle_network_error(e, "check publish status")

        _raise_for_status(resp, "check publish status")
        data = resp.json()
        _check_tiktok_error(data, "check publish status")

        status_data = data.get("data", {})
        status_str = status_data.get("status", "PROCESSING_DOWNLOAD")
        # Map to our enum, defaulting to PROCESSING_DOWNLOAD for unknown values
        try:
            status_enum = TikTokPublishStatus(status_str)
        except ValueError:
            status_enum = TikTokPublishStatus.PROCESSING_DOWNLOAD

        return TikTokPublishStatusResponse(
            publish_id=publish_id,
            status=status_enum,
            uploaded_bytes=_safe_int(status_data.get("uploaded_bytes")),
            error_msg=status_data.get("fail_reason", ""),
        )

    # ─── Aggregated Analytics ─────────────────────────────────────────────

    async def fetch_profile_analytics(
        self,
        access_token: str,
    ) -> TikTokProfileInsightsResponse:
        """
        Fetch full profile analytics: user info + video-level metrics.

        Combines data from:
          1. /v2/user/info/   → follower count, likes, video count
          2. /v2/video/list/  → per-video views, likes, comments, shares

        Calculates aggregate engagement rate:
          engagement_rate = (total_likes + total_comments + total_shares) / total_views * 100

        Args:
            access_token: Valid TikTok access token.

        Returns:
            TikTokProfileInsightsResponse with profile, metrics, and recent videos.
        """
        # Fetch profile and videos concurrently
        profile = await self.fetch_user_info(access_token)
        videos = await self.fetch_video_list(access_token, max_count=20)

        # Aggregate video-level metrics
        total_views = sum(v.view_count for v in videos)
        total_likes = sum(v.like_count for v in videos)
        total_comments = sum(v.comment_count for v in videos)
        total_shares = sum(v.share_count for v in videos)

        # Calculate engagement rate (avoid division by zero)
        engagement_rate = 0.0
        if total_views > 0:
            engagement_rate = round(
                (total_likes + total_comments + total_shares) / total_views * 100, 2
            )

        metrics = TikTokProfileMetrics(
            followers=profile.follower_count,
            following=profile.following_count,
            total_likes=profile.likes_count or total_likes,
            total_videos=profile.video_count or len(videos),
            total_views=total_views,
            total_shares=total_shares,
            total_comments=total_comments,
            engagement_rate=engagement_rate,
        )

        return TikTokProfileInsightsResponse(
            profile=profile,
            metrics=metrics,
            recent_videos=videos,
        )
