"""
Snapchat Competitor Analysis - Pydantic Schemas
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LatestSnapPost(BaseModel):
    id: str = Field("", description="Post/story ID")
    url: str = Field("", description="Public URL")
    caption: str = Field("", description="Post text")
    type: str = Field("Story", description="Story/Spotlight/Post type")
    imageUrl: str = Field("", description="Image or thumbnail URL")
    videoUrl: str = Field("", description="Video URL")
    createdTime: str | None = Field(None, description="Post timestamp")
    viewCount: int = Field(0, description="Views")
    likeCount: int = Field(0, description="Likes")
    commentCount: int = Field(0, description="Comments")
    shareCount: int = Field(0, description="Shares")


class SnapchatCompetitorResponse(BaseModel):
    username: str = Field("", description="Snapchat username")
    displayName: str = Field("", description="Display name")
    bio: str = Field("", description="Bio/about text")
    isVerified: bool = Field(False, description="Whether profile is verified")
    followersCount: int = Field(0, description="Followers/subscribers")
    friendsCount: int = Field(0, description="Friends/following")
    snapScore: int = Field(0, description="Snap score if available")
    profilePicture: str = Field("", description="Avatar URL")
    profileUrl: str = Field("", description="Public profile URL")
    latestPosts: list[LatestSnapPost] = Field(default_factory=list)
