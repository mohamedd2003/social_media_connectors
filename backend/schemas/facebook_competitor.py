"""
Facebook Competitor Analysis – Pydantic v2 Schemas
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatestFacebookPost(BaseModel):
    id: str = Field("", description="Facebook post ID")
    url: str = Field("", description="Facebook post permalink")
    message: str = Field("", description="Post text/content")
    imageUrl: str = Field("", description="Post image URL")
    createdTime: str | None = Field(None, description="Post timestamp")
    likeCount: int = Field(0, description="Post likes")
    commentCount: int = Field(0, description="Post comments")
    shareCount: int = Field(0, description="Post shares")
    reactionCount: int = Field(0, description="Post reactions")


class FacebookCompetitorResponse(BaseModel):
    pageId: str = Field(..., description="Facebook Page ID")
    name: str = Field("", description="Page display name")
    username: str = Field("", description="Page username")
    category: str = Field("", description="Page category")
    about: str = Field("", description="Page about text")
    description: str = Field("", description="Page description")
    followersCount: int = Field(0, description="Page followers count")
    fanCount: int = Field(0, description="Page fan count")
    isVerified: bool = Field(False, description="Whether page is verified")
    profilePicture: str = Field("", description="Page profile picture URL")
    pageUrl: str = Field("", description="Page URL")
    latestPosts: list[LatestFacebookPost] = Field(default_factory=list)
