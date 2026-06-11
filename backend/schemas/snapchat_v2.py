"""
Snapchat Marketing & Public Profile API — Pydantic v2 Schemas

Strict, type-hinted response models for:
  1. Public Profile API  → organic metrics, content metadata, audience insights
  2. Ads API             → campaign / ad-squad / ad-level reporting stats

Snapchat API base: https://adsapi.snapchat.com/v1/
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class ContentType(str, Enum):
    """Types of content on a Public Profile."""
    STORY = "STORY"
    SAVED_STORY = "SAVED_STORY"
    SPOTLIGHT = "SPOTLIGHT"
    LENS = "LENS"


class ProfileTier(str, Enum):
    PUBLIC = "PUBLIC"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"


class ProfileCategory(str, Enum):
    PERSON = "PERSON"
    BUSINESS = "BUSINESS"


class ReportGranularity(str, Enum):
    TOTAL = "TOTAL"
    DAY = "DAY"
    HOUR = "HOUR"


class CampaignStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile API – Profile Metadata
# ═══════════════════════════════════════════════════════════════════════════════


class ProfileInfo(BaseModel):
    """
    Public Profile metadata returned by:
      GET /v1/organizations/{org_id}/public_profiles
      GET /v1/public_profiles/{profile_id}
    """
    id: str = Field(..., description="UUID of the Public Profile")
    name: str = Field(default="", description="Display name")
    snap_user_name: Optional[str] = Field(default=None, description="@username handle")
    profile_picture_url: Optional[str] = None
    bio: Optional[str] = None
    tier: Optional[str] = None
    category: Optional[str] = None
    subscriber_count: Optional[int] = Field(default=None, description="Total followers/subscribers")
    organization_id: Optional[str] = None
    website_url: Optional[str] = None
    logo_urls: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile API – Organic Content Items
# ═══════════════════════════════════════════════════════════════════════════════


class StoryMetadata(BaseModel):
    """
    A single Story/Saved Story item from:
      GET /v1/public_profiles/{profile_id}/organic/stories
      GET /v1/public_profiles/{profile_id}/organic/saved_stories
    """
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    snap_count: int = Field(default=0, description="Number of snaps in the story")
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class SpotlightMetadata(BaseModel):
    """
    A Spotlight item from:
      GET /v1/public_profiles/{profile_id}/organic/spotlights
    """
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration_ms: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile API – Organic Metrics / Insights
# ═══════════════════════════════════════════════════════════════════════════════


class OrganicTimeseriesPoint(BaseModel):
    """A single data point in a time-series stat response."""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    value: int = 0


class OrganicStoryStats(BaseModel):
    """
    Per-story organic metrics from:
      GET /v1/public_profiles/{profile_id}/organic/stories/{story_id}/stats

    Standard organic metrics returned by Snapchat.
    """
    story_id: str
    total_views: int = Field(default=0, description="Total story views")
    unique_viewers: int = Field(default=0, description="Unique viewers")
    screenshots: int = Field(default=0, description="Number of screenshots taken")
    shares: int = Field(default=0, description="Share count")
    total_time_viewed_ms: int = Field(default=0, description="Total time viewed in milliseconds")
    completion_rate: Optional[float] = Field(default=None, description="Story completion rate (0-1)")
    subscribers_gained: int = Field(default=0, description="New subscribers from this story")
    subscribers_lost: int = Field(default=0, description="Subscribers lost from this story")


class SpotlightStats(BaseModel):
    """
    Per-spotlight metrics from:
      GET /v1/public_profiles/{profile_id}/organic/spotlights/{spotlight_id}/stats
    """
    spotlight_id: str
    total_views: int = 0
    unique_viewers: int = 0
    shares: int = 0
    favorites: int = 0
    total_time_viewed_ms: int = 0


class ProfileMetrics(BaseModel):
    """
    Aggregated profile-level organic insights from:
      GET /v1/public_profiles/{profile_id}/stats?start_time=...&end_time=...

    Snapchat returns these rolled-up metrics for a given date window.
    """
    profile_id: str
    subscriber_count: int = Field(default=0, description="Current total subscribers")
    subscriber_change: int = Field(default=0, description="Net change in subscribers over period")
    total_story_views: int = Field(default=0, description="Aggregate story views in window")
    unique_story_viewers: int = Field(default=0, description="Unique story viewers in window")
    total_shares: int = Field(default=0, description="Total shares across content")
    total_screenshots: int = Field(default=0, description="Total screenshots across content")
    total_reach: int = Field(default=0, description="Unique reach across all content")
    total_time_viewed_ms: int = Field(default=0, description="Total engagement time in ms")
    avg_completion_rate: Optional[float] = Field(default=None, description="Avg story completion (0-1)")
    time_series: list[OrganicTimeseriesPoint] = Field(default_factory=list)


class ProfileInsightsResponse(BaseModel):
    """
    Full response envelope for GET /api/v1/snapchat/profile-insights/{profile_id}
    """
    profile: ProfileInfo
    metrics: ProfileMetrics
    stories: list[StoryMetadata] = Field(default_factory=list)
    spotlight: list[SpotlightMetadata] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    api_available: bool = True
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Ads API – Campaign Reporting
# ═══════════════════════════════════════════════════════════════════════════════


class AdEntityStats(BaseModel):
    """
    Stats for a single ad entity (campaign / ad_squad / ad) from:
      GET /v1/campaigns/{id}/stats
      GET /v1/adsquads/{id}/stats
      GET /v1/ads/{id}/stats

    Fields mirror Snapchat's standard reporting fields.
    """
    entity_id: str = Field(..., description="Campaign, Ad Squad, or Ad UUID")
    entity_name: str = ""
    entity_type: str = Field(default="campaign", description="campaign | adsquad | ad")
    status: Optional[str] = None
    impressions: int = 0
    swipes: int = Field(default=0, description="Swipe-ups (link clicks)")
    spend_micro: int = Field(default=0, description="Spend in micro-currency units")
    spend: float = Field(default=0.0, description="Spend in real currency (spend_micro / 1e6)")
    video_views: int = 0
    video_views_15s: int = Field(default=0, description="15-second video views")
    screen_time_millis: int = Field(default=0, description="Total screen time in ms")
    quartile_1: int = Field(default=0, description="Video 25% views")
    quartile_2: int = Field(default=0, description="Video 50% views")
    quartile_3: int = Field(default=0, description="Video 75% views")
    view_completion: int = Field(default=0, description="Video 100% views")
    saves: int = 0
    shares: int = 0
    story_opens: int = 0
    conversion_purchases: int = 0
    conversion_purchases_value_micro: int = 0
    swipe_up_pct: Optional[float] = Field(default=None, description="Swipe rate = swipes / impressions")
    ecpm_micro: Optional[int] = Field(default=None, description="Effective CPM in micro-currency")


class DailyReportingRow(BaseModel):
    """A single day's stats within a time-series reporting response."""
    date: str = Field(..., description="ISO date string YYYY-MM-DD")
    impressions: int = 0
    swipes: int = 0
    spend_micro: int = 0
    spend: float = 0.0
    video_views: int = 0
    conversion_purchases: int = 0


class CampaignReportDetail(BaseModel):
    """
    Full reporting data for a single campaign, including roll-up totals
    and optional daily time-series.
    """
    campaign_id: str
    campaign_name: str = ""
    status: Optional[str] = None
    objective: Optional[str] = None
    daily_budget_micro: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    totals: AdEntityStats
    daily_breakdown: list[DailyReportingRow] = Field(default_factory=list)
    ad_squads: list[AdEntityStats] = Field(default_factory=list, description="Nested ad-squad level stats")


class AdsReportingResponse(BaseModel):
    """
    Full response envelope for GET /api/v1/snapchat/ads-insights/{ad_account_id}
    """
    ad_account_id: str
    ad_account_name: str = ""
    currency: str = "USD"
    start_date: str
    end_date: str
    total_impressions: int = 0
    total_spend: float = 0.0
    total_swipes: int = 0
    total_conversions: int = 0
    campaigns: list[CampaignReportDetail] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
