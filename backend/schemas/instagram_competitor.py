"""
Instagram Competitor Analysis – Pydantic v2 Schemas
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LatestPost(BaseModel):
    """A single public Instagram post returned by the Apify scraper."""

    id: str = Field("", description="Instagram media ID")
    url: str = Field("", description="Canonical Instagram post/reel URL")
    caption: str = Field("", description="Post caption")
    type: str = Field("", description="Image, Video, or Sidecar")
    displayUrl: str = Field("", description="Post image/thumbnail URL")
    likeCount: int = Field(0, description="Number of likes")
    commentCount: int = Field(0, description="Number of comments")
    videoViewCount: Optional[int] = Field(
        None,
        description="Video view count when post type is video/reel",
    )
    timestamp: Optional[str] = Field(
        None,
        description="Post publish timestamp in ISO format",
    )


class InstagramCompetitorResponse(BaseModel):
    """Public profile metrics and latest posts for a competitor account."""

    username: str = Field(..., description="Instagram handle")
    fullName: str = Field("", description="Display full name")
    biography: str = Field("", description="Profile biography")
    followersCount: int = Field(0, description="Followers count")
    followsCount: int = Field(0, description="Following count")
    postsCount: int = Field(0, description="Total media posts count")
    profilePicUrl: str = Field("", description="Profile picture URL")
    isVerified: bool = Field(False, description="Whether profile is verified")
    latestPosts: list[LatestPost] = Field(default_factory=list)
