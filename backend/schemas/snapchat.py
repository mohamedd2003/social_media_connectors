from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class SnapAdStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class SnapOptimizationGoal(str, Enum):
    IMPRESSIONS = "IMPRESSIONS"
    SWIPES = "SWIPES"
    APP_INSTALLS = "APP_INSTALLS"
    VIDEO_VIEWS = "VIDEO_VIEWS"


# ── OAuth ────────────────────────────────────────────────────────────────────

class SnapTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800
    scope: str = ""


# ── Organization / Ad Account ───────────────────────────────────────────────

class SnapOrganization(BaseModel):
    id: str
    name: str


class SnapAdAccount(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    currency: Optional[str] = None


# ── Campaign ─────────────────────────────────────────────────────────────────

class SnapCampaign(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    daily_budget_micro: Optional[int] = None


class SnapCampaignCreate(BaseModel):
    ad_account_id: str
    name: str
    status: SnapAdStatus = SnapAdStatus.PAUSED
    daily_budget_micro: int = Field(default=20_000_000, description="Daily budget in micro-currency (e.g. 20000000 = $20)")
    start_time: Optional[str] = None


# ── Ad Squad ─────────────────────────────────────────────────────────────────

class SnapAdSquad(BaseModel):
    id: str
    name: str
    status: Optional[str] = None
    optimization_goal: Optional[str] = None


class SnapAdSquadCreate(BaseModel):
    campaign_id: str
    name: str
    optimization_goal: SnapOptimizationGoal = SnapOptimizationGoal.IMPRESSIONS
    bid_micro: int = Field(default=1_000_000, description="Bid in micro-currency")
    daily_budget_micro: int = Field(default=20_000_000, description="Daily budget in micro-currency")
    target_country: str = Field(default="US", description="ISO country code for targeting")
    status: SnapAdStatus = SnapAdStatus.PAUSED


# ── Ad / Creative ────────────────────────────────────────────────────────────

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


# ── Creative Kit (frontend-initiated sharing) ───────────────────────────────

class SnapShareRequest(BaseModel):
    media_url: str = Field(..., description="Public URL to the image/video to share")
    attachment_url: Optional[str] = Field(None, description="URL to attach (swipe-up link)")
    caption: Optional[str] = Field(None, description="Pre-filled caption text")
    sticker_url: Optional[str] = Field(None, description="Optional sticker image URL")
