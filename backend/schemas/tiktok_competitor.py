"""
TikTok Competitor Analysis – Pydantic v2 Schemas

Models for the Apify-based competitor scraping feature.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LatestVideo(BaseModel):
    """A single scraped TikTok video from a competitor's profile."""
    videoUrl: str = Field("", description="Direct URL to the TikTok video")
    description: str = Field("", description="Video caption / description")
    viewCount: int = Field(0, description="Number of views")
    likeCount: int = Field(0, description="Number of likes")
    commentCount: int = Field(0, description="Number of comments")
    shareCount: int = Field(0, description="Number of shares")
    downloadCount: int = Field(0, description="Number of downloads")
    duration: int = Field(0, description="Video duration in seconds")
    format: str = Field("", description="Video file format (e.g., mp4)")
    coverUrl: str = Field("", description="Video cover/thumbnail URL")
    musicTitle: str = Field("", description="Music title used in the video")
    musicAuthor: str = Field("", description="Music author/artist")
    createdAt: Optional[str] = Field(None, description="ISO-8601 creation timestamp")


class TikTokCompetitorResponse(BaseModel):
    """Aggregated public profile data for a TikTok competitor."""
    username: str = Field(..., description="TikTok @handle")
    displayName: str = Field("", description="Display name on profile")
    followers: int = Field(0)
    following: int = Field(0)
    totalLikes: int = Field(0, description="Heart count across all videos")
    bio: str = Field("", description="Profile bio/signature")
    isVerified: bool = Field(False, description="Whether the account is verified")
    region: str = Field("", description="Profile region if available")
    language: str = Field("", description="Profile language if available")
    avatar: str = Field("", description="URL to the profile picture")
    latestVideos: list[LatestVideo] = Field(default_factory=list)
