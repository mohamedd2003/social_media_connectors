"""
Snapchat Marketing API – Pydantic Schemas

Defines all request/response models for the Snapchat integration:
- OAuth 2.0 token exchange & storage
- Organization / Ad Account / Campaign entities
- Public Profile details & overview metrics
- Story & Spotlight content items
- Ad creation payloads
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class SnapAdStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class SnapOptimizationGoal(str, Enum):
    IMPRESSIONS = "IMPRESSIONS"
    SWIPES = "SWIPES"
    APP_INSTALLS = "APP_INSTALLS"
    VIDEO_VIEWS = "VIDEO_VIEWS"


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0
# ═══════════════════════════════════════════════════════════════════════════════


class SnapTokenResponse(BaseModel):
    """Response from Snapchat's /login/oauth2/access_token endpoint."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800  # Snapchat tokens expire in 30 minutes
    scope: str = ""


class SnapTokenDB(BaseModel):
    """Shape of a stored Snapchat account row from the database."""
    id: str
    type: str = "snapchat"
    name: str = ""
    access_token: str
    refresh_token: str = ""
    org_id: Optional[str] = None


class SnapAuthState(BaseModel):
    """OAuth state parameter (CSRF protection)."""
    redirect_uri: str
    nonce: str


# ═══════════════════════════════════════════════════════════════════════════════
# Organization / Ad Account
# ═══════════════════════════════════════════════════════════════════════════════


class SnapOrganization(BaseModel):
    id: str
    name: str


class SnapAdAccount(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    currency: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile – Profile Details & Overview Metrics
# ═══════════════════════════════════════════════════════════════════════════════


class SnapProfileDetails(BaseModel):
    """Profile info shown at the top of the Snapchat Creator Portal."""
    user_id: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    profile_type: str = "Organization Admin"
    avatar_url: Optional[str] = None
    public_profile_id: Optional[str] = None
    public_profile_name: Optional[str] = None
    snap_user_name: Optional[str] = None
    profile_tier: Optional[str] = None
    logo_urls: Optional[dict] = None


class SnapMetricValue(BaseModel):
    """A single metric with current value and 28-day comparison."""
    current: int = 0
    previous_28d: int = 0
    change_pct: Optional[float] = None


class SnapOverviewMetrics(BaseModel):
    """Overview section: Total Followers, Total Reach, Profile Views."""
    total_followers: SnapMetricValue = Field(default_factory=SnapMetricValue)
    total_reach: SnapMetricValue = Field(default_factory=SnapMetricValue)
    profile_views: SnapMetricValue = Field(default_factory=SnapMetricValue)


class SnapStoryItem(BaseModel):
    """A single story/media item from Public Profile or Ad Account."""
    id: str
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    download_link: Optional[str] = None
    file_name: Optional[str] = None
    file_size_in_bytes: Optional[int] = None
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    image_format: Optional[str] = None
    visibility: Optional[str] = None
    view_count: Optional[int] = None
    completion_rate: Optional[float] = None
    source: str = "profile"
    profile_id: Optional[str] = None
    profile_name: Optional[str] = None


class SnapProfileOverview(BaseModel):
    """Aggregated dashboard response matching Snapchat Creator Portal."""
    profile: SnapProfileDetails = Field(default_factory=SnapProfileDetails)
    metrics: SnapOverviewMetrics = Field(default_factory=SnapOverviewMetrics)
    public_stories: list[SnapStoryItem] = []
    saved_stories: list[SnapStoryItem] = []
    spotlight: list[SnapStoryItem] = []
    campaigns_count: int = 0
    media_count: int = 0
    api_available: bool = False
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Campaign / Ad Squad / Ad Creation
# ═══════════════════════════════════════════════════════════════════════════════


class SnapCampaign(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    daily_budget_micro: Optional[int] = None


class SnapCampaignCreate(BaseModel):
    ad_account_id: str
    name: str
    status: SnapAdStatus = SnapAdStatus.PAUSED
    daily_budget_micro: int = Field(
        default=20_000_000,
        description="Daily budget in micro-currency (20000000 = $20)",
    )
    start_time: Optional[str] = None


class SnapAdSquad(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    optimization_goal: Optional[str] = None


class SnapAdSquadCreate(BaseModel):
    campaign_id: str
    name: str
    optimization_goal: SnapOptimizationGoal = SnapOptimizationGoal.IMPRESSIONS
    bid_micro: int = Field(default=1_000_000)
    daily_budget_micro: int = Field(default=20_000_000)
    target_country: str = Field(default="US")
    status: SnapAdStatus = SnapAdStatus.PAUSED


class SnapAdCreate(BaseModel):
    ad_account_id: str
    campaign_id: str
    message: str = Field(..., description="Headline / ad copy text")


class SnapInsight(BaseModel):
    id: str
    caption: str = ""
    created_time: Optional[str] = None
    impressions: int = 0
    swipes: int = 0
    spend: float = 0.0
    conversions: int = 0
    engagement_rate: Optional[float] = None
    platform: str = "snapchat"


class SnapShareRequest(BaseModel):
    media_url: str = Field(..., description="Public URL to the image/video to share")
    attachment_url: Optional[str] = None
    caption: Optional[str] = None
    sticker_url: Optional[str] = None
