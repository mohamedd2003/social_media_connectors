"""
TikTok API – Pydantic v2 Schemas

Defines all request/response models for the TikTok integration:
- OAuth 2.0 token exchange & storage
- User profile info & aggregate metrics
- Video list items & video publish payloads
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokPrivacyLevel(str, Enum):
    """Audience visibility for a published TikTok video."""
    PUBLIC_TO_EVERYONE = "PUBLIC_TO_EVERYONE"
    MUTUAL_FOLLOW_FRIENDS = "MUTUAL_FOLLOW_FRIENDS"
    FOLLOWER_OF_CREATOR = "FOLLOWER_OF_CREATOR"
    SELF_ONLY = "SELF_ONLY"


class TikTokPublishStatus(str, Enum):
    """Possible states of a video publish job."""
    PROCESSING_UPLOAD = "PROCESSING_UPLOAD"
    PROCESSING_DOWNLOAD = "PROCESSING_DOWNLOAD"
    SEND_TO_USER_INBOX = "SEND_TO_USER_INBOX"
    PUBLISH_COMPLETE = "PUBLISH_COMPLETE"
    FAILED = "FAILED"


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokTokenResponse(BaseModel):
    """Response from TikTok's /v2/oauth/token/ endpoint."""
    access_token: str
    refresh_token: str = ""
    open_id: str = ""
    token_type: str = "Bearer"
    expires_in: int = 86400  # TikTok tokens expire in 24 hours
    refresh_expires_in: int = 0
    scope: str = ""


class TikTokTokenDB(BaseModel):
    """Shape of a stored TikTok account row in the database."""
    id: str
    type: str = "tiktok"
    name: str = ""
    access_token: str
    refresh_token: str = ""
    open_id: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# User Profile
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokUserProfile(BaseModel):
    """User info from TikTok's /v2/user/info/ endpoint."""
    open_id: str = ""
    union_id: str = ""
    display_name: str = ""
    avatar_url: str = ""
    avatar_url_100: str = ""
    bio_description: str = ""
    profile_deep_link: str = ""
    is_verified: bool = False
    follower_count: int = 0
    following_count: int = 0
    likes_count: int = 0
    video_count: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregate Metrics (for dashboard)
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokProfileMetrics(BaseModel):
    """Aggregated profile-level metrics shown on the analytics dashboard."""
    followers: int = 0
    following: int = 0
    total_likes: int = 0
    total_videos: int = 0
    total_views: int = 0
    total_shares: int = 0
    total_comments: int = 0
    engagement_rate: float = 0.0


class TikTokProfileInsightsResponse(BaseModel):
    """Full analytics payload returned to the frontend."""
    profile: TikTokUserProfile = Field(default_factory=TikTokUserProfile)
    metrics: TikTokProfileMetrics = Field(default_factory=TikTokProfileMetrics)
    recent_videos: list[TikTokVideoItem] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Video Items
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokVideoItem(BaseModel):
    """A single video from TikTok's /v2/video/list/ endpoint."""
    id: str = ""
    title: str = ""
    cover_image_url: str = ""
    share_url: str = ""
    embed_link: str = ""
    duration: int = 0
    create_time: int = 0
    # Metrics
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0


# Forward ref update for TikTokProfileInsightsResponse
TikTokProfileInsightsResponse.model_rebuild()


# ═══════════════════════════════════════════════════════════════════════════════
# Video Publishing
# ═══════════════════════════════════════════════════════════════════════════════


class TikTokPublishRequest(BaseModel):
    """Request body for the video publish endpoint."""
    title: str = Field(..., max_length=150, description="Video caption / hashtags")
    video_url: str = Field(..., description="Publicly accessible URL of the video file")
    privacy_level: TikTokPrivacyLevel = TikTokPrivacyLevel.PUBLIC_TO_EVERYONE
    disable_duet: bool = False
    disable_stitch: bool = False
    disable_comment: bool = False


class TikTokPublishResponse(BaseModel):
    """Response after initiating a TikTok video publish."""
    publish_id: str = ""
    upload_url: str = ""
    status: TikTokPublishStatus = TikTokPublishStatus.PROCESSING_DOWNLOAD


class TikTokPublishStatusResponse(BaseModel):
    """Response from checking publish status."""
    publish_id: str = ""
    status: TikTokPublishStatus = TikTokPublishStatus.PROCESSING_DOWNLOAD
    uploaded_bytes: int = 0
    error_msg: str = ""
