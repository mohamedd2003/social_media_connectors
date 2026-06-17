"""
Manual Scrape Service – Playwright-based scraper for TikTok, Instagram, Facebook.

This is a functional alternative to Apify actors for scraping public profile data.
Uses stealth techniques and human behavior simulation to avoid detection.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import sys
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger("manual_scrape_service")


# ─── Response Models ─────────────────────────────────────────────────────────

class PostItem(BaseModel):
    """A single post/video from a scraped profile (matches Apify-level detail)."""
    id: str | None = None
    url: str | None = None
    thumbnail: str | None = None
    description: str | None = None
    type: str | None = None  # "video", "image", "sidecar", "reel"
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    downloads: int | None = None
    duration: int | None = None  # seconds
    format: str | None = None  # video format (e.g. mp4)
    music_title: str | None = None
    music_author: str | None = None
    created_at: str | None = None  # ISO timestamp
    reactions: int | None = None  # Facebook reactions


class ScrapeResult(BaseModel):
    """Full profile scrape result (matches Apify competitor response richness)."""
    status: str = "success"
    platform: str
    username: str
    display_name: str | None = None
    avatar: str | None = None
    followers: int | None = None
    following: int | None = None
    likes: int | None = None  # total likes / heart count
    posts_count: int | None = None
    bio: str | None = None
    is_verified: bool | None = None
    region: str | None = None
    language: str | None = None
    category: str | None = None  # FB page category
    about: str | None = None  # FB page about text
    description: str | None = None  # FB page description
    fan_count: int | None = None  # FB page likes / fan count
    page_url: str | None = None
    recent_posts: list[PostItem] = []
    error_message: str | None = None


# ─── Utility ─────────────────────────────────────────────────────────────────

def _parse_count(text: str | None) -> int | None:
    """Parse human-readable numbers like '1.2M', '500K', '3,456'."""
    if not text:
        return None
    text = text.strip().replace(",", "").replace(" ", "")
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if text.upper().endswith(suffix):
            try:
                return int(float(text[:-1]) * mult)
            except ValueError:
                return None
    try:
        return int(float(text))
    except ValueError:
        return None


async def _random_delay(min_s: float = 0.5, max_s: float = 2.0):
    """Simulate human-like delay between actions."""
    await asyncio.sleep(random.uniform(min_s, max_s))


# ─── Stealth Browser Setup ───────────────────────────────────────────────────

STEALTH_JS = """
// Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
delete navigator.__proto__.webdriver;

// Fake plugins
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const plugins = [
      {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
      {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
      {name: 'Native Client', filename: 'internal-nacl-plugin'}
    ];
    plugins.length = 3;
    return plugins;
  }
});

// Fake languages
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

// Chrome runtime
window.chrome = {runtime: {}, loadTimes: () => ({})};

// Permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
  parameters.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : originalQuery(parameters);

// Hide automation flags
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

// WebGL vendor
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.';
  if (parameter === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, parameter);
};
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
]


async def _get_stealth_page(playwright, extra_headers: dict | None = None):
    """Launch a stealth browser context and return (browser, page)."""
    ua = random.choice(USER_AGENTS)
    vp = random.choice(VIEWPORTS)

    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--window-size=1920,1080",
        ],
    )
    context = await browser.new_context(
        user_agent=ua,
        viewport=vp,
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            **(extra_headers or {}),
        },
    )
    await context.add_init_script(STEALTH_JS)
    page = await context.new_page()
    return browser, page


# ─── TikTok Scraper ─────────────────────────────────────────────────────────

async def _scrape_tiktok(username: str) -> ScrapeResult:
    """
    Scrape TikTok profile using multiple strategies:
    1. Direct HTTP fetch + embedded JSON extraction (fastest)
    2. Playwright with response interception + DOM fallback
    3. Meta tags / og:description (last resort)
    """

    def _final_ownership_guard(result: ScrapeResult) -> ScrapeResult:
        """Final safety net: strip any posts that don't belong to the target user."""
        if result and result.recent_posts:
            filtered = _tt_filter_owned_posts(result.recent_posts, username)
            if len(filtered) < len(result.recent_posts):
                logger.warning(
                    "TikTok: Final guard stripped %d/%d posts not belonging to @%s",
                    len(result.recent_posts) - len(filtered), len(result.recent_posts), username,
                )
            result.recent_posts = filtered or None
            # If we had posts but all were stripped, downgrade status
            if not result.recent_posts and result.status == "success":
                result.status = "partial_success"
                result.error_message = (
                    result.error_message or
                    "Profile loaded, but all captured videos belonged to other creators."
                )
        return result

    # Strategy 1: Direct HTTP – parse __UNIVERSAL_DATA / SIGI_STATE from HTML
    http_result = await _tt_strategy_http(username)
    if http_result and http_result.status == "success" and http_result.recent_posts:
        # Only skip Playwright if we actually got videos
        return _final_ownership_guard(http_result)

    # Strategy 2: Playwright browser with scrolling + API interception
    # This is the primary strategy for getting videos (TikTok lazy-loads them)
    pw_result = await _tt_strategy_playwright(username)
    if pw_result and pw_result.status == "success" and pw_result.recent_posts:
        return _final_ownership_guard(pw_result)

    # Strategy 3: Meta tags (minimal data)
    meta_result = await _tt_strategy_meta(username)

    # Prefer whichever strategy actually returned videos.
    for candidate in (pw_result, http_result, meta_result):
        if candidate and candidate.status == "success" and candidate.recent_posts:
            return _final_ownership_guard(candidate)

    # Merge profile data after all video strategies are exhausted.
    profile_result = None
    if pw_result and pw_result.status in ("success", "partial_success"):
        profile_result = pw_result

    if profile_result and http_result and http_result.status in ("success", "partial_success"):
        if http_result.followers and not profile_result.followers:
            profile_result.followers = http_result.followers
        if http_result.following and not profile_result.following:
            profile_result.following = http_result.following
        if http_result.likes and not profile_result.likes:
            profile_result.likes = http_result.likes
        if http_result.posts_count and not profile_result.posts_count:
            profile_result.posts_count = http_result.posts_count
        profile_result.display_name = profile_result.display_name or http_result.display_name
        profile_result.avatar = profile_result.avatar or http_result.avatar
        profile_result.bio = profile_result.bio or http_result.bio
        profile_result.is_verified = profile_result.is_verified or http_result.is_verified
        profile_result.region = profile_result.region or http_result.region
        profile_result.language = profile_result.language or http_result.language

    if not profile_result and http_result and http_result.status in ("success", "partial_success"):
        profile_result = http_result

    if not profile_result and meta_result and meta_result.status in ("success", "partial_success"):
        profile_result = meta_result

    if profile_result:
        if profile_result.recent_posts:
            profile_result.status = "success"
            return _final_ownership_guard(profile_result)
        if (profile_result.posts_count or 0) > 0:
            profile_result.status = "partial_success"
            if not profile_result.error_message:
                profile_result.error_message = (
                    "Profile loaded, but TikTok videos could not be extracted due to anti-bot checks or layout changes."
                )
        return profile_result

    # Return whatever we got
    if http_result:
        return http_result
    if pw_result:
        return pw_result
    if meta_result:
        return meta_result
    return ScrapeResult(
        status="blocked_by_challenge",
        platform="tiktok",
        username=username,
        error_message="TikTok blocked all scraping attempts. Try again later.",
    )


async def _tt_strategy_http(username: str) -> ScrapeResult | None:
    """Strategy 1: Fetch TikTok profile HTML and extract embedded JSON data."""
    import httpx
    import json as _json

    url = f"https://www.tiktok.com/@{username}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                return ScrapeResult(
                    status="not_found", platform="tiktok", username=username,
                    error_message="Profile not found.",
                )

            if resp.status_code != 200:
                return None

            html = resp.text

            # Try __UNIVERSAL_DATA_FOR_REHYDRATION__
            user_data = _extract_tt_universal_data(html, username)
            if user_data:
                return user_data

            # Try SIGI_STATE
            user_data = _extract_tt_sigi_state(html, username)
            if user_data:
                return user_data

            # Try webapp.user-detail
            user_data = _extract_tt_webapp_data(html, username)
            if user_data:
                return user_data

    except Exception as e:
        logger.debug("TikTok HTTP strategy failed for %s: %s", username, e)

    return None


def _extract_tt_universal_data(html: str, username: str) -> ScrapeResult | None:
    """Parse __UNIVERSAL_DATA_FOR_REHYDRATION__ from TikTok HTML."""
    import json as _json

    marker = '__UNIVERSAL_DATA_FOR_REHYDRATION__'
    idx = html.find(marker)
    if idx == -1:
        return None

    try:
        # Find the JSON object after the marker
        start = html.find('{', idx)
        if start == -1:
            return None
        # Find matching closing brace
        json_str = _extract_json_block(html, start)
        if not json_str:
            return None

        data = _json.loads(json_str)

        # Navigate to user data – structure is frequently changed by TikTok.
        default_scope = data.get("__DEFAULT_SCOPE__", {})
        user_detail = default_scope.get("webapp.user-detail", {})
        user_info = user_detail.get("userInfo", {})

        if not user_info:
            for scope_value in default_scope.values():
                if isinstance(scope_value, dict) and isinstance(scope_value.get("userInfo"), dict):
                    user_detail = scope_value
                    user_info = scope_value.get("userInfo", {})
                    break

        if not user_info:
            return None

        # itemList (videos) can live under multiple scope keys.
        item_list = user_detail.get("itemList", [])
        if not item_list:
            for scope_value in default_scope.values():
                if isinstance(scope_value, dict):
                    candidate = scope_value.get("itemList")
                    if isinstance(candidate, list) and candidate:
                        item_list = candidate
                        break

        # Filter itemList to only include videos from target user
        if item_list:
            item_list = [
                item for item in item_list
                if isinstance(item, dict) and _tt_video_belongs_to_user(item, username)
            ]

        if not user_info.get("itemList") and item_list:
            user_info["itemList"] = item_list

        result = _parse_tt_user_info(username, user_info)

        # Apply URL-based ownership filter on parsed posts
        if result.recent_posts:
            result.recent_posts = _tt_filter_owned_posts(result.recent_posts, username)

        if result.recent_posts:
            return result

        # Secondary check: parse ItemModule-like structures from scope keys.
        scope_posts: list[PostItem] = []
        for scope_value in default_scope.values():
            if not isinstance(scope_value, dict):
                continue

            module_candidates: list[dict] = []
            for key in ("ItemModule", "itemModule", "item_module", "items"):
                module = scope_value.get(key)
                if isinstance(module, dict) and module:
                    module_candidates.append(module)

            if not module_candidates and scope_value and all(isinstance(v, dict) for v in scope_value.values()):
                if any(("video" in v or "stats" in v) for v in scope_value.values()):
                    module_candidates.append(scope_value)

            for module in module_candidates:
                scope_posts.extend(_parse_tt_items(module, owner_username=username))

        # Filter by URL ownership as final guard
        scope_posts = _tt_filter_owned_posts(scope_posts, username)

        if scope_posts:
            unique_posts: list[PostItem] = []
            seen: set[str] = set()
            for post in scope_posts:
                key = post.id or post.url
                if not key or key in seen:
                    continue
                seen.add(key)
                unique_posts.append(post)
                if len(unique_posts) >= 12:
                    break
            result.recent_posts = unique_posts

        return result

    except Exception:
        return None


def _extract_tt_sigi_state(html: str, username: str) -> ScrapeResult | None:
    """Parse SIGI_STATE from TikTok HTML."""
    import json as _json

    marker = 'SIGI_STATE'
    idx = html.find(marker)
    if idx == -1:
        return None

    try:
        start = html.find('{', idx)
        if start == -1:
            return None
        json_str = _extract_json_block(html, start)
        if not json_str:
            return None

        data = _json.loads(json_str)

        # UserModule.users has user stats
        user_module = data.get("UserModule", {})
        users = user_module.get("users", {})
        stats = user_module.get("stats", {})

        user_key = username.lower()
        user = users.get(user_key) or users.get(username)
        user_stats = stats.get(user_key) or stats.get(username)

        if not user and not user_stats:
            # Try first key
            if users:
                user_key = next(iter(users))
                user = users[user_key]
                user_stats = stats.get(user_key, {})

        if not user:
            return None

        # Build video list from ItemModule – filter by owner
        item_module = data.get("ItemModule", {})
        posts = _parse_tt_items(item_module, owner_username=username)

        return ScrapeResult(
            status="success",
            platform="tiktok",
            username=username,
            display_name=user.get("nickname", username),
            avatar=user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb"),
            followers=user_stats.get("followerCount") if user_stats else None,
            following=user_stats.get("followingCount") if user_stats else None,
            likes=user_stats.get("heartCount") or (user_stats.get("heart") if user_stats else None),
            posts_count=user_stats.get("videoCount") if user_stats else None,
            bio=user.get("signature") or None,
            is_verified=user.get("verified"),
            region=user.get("region") or None,
            language=user.get("language") or None,
            recent_posts=posts,
        )

    except Exception:
        return None


def _extract_tt_webapp_data(html: str, username: str) -> ScrapeResult | None:
    """Parse webapp.user-detail JSON from script tags."""
    import json as _json

    # Look for script with id="__UNIVERSAL_DATA_FOR_REHYDRATION__" or id="SIGI_STATE"
    # or any script containing userInfo
    pattern = r'<script[^>]*id="([^"]*)"[^>]*>(.*?)</script>'
    for match in re.finditer(pattern, html, re.DOTALL):
        script_id, content = match.group(1), match.group(2)
        if not content.strip().startswith('{'):
            continue
        try:
            data = _json.loads(content)
            # Check various paths
            user_info = None
            if "userInfo" in str(data)[:500]:
                # Direct userInfo
                user_info = data.get("userInfo")
                if not user_info:
                    for key in data:
                        if isinstance(data[key], dict) and "userInfo" in data[key]:
                            user_info = data[key]["userInfo"]
                            break
            if user_info:
                return _parse_tt_user_info(username, user_info)
        except Exception:
            continue

    return None


def _parse_tt_user_info(username: str, user_info: dict) -> ScrapeResult:
    """Parse TikTok userInfo structure into ScrapeResult."""
    user = user_info.get("user", {})
    stats = user_info.get("stats", {})

    posts: list[PostItem] = []
    # Some responses include itemList at userInfo level or passed in
    item_list = user_info.get("itemList", [])
    for item in item_list[:12]:
        video = item.get("video", {})
        vid_id = item.get("id", "")
        author = item.get("author", username)
        if isinstance(author, dict):
            author = author.get("uniqueId", username)
        cover = (
            video.get("cover")
            or video.get("dynamicCover")
            or video.get("originCover")
            or item.get("cover")
        )
        # Music info
        music = item.get("music", {})
        # Timestamp
        create_time = item.get("createTime")
        created_at = None
        if create_time:
            try:
                from datetime import datetime, timezone
                created_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
            except Exception:
                created_at = None

        item_stats = item.get("stats", {})
        posts.append(PostItem(
            id=vid_id,
            url=f"https://www.tiktok.com/@{author}/video/{vid_id}" if vid_id else None,
            thumbnail=cover,
            description=item.get("desc") or None,
            type="video",
            views=item_stats.get("playCount"),
            likes=item_stats.get("diggCount"),
            comments=item_stats.get("commentCount"),
            shares=item_stats.get("shareCount"),
            downloads=item_stats.get("downloadCount"),
            duration=video.get("duration"),
            format=video.get("format") or video.get("codecType") or None,
            music_title=music.get("title") or None,
            music_author=music.get("authorName") or None,
            created_at=created_at,
        ))

    return ScrapeResult(
        status="success",
        platform="tiktok",
        username=username,
        display_name=user.get("nickname", username),
        avatar=user.get("avatarLarger") or user.get("avatarMedium") or user.get("avatarThumb"),
        followers=stats.get("followerCount"),
        following=stats.get("followingCount"),
        likes=stats.get("heartCount") or stats.get("heart"),
        posts_count=stats.get("videoCount"),
        bio=user.get("signature") or None,
        is_verified=user.get("verified"),
        region=user.get("region") or None,
        language=user.get("language") or None,
        recent_posts=posts,
    )


def _tt_video_belongs_to_user(item: dict, target_username: str) -> bool:
    """Check if a TikTok video item belongs to the target user (strict ownership)."""
    if not target_username:
        return True  # No filter if username unknown
    target_lower = target_username.lower().strip()
    author = item.get("author")
    if isinstance(author, dict):
        author_id = (author.get("uniqueId") or author.get("nickname") or "").lower()
    elif isinstance(author, str):
        author_id = author.lower()
    else:
        author_id = ""
    if author_id and author_id == target_lower:
        return True
    # Also check authorId field (numeric or string user ID match not possible without secUid)
    # and check nickname fallback
    nickname = ""
    if isinstance(author, dict):
        nickname = (author.get("uniqueId") or "").lower()
    # If author field is completely absent, we can't verify – allow it (DOM-extracted)
    if not author_id and not nickname:
        return True
    return False


def _tt_filter_owned_posts(posts: list["PostItem"], target_username: str) -> list["PostItem"]:
    """Remove posts that clearly don't belong to target_username based on URL."""
    if not target_username or not posts:
        return posts
    target_lower = target_username.lower().strip()
    filtered = []
    for post in posts:
        # If URL contains a different @username, discard
        if post.url:
            url_match = re.search(r"tiktok\.com/@([\w.]+)/", post.url)
            if url_match:
                url_author = url_match.group(1).lower()
                if url_author != target_lower:
                    continue
        filtered.append(post)
    return filtered


def _parse_tt_items(item_module: dict, owner_username: str | None = None) -> list[PostItem]:
    """Parse TikTok ItemModule dict into PostItem list, optionally filtering by owner."""
    posts: list[PostItem] = []
    for vid_id, item in list(item_module.items())[:24]:
        if not isinstance(item, dict):
            continue

        # Strict ownership check: skip videos from other authors
        if owner_username and not _tt_video_belongs_to_user(item, owner_username):
            continue

        video = item.get("video", {})
        stats = item.get("stats", {})
        music = item.get("music", {})
        create_time = item.get("createTime")
        created_at = None
        if create_time:
            try:
                from datetime import datetime, timezone
                created_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
            except Exception:
                created_at = None

        author = item.get("author")
        if isinstance(author, dict):
            author = author.get("uniqueId")

        posts.append(PostItem(
            id=vid_id,
            url=f"https://www.tiktok.com/@{author}/video/{vid_id}" if author and vid_id else None,
            thumbnail=video.get("cover") or video.get("dynamicCover") or video.get("originCover"),
            description=item.get("desc") or None,
            type="video",
            views=stats.get("playCount"),
            likes=stats.get("diggCount"),
            comments=stats.get("commentCount"),
            shares=stats.get("shareCount"),
            downloads=stats.get("downloadCount"),
            duration=video.get("duration"),
            format=video.get("format") or video.get("codecType") or None,
            music_title=music.get("title") or None,
            music_author=music.get("authorName") or None,
            created_at=created_at,
        ))
        if len(posts) >= 12:
            break
    return posts


def _extract_json_block(text: str, start: int) -> str | None:
    """Extract a balanced JSON object from text starting at position `start`."""
    depth = 0
    i = start
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        elif ch == '"':
            # Skip string content
            i += 1
            while i < length:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == '"':
                    break
                i += 1
        i += 1
    return None


async def _tt_strategy_playwright(username: str) -> ScrapeResult | None:
    """Strategy 2: Use Playwright with aggressive scrolling, API interception, and DOM extraction."""
    from playwright.async_api import async_playwright
    import json as _json

    url = f"https://www.tiktok.com/@{username}"
    captured_user_info: dict[str, Any] = {}
    captured_items: list[dict] = []

    async with async_playwright() as pw:
        browser, page = await _get_stealth_page(pw)
        try:
            # Intercept API responses for both user info AND video list
            async def handle_response(response):
                nonlocal captured_user_info, captured_items
                try:
                    resp_url = response.url
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type and "javascript" not in content_type:
                        return

                    if any(k in resp_url for k in [
                        "/api/user/detail",
                        "user/detail",
                        "webapp/user",
                    ]):
                        json_body = await response.json()
                        if "userInfo" in json_body:
                            captured_user_info.update(json_body["userInfo"])
                        elif "user" in json_body and "stats" in json_body:
                            captured_user_info["user"] = json_body["user"]
                            captured_user_info["stats"] = json_body["stats"]

                    # Capture video/item list API responses
                    if any(k in resp_url for k in [
                        "/api/post/item_list",
                        "item_list",
                        "/api/recommend/item_list",
                    ]):
                        json_body = await response.json()
                        items = json_body.get("itemList", [])
                        if items:
                            captured_items.extend(items)
                except Exception:
                    pass

            page.on("response", handle_response)

            # Visit TikTok root to get cookies first
            try:
                await page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=15000)
                await _random_delay(1.5, 2.5)
                # Dismiss any cookie consent
                for selector in [
                    "button:has-text('Accept all')",
                    "button:has-text('Accept All')",
                    "button:has-text('Allow all cookies')",
                    "[class*='cookie'] button",
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await _random_delay(0.5, 1.0)
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            if resp and resp.status == 404:
                return ScrapeResult(
                    status="not_found", platform="tiktok", username=username,
                    error_message="Profile not found.",
                )

            await _random_delay(2.0, 3.0)

            # Check for captcha
            captcha = await page.query_selector(
                "[class*='captcha'], [class*='verify'], [class*='Captcha'], "
                "#captcha-verify-container, [data-e2e='verify-code']"
            )
            if captcha:
                # Debug screenshot
                try:
                    await page.screenshot(path="static/uploads/tiktok_debug_captcha.png")
                except Exception:
                    pass
                return ScrapeResult(
                    status="blocked_by_challenge", platform="tiktok", username=username,
                    error_message="TikTok is showing a captcha. Try again later.",
                )

            # ── Redirect / challenge detection ──
            # If TikTok redirected away from the profile URL to explore, login, or generic feed,
            # the page content is NOT from the target user — abort immediately.
            current_url = page.url.lower()
            expected_path = f"/@{username.lower()}"
            if expected_path not in current_url:
                # Redirected to explore, login wall, or other non-profile page
                redirected_to_generic = any(tok in current_url for tok in [
                    "/explore", "/login", "/foryou", "/for-you", "loginModal",
                ])
                if redirected_to_generic or f"/@" not in current_url:
                    logger.warning(
                        "TikTok: Page redirected from @%s to %s – aborting Playwright strategy.",
                        username, page.url,
                    )
                    return ScrapeResult(
                        status="blocked_by_challenge", platform="tiktok", username=username,
                        error_message="TikTok redirected to a login/challenge page instead of the profile.",
                    )

            # Try to extract embedded JSON from page (profile + items)
            embedded = await page.evaluate("""
                () => {
                    // __UNIVERSAL_DATA_FOR_REHYDRATION__
                    try {
                        const el = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                        if (el) {
                            const d = JSON.parse(el.textContent);
                            const ud = d?.['__DEFAULT_SCOPE__']?.['webapp.user-detail'];
                            const ui = ud?.userInfo;
                            if (ui) {
                                if (ud?.itemList && !ui.itemList) {
                                    ui.itemList = ud.itemList;
                                }
                                return ui;
                            }
                        }
                    } catch(e) {}

                    // SIGI_STATE
                    try {
                        const el = document.getElementById('SIGI_STATE');
                        if (el) {
                            const d = JSON.parse(el.textContent);
                            const users = d?.UserModule?.users || {};
                            const stats = d?.UserModule?.stats || {};
                            const items = d?.ItemModule || {};
                            const userKey = Object.keys(users)[0];
                            if (userKey) {
                                return {
                                    user: users[userKey],
                                    stats: stats[userKey] || {},
                                    _items: items,
                                };
                            }
                        }
                    } catch(e) {}

                    // __NEXT_DATA__
                    try {
                        const el = document.getElementById('__NEXT_DATA__');
                        if (el) {
                            const d = JSON.parse(el.textContent);
                            const pp = d?.props?.pageProps;
                            const ui = pp?.userInfo;
                            if (ui) {
                                if (pp?.items && !ui.itemList) {
                                    ui.itemList = pp.items;
                                }
                                return ui;
                            }
                        }
                    } catch(e) {}

                    return null;
                }
            """)

            # Parse embedded JSON if found and has items
            profile_result = None
            if embedded:
                if "_items" in embedded:
                    items = embedded.pop("_items", {})
                    profile_result = _parse_tt_user_info(username, embedded)
                    if not profile_result.recent_posts and items:
                        profile_result.recent_posts = _parse_tt_items(items)
                else:
                    profile_result = _parse_tt_user_info(username, embedded)

            # If we already have videos from embedded JSON, return early
            if profile_result and profile_result.recent_posts:
                return profile_result

            # ── Aggressive scrolling to trigger TikTok's lazy-loaded video grid ──
            logger.info("TikTok: No videos in embedded JSON for @%s, scrolling to trigger lazy load...", username)

            # Human-like scrolling loop
            for scroll_round in range(6):
                await page.evaluate(f"window.scrollBy(0, {random.randint(400, 800)})")
                await _random_delay(1.0, 2.0)

                # Check if video links appeared after scroll
                video_links = await page.query_selector_all('a[href*="/video/"]')
                if len(video_links) >= 3:
                    logger.info("TikTok: Found %d video links after %d scrolls", len(video_links), scroll_round + 1)
                    break

            # Wait a bit more for any pending network requests
            await _random_delay(1.5, 2.5)

            # ── Extract videos from intercepted API responses ──
            if captured_items:
                # Filter out items that don't belong to target user
                owned_items = [item for item in captured_items if _tt_video_belongs_to_user(item, username)]
                logger.info(
                    "TikTok: Captured %d items from API interception, %d belong to @%s",
                    len(captured_items), len(owned_items), username,
                )
                posts = []
                for item in owned_items[:12]:
                    video = item.get("video", {})
                    stats = item.get("stats", {})
                    music = item.get("music", {})
                    vid_id = item.get("id", "")
                    author_name = username
                    author = item.get("author")
                    if isinstance(author, dict):
                        author_name = author.get("uniqueId", username)
                    elif isinstance(author, str):
                        author_name = author

                    create_time = item.get("createTime")
                    created_at = None
                    if create_time:
                        try:
                            from datetime import datetime, timezone
                            created_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
                        except Exception:
                            created_at = None

                    cover = (
                        video.get("cover")
                        or video.get("dynamicCover")
                        or video.get("originCover")
                    )
                    posts.append(PostItem(
                        id=vid_id,
                        url=f"https://www.tiktok.com/@{author_name}/video/{vid_id}" if vid_id else None,
                        thumbnail=cover,
                        description=item.get("desc") or None,
                        type="video",
                        views=stats.get("playCount"),
                        likes=stats.get("diggCount"),
                        comments=stats.get("commentCount"),
                        shares=stats.get("shareCount"),
                        downloads=stats.get("downloadCount"),
                        duration=video.get("duration"),
                        format=video.get("format") or video.get("codecType") or None,
                        music_title=music.get("title") or None,
                        music_author=music.get("authorName") or None,
                        created_at=created_at,
                    ))

                if posts:
                    if profile_result:
                        profile_result.recent_posts = posts
                        return profile_result
                    # Build from captured_user_info if available
                    if captured_user_info:
                        result = _parse_tt_user_info(username, captured_user_info)
                        result.recent_posts = posts
                        return result
                    return ScrapeResult(
                        status="success",
                        platform="tiktok",
                        username=username,
                        recent_posts=posts,
                    )

            # ── DOM fallback: extract video cards using resilient selectors ──
            # Use structural selectors that survive class name obfuscation
            # Only extract links that belong to the target user's profile
            all_video_links = await page.query_selector_all('a[href*="/video/"]')
            video_links = []
            for link in all_video_links:
                href = await link.get_attribute("href") or ""
                # Only keep links that contain /@username/video/
                if f"/@{username.lower()}/video/" in href.lower() or f"/@{username}/video/" in href:
                    video_links.append(link)
                elif "/video/" in href and "@" not in href:
                    # Relative link without username - may still be user's; keep with caution
                    video_links.append(link)
            posts: list[PostItem] = []

            for link in video_links[:12]:
                video_url = await link.get_attribute("href")
                if video_url and not video_url.startswith("http"):
                    video_url = f"https://www.tiktok.com{video_url}"

                # Extract video ID from URL
                vid_id = None
                if video_url:
                    vid_match = re.search(r"/video/(\d+)", video_url)
                    if vid_match:
                        vid_id = vid_match.group(1)

                # Get thumbnail from the link's container or parent
                thumbnail = None
                # Try img inside the link
                img_el = await link.query_selector("img")
                if img_el:
                    thumbnail = await img_el.get_attribute("src")

                # Try parent container's img
                if not thumbnail:
                    parent = await link.evaluate_handle("el => el.closest('div')")
                    if parent:
                        img_in_parent = await parent.query_selector("img")
                        if img_in_parent:
                            thumbnail = await img_in_parent.get_attribute("src")

                # Get description from title/aria-label
                desc = await link.get_attribute("title") or await link.get_attribute("aria-label")

                # Get view count - look for sibling/child strong or span elements
                views_text = None
                try:
                    views_el = await link.query_selector(
                        "[data-e2e='video-views'], strong, span[class*='Count']"
                    )
                    if views_el:
                        views_text = await views_el.inner_text()
                except Exception:
                    pass

                posts.append(PostItem(
                    id=vid_id,
                    url=video_url,
                    thumbnail=thumbnail,
                    description=desc,
                    type="video",
                    views=_parse_count(views_text),
                ))

            # If we still got no posts, try a broader selector approach
            if not posts:
                # Look for any container that wraps video thumbnails
                containers = await page.query_selector_all(
                    "[data-e2e='user-post-item'], "
                    "[data-e2e='user-post-item-list'] > div"
                )
                for container in containers[:12]:
                    link_el = await container.query_selector("a[href*='/video/']")
                    if not link_el:
                        link_el = await container.query_selector("a")
                    video_url = await link_el.get_attribute("href") if link_el else None
                    if video_url and not video_url.startswith("http"):
                        video_url = f"https://www.tiktok.com{video_url}"

                    img_el = await container.query_selector("img")
                    thumbnail = await img_el.get_attribute("src") if img_el else None

                    views_el = await container.query_selector("strong, [data-e2e='video-views']")
                    views_text = await views_el.inner_text() if views_el else None

                    desc_el = await container.query_selector("a[href*='/video/']")
                    desc = None
                    if desc_el:
                        desc = await desc_el.get_attribute("title") or await desc_el.get_attribute("aria-label")

                    posts.append(PostItem(
                        url=video_url,
                        thumbnail=thumbnail,
                        description=desc,
                        type="video",
                        views=_parse_count(views_text),
                    ))

            # ── Debug screenshot if no videos found ──
            if not posts:
                try:
                    import os
                    os.makedirs("static/uploads", exist_ok=True)
                    await page.screenshot(path="static/uploads/tiktok_debug.png", full_page=True)
                    logger.warning(
                        "TikTok: No videos extracted for @%s. Debug screenshot saved to static/uploads/tiktok_debug.png",
                        username,
                    )
                except Exception as ss_err:
                    logger.warning("TikTok: Screenshot failed: %s", ss_err)

            # Build result with DOM-extracted stats if no profile_result
            if profile_result:
                if posts:
                    profile_result.recent_posts = posts
                    profile_result.status = "success"
                    return profile_result
                if (profile_result.posts_count or 0) == 0:
                    profile_result.status = "success"
                    return profile_result

            if captured_user_info:
                result = _parse_tt_user_info(username, captured_user_info)
                if posts:
                    result.recent_posts = posts
                    result.status = "success"
                    return result
                if (result.posts_count or 0) == 0:
                    result.status = "success"
                    return result
                result.status = "partial_success"
                result.error_message = (
                    "Profile loaded, but TikTok videos could not be extracted due to anti-bot checks or layout changes."
                )
                return result

            # Pure DOM extraction
            display_name = await _safe_text(page,
                "[data-e2e='user-subtitle'], [data-e2e='user-title'], "
                "h1[class*='Title'], h2[class*='ShareTitle'], "
                "[class*='UserTitle'] h1, header h1"
            )
            bio = await _safe_text(page,
                "[data-e2e='user-bio'], [class*='ShareDesc'], "
                "[class*='UserBio'] span, header h2 + div"
            )
            avatar = await _safe_attr(page,
                "[data-e2e='user-avatar'] img, [class*='ImgAvatar'] img, "
                "[class*='UserAvatar'] img, [class*='avatar'] img[src*='tiktok']",
                "src"
            )
            followers_text = await _safe_text(page,
                "[data-e2e='followers-count'], [title*='Followers'] strong"
            )
            following_text = await _safe_text(page,
                "[data-e2e='following-count'], [title*='Following'] strong"
            )
            likes_text = await _safe_text(page,
                "[data-e2e='likes-count'], [title*='Likes'] strong"
            )

            if _parse_count(followers_text) is not None or posts:
                has_posts = bool(posts)
                return ScrapeResult(
                    status="success" if has_posts else "partial_success",
                    platform="tiktok",
                    username=username,
                    display_name=display_name or username,
                    avatar=avatar,
                    followers=_parse_count(followers_text),
                    following=_parse_count(following_text),
                    likes=_parse_count(likes_text),
                    bio=bio,
                    recent_posts=posts,
                    error_message=(
                        None
                        if has_posts
                        else "Profile loaded, but TikTok videos could not be extracted due to anti-bot checks or layout changes."
                    ),
                )

            return None

        except Exception as e:
            logger.exception("TikTok Playwright strategy failed for %s", username)
            return ScrapeResult(
                status="error", platform="tiktok", username=username,
                error_message=str(e),
            )
        finally:
            await browser.close()


async def _tt_strategy_meta(username: str) -> ScrapeResult | None:
    """Strategy 3: Parse TikTok meta tags for basic profile info."""
    import httpx

    url = f"https://www.tiktok.com/@{username}"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                return ScrapeResult(
                    status="not_found", platform="tiktok", username=username,
                    error_message="Profile not found.",
                )

            html = resp.text

            # og:description often contains: "username (@handle) on TikTok | 1.2M Followers. ..."
            og_desc = _extract_meta(html, "og:description")
            og_title = _extract_meta(html, "og:title")
            og_image = _extract_meta(html, "og:image")

            followers = following = likes = None
            if og_desc:
                # Pattern: "1.2M Followers. 500 Following. 10M Likes."
                f_match = re.search(r"([\d,.]+[KMB]?)\s*Followers", og_desc, re.IGNORECASE)
                fo_match = re.search(r"([\d,.]+[KMB]?)\s*Following", og_desc, re.IGNORECASE)
                l_match = re.search(r"([\d,.]+[KMB]?)\s*Likes", og_desc, re.IGNORECASE)
                if f_match:
                    followers = _parse_count(f_match.group(1))
                if fo_match:
                    following = _parse_count(fo_match.group(1))
                if l_match:
                    likes = _parse_count(l_match.group(1))

            display_name = None
            if og_title:
                # Format: "Name (@username) | TikTok"
                name_match = re.match(r"^(.+?)\s*\(@", og_title)
                if name_match:
                    display_name = name_match.group(1).strip()

            if followers is not None or display_name:
                return ScrapeResult(
                    status="success",
                    platform="tiktok",
                    username=username,
                    display_name=display_name or username,
                    avatar=og_image,
                    followers=followers,
                    following=following,
                    likes=likes,
                    bio=None,
                    recent_posts=[],
                )

    except Exception as e:
        logger.debug("TikTok meta strategy failed for %s: %s", username, e)

    return None


# ─── Instagram Scraper ───────────────────────────────────────────────────────

async def _scrape_instagram(username: str) -> ScrapeResult:
    """
    Scrape Instagram profile using multiple strategies:
    1. Direct HTTP API request (fastest, no browser)
    2. Playwright with aggressive response interception
    3. Meta tag / SEO data fallback
    """
    # Strategy 1: Direct HTTP API call (no browser needed)
    result = await _ig_strategy_http_api(username)
    if result and result.status == "success" and (result.followers is not None or result.recent_posts):
        return result

    # Strategy 2: Playwright with response interception + embedded JSON
    result = await _ig_strategy_playwright(username)
    if result and result.status == "success" and (result.followers is not None or result.recent_posts):
        return result

    # Strategy 3: Meta tags / og:description parsing (last resort)
    result = await _ig_strategy_meta_tags(username)
    if result and result.status == "success" and result.followers is not None:
        return result

    # If all strategies returned something, return the best one; otherwise blocked
    if result:
        return result
    return ScrapeResult(
        status="blocked_by_challenge",
        platform="instagram",
        username=username,
        error_message="Instagram blocked all scraping attempts. The profile may be private or login is required.",
    )


async def _ig_strategy_http_api(username: str) -> ScrapeResult | None:
    """Strategy 1: Hit Instagram's web API with session cookies."""
    import httpx

    ua = random.choice(USER_AGENTS)
    base_headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            # Step 1: Visit the profile page to get session cookies (csrftoken, mid, ig_did)
            profile_page_url = f"https://www.instagram.com/{username}/"
            page_resp = await client.get(profile_page_url, headers=base_headers)

            if page_resp.status_code == 404:
                return ScrapeResult(
                    status="not_found", platform="instagram", username=username,
                    error_message="Profile not found.",
                )

            # Extract cookies and csrf token
            cookies = dict(client.cookies)
            csrf_token = cookies.get("csrftoken", "")

            # Try to extract data from the page HTML directly (meta tags / embedded JSON)
            if page_resp.status_code == 200:
                html = page_resp.text

                # Try og:description for quick stats
                og_desc = _extract_meta(html, "og:description")
                og_title = _extract_meta(html, "og:title")
                og_image = _extract_meta(html, "og:image")

                # Look for embedded JSON in script tags
                # Pattern 1: "edge_followed_by":{"count":12345}
                followers_m = re.search(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)', html)
                following_m = re.search(r'"edge_follow"\s*:\s*\{\s*"count"\s*:\s*(\d+)', html)
                posts_m = re.search(r'"edge_owner_to_timeline_media"\s*:\s*\{\s*"count"\s*:\s*(\d+)', html)
                name_m = re.search(r'"full_name"\s*:\s*"([^"]*)"', html)
                bio_m = re.search(r'"biography"\s*:\s*"([^"]*)"', html)
                pic_m = re.search(r'"profile_pic_url_hd"\s*:\s*"([^"]*)"', html)
                verified_m = re.search(r'"is_verified"\s*:\s*(true|false)', html)

                if followers_m:
                    followers = int(followers_m.group(1))
                    following = int(following_m.group(1)) if following_m else None
                    posts_count = int(posts_m.group(1)) if posts_m else None
                    full_name = name_m.group(1) if name_m else None
                    biography = bio_m.group(1).encode().decode('unicode_escape', errors='ignore') if bio_m else None
                    pic_url = pic_m.group(1).replace("\\u0026", "&") if pic_m else og_image
                    is_verified = verified_m.group(1) == "true" if verified_m else False

                    # Try to extract posts from embedded JSON
                    posts = _extract_ig_posts_from_html(html)

                    return ScrapeResult(
                        status="success",
                        platform="instagram",
                        username=username,
                        display_name=full_name or username,
                        avatar=pic_url,
                        followers=followers,
                        following=following,
                        posts_count=posts_count,
                        bio=biography,
                        is_verified=is_verified,
                        recent_posts=posts,
                    )

                # Fallback: parse og:description
                if og_desc:
                    followers = following = posts_count = None
                    parts = re.findall(r"([\d,.]+[KMB]?)\s+(Followers|Following|Posts)", og_desc, re.IGNORECASE)
                    for value, label in parts:
                        parsed = _parse_count(value)
                        if label.lower() == "followers":
                            followers = parsed
                        elif label.lower() == "following":
                            following = parsed
                        elif label.lower() == "posts":
                            posts_count = parsed

                    display_name = None
                    if og_title:
                        name_match = re.match(r"^(.+?)\s*\(@", og_title)
                        if name_match:
                            display_name = name_match.group(1).strip()

                    if followers is not None:
                        return ScrapeResult(
                            status="success",
                            platform="instagram",
                            username=username,
                            display_name=display_name or username,
                            avatar=og_image,
                            followers=followers,
                            following=following,
                            posts_count=posts_count,
                            bio=None,
                            recent_posts=[],
                        )

            # Step 2: Try the API with acquired cookies
            api_headers = {
                "User-Agent": ua,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "X-IG-App-ID": "936619743392459",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": csrf_token,
                "Referer": f"https://www.instagram.com/{username}/",
                "Origin": "https://www.instagram.com",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }

            api_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            resp = await client.get(api_url, headers=api_headers)

            if resp.status_code == 200:
                data = resp.json()
                user = data.get("data", {}).get("user")
                if user:
                    return _parse_instagram_api_data(username, user)

            # Try ?__a=1&__d=dis
            profile_url = f"https://www.instagram.com/{username}/?__a=1&__d=dis"
            resp2 = await client.get(profile_url, headers=api_headers)
            if resp2.status_code == 200:
                try:
                    data2 = resp2.json()
                    user2 = data2.get("graphql", {}).get("user")
                    if not user2:
                        user2 = data2.get("data", {}).get("user")
                    if user2:
                        return _parse_instagram_api_data(username, user2)
                except Exception:
                    pass

    except Exception as e:
        logger.debug("IG HTTP API strategy failed for %s: %s", username, e)

    return None


def _extract_ig_posts_from_html(html: str) -> list[PostItem]:
    """Extract Instagram posts from embedded JSON in HTML."""
    posts: list[PostItem] = []
    try:
        # Look for edge_owner_to_timeline_media edges
        pattern = r'"edge_owner_to_timeline_media"\s*:\s*\{[^}]*"edges"\s*:\s*(\[.*?\])\s*\}'
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            return posts

        import json as _json
        edges_str = match.group(1)
        # This might be truncated, try to parse what we can
        edges = _json.loads(edges_str)

        for edge in edges[:12]:
            node = edge.get("node", {})
            shortcode = node.get("shortcode", "")
            post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else None
            thumbnail = node.get("thumbnail_src") or node.get("display_url")
            is_video = node.get("is_video", False)
            typename = node.get("__typename", "")

            caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
            caption = caption_edges[0]["node"]["text"] if caption_edges else None

            post_likes = node.get("edge_liked_by", {}).get("count") or node.get("edge_media_preview_like", {}).get("count")
            post_comments = node.get("edge_media_to_comment", {}).get("count")
            video_views = node.get("video_view_count")

            taken_at = node.get("taken_at_timestamp")
            created_at = None
            if taken_at:
                try:
                    from datetime import datetime, timezone
                    created_at = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat()
                except Exception:
                    pass

            if "Video" in typename or is_video:
                post_type = "video"
            elif "Sidecar" in typename:
                post_type = "sidecar"
            else:
                post_type = "image"

            posts.append(PostItem(
                id=node.get("id", shortcode),
                url=post_url,
                thumbnail=thumbnail,
                description=caption[:200] if caption else None,
                type=post_type,
                views=video_views,
                likes=post_likes,
                comments=post_comments,
                created_at=created_at,
            ))
    except Exception:
        pass
    return posts


async def _ig_strategy_playwright(username: str) -> ScrapeResult | None:
    """Strategy 2: Use Playwright to intercept API responses and parse embedded data."""
    from playwright.async_api import async_playwright

    url = f"https://www.instagram.com/{username}/"
    captured_data: dict[str, Any] = {}

    async with async_playwright() as pw:
        browser, page = await _get_stealth_page(pw)
        try:
            # Intercept all relevant API responses
            async def handle_response(response):
                nonlocal captured_data
                try:
                    resp_url = response.url
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")
                    if "json" not in ct and "javascript" not in ct:
                        return
                    if any(k in resp_url for k in [
                        "web_profile_info",
                        "graphql/query",
                        "api/v1/users/",
                        "__a=1",
                        "xdt_api__v1__users__web_profile_info",
                    ]):
                        json_body = await response.json()
                        # web_profile_info format
                        user = json_body.get("data", {}).get("user")
                        if user and ("edge_followed_by" in user or "follower_count" in user):
                            captured_data.update(user)
                            return
                        # xdt format (newer)
                        xdt_user = json_body.get("data", {}).get("xdt_api__v1__users__web_profile_info", {}).get("user")
                        if xdt_user:
                            captured_data.update(xdt_user)
                            return
                        # graphql format
                        user = json_body.get("graphql", {}).get("user")
                        if user:
                            captured_data.update(user)
                            return
                        # v1 users format
                        user = json_body.get("user")
                        if user and ("follower_count" in user or "edge_followed_by" in user):
                            captured_data.update(user)
                except Exception:
                    pass

            page.on("response", handle_response)

            # First visit Instagram homepage to get session cookies
            try:
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
                await _random_delay(1.5, 2.5)

                # Dismiss cookie consent
                for btn_text in ["Decline optional cookies", "Allow essential and optional cookies",
                                 "Accept All", "Allow All Cookies", "Accept"]:
                    try:
                        btn = page.locator(f"button:has-text('{btn_text}')").first
                        if await btn.is_visible(timeout=1000):
                            await btn.click()
                            await _random_delay(0.5, 1.0)
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            # Now navigate to the profile
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _random_delay(3.0, 5.0)

            # Dismiss login modals / popups
            for selector in [
                "button:has-text('Not Now')",
                "button:has-text('Not now')",
                "[aria-label='Close']",
                "button:has-text('Decline optional cookies')",
                "button:has-text('Allow essential and optional cookies')",
                "div[role='dialog'] button:first-child",
            ]:
                try:
                    el = page.locator(selector).first
                    if await el.is_visible(timeout=1500):
                        await el.click()
                        await _random_delay(0.5, 1.0)
                except Exception:
                    pass

            if resp and resp.status == 404:
                return ScrapeResult(
                    status="not_found", platform="instagram", username=username,
                    error_message="Profile not found.",
                )

            # Check for login wall - if we see login form, try to work around it
            login_wall = False
            try:
                login_form = await page.query_selector('input[name="username"]')
                if login_form:
                    login_wall = True
                    # The page might still have rendered meta tags and partial data before redirect
                    logger.info("IG login wall detected for %s, extracting what we can", username)
            except Exception:
                pass

            # Give time for API calls to complete
            await _random_delay(2.0, 4.0)

            # If not login wall, try scrolling to trigger lazy loads
            if not login_wall:
                try:
                    await page.evaluate("window.scrollBy(0, 800)")
                    await _random_delay(1.0, 2.0)
                    await page.evaluate("window.scrollBy(0, 800)")
                    await _random_delay(1.0, 2.0)
                except Exception:
                    pass

            # Check if we captured data from API interception
            if captured_data:
                return _parse_instagram_api_data(username, captured_data)

            # Try to extract data from embedded JSON in page source
            embedded = await page.evaluate("""
                () => {
                    // Strategy A: window._sharedData
                    try {
                        if (window._sharedData?.entry_data?.ProfilePage?.[0]?.graphql?.user) {
                            return window._sharedData.entry_data.ProfilePage[0].graphql.user;
                        }
                    } catch(e) {}

                    // Strategy B: __additionalDataLoaded
                    try {
                        if (window.__additionalDataLoaded) {
                            const keys = Object.keys(window.__additionalDataLoaded);
                            for (const k of keys) {
                                const u = window.__additionalDataLoaded[k]?.graphql?.user;
                                if (u) return u;
                            }
                        }
                    } catch(e) {}

                    // Strategy C: Search script tags for JSON with user data
                    try {
                        const scripts = document.querySelectorAll('script[type="application/json"]');
                        for (const s of scripts) {
                            const text = s.textContent || '';
                            if (text.includes('edge_followed_by') || text.includes('follower_count')) {
                                const parsed = JSON.parse(text);
                                // Try to find user data in nested structure
                                const findUser = (obj, depth=0) => {
                                    if (depth > 5 || !obj || typeof obj !== 'object') return null;
                                    if (obj.edge_followed_by || obj.follower_count) return obj;
                                    for (const k of Object.keys(obj)) {
                                        const result = findUser(obj[k], depth + 1);
                                        if (result) return result;
                                    }
                                    return null;
                                };
                                const found = findUser(parsed);
                                if (found) return found;
                            }
                        }
                    } catch(e) {}

                    // Strategy D: Look for require/relay data in all script tags
                    try {
                        const allScripts = document.querySelectorAll('script');
                        for (const s of allScripts) {
                            const text = s.textContent || '';
                            if (text.includes('XIGSharedData') || text.includes('xdt_api__v1__users__web_profile_info')
                                || text.includes('edge_followed_by') || text.includes('follower_count')) {
                                // Find JSON-like user data via regex
                                const match = text.match(/"edge_followed_by"\\s*:\\s*\\{\\s*"count"\\s*:\\s*(\\d+)/);
                                const followingMatch = text.match(/"edge_follow"\\s*:\\s*\\{\\s*"count"\\s*:\\s*(\\d+)/);
                                const nameMatch = text.match(/"full_name"\\s*:\\s*"([^"]+)"/);
                                const bioMatch = text.match(/"biography"\\s*:\\s*"([^"]+)"/);
                                const picMatch = text.match(/"profile_pic_url(?:_hd)?"\\s*:\\s*"([^"]+)"/);
                                const postsMatch = text.match(/"edge_owner_to_timeline_media"\\s*:\\s*\\{\\s*"count"\\s*:\\s*(\\d+)/);
                                const verifiedMatch = text.match(/"is_verified"\\s*:\\s*(true|false)/);

                                // Also try follower_count format (newer API)
                                const fcMatch = text.match(/"follower_count"\\s*:\\s*(\\d+)/);
                                const fgMatch = text.match(/"following_count"\\s*:\\s*(\\d+)/);
                                const mcMatch = text.match(/"media_count"\\s*:\\s*(\\d+)/);

                                if (match || fcMatch) {
                                    return {
                                        edge_followed_by: { count: parseInt(match ? match[1] : fcMatch[1]) },
                                        edge_follow: { count: parseInt(followingMatch ? followingMatch[1] : (fgMatch ? fgMatch[1] : '0')) },
                                        full_name: nameMatch ? nameMatch[1] : null,
                                        biography: bioMatch ? bioMatch[1] : null,
                                        profile_pic_url_hd: picMatch ? picMatch[1].replace(/\\\\u0026/g, '&') : null,
                                        edge_owner_to_timeline_media: { count: parseInt(postsMatch ? postsMatch[1] : (mcMatch ? mcMatch[1] : '0')), edges: [] },
                                        is_verified: verifiedMatch ? verifiedMatch[1] === 'true' : false,
                                    };
                                }
                            }
                        }
                    } catch(e) {}

                    return null;
                }
            """)

            if embedded:
                return _parse_instagram_api_data(username, embedded)

            # DOM-based fallback - try to get stats from visible page
            dom_result = await _parse_instagram_dom(page, username)
            if dom_result and dom_result.status == "success":
                return dom_result

            # Last resort: get page HTML and try regex extraction
            html_content = await page.content()
            # Try meta tags from rendered HTML
            og_desc = _extract_meta(html_content, "og:description")
            og_title = _extract_meta(html_content, "og:title")
            og_image = _extract_meta(html_content, "og:image")

            if og_desc:
                followers = following = posts_count = None
                parts = re.findall(r"([\d,.]+[KMB]?)\s+(Followers|Following|Posts)", og_desc, re.IGNORECASE)
                for value, label in parts:
                    parsed = _parse_count(value)
                    if label.lower() == "followers":
                        followers = parsed
                    elif label.lower() == "following":
                        following = parsed
                    elif label.lower() == "posts":
                        posts_count = parsed

                display_name = None
                if og_title:
                    name_match = re.match(r"^(.+?)\s*\(@", og_title)
                    if name_match:
                        display_name = name_match.group(1).strip()

                if followers is not None:
                    return ScrapeResult(
                        status="success",
                        platform="instagram",
                        username=username,
                        display_name=display_name or username,
                        avatar=og_image,
                        followers=followers,
                        following=following,
                        posts_count=posts_count,
                        bio=None,
                        recent_posts=[],
                    )

            # Save debug screenshot
            try:
                screenshot_path = os.path.join("static", "uploads", f"debug_ig_{username}.png")
                await page.screenshot(path=screenshot_path)
                logger.info("IG debug screenshot saved: %s", screenshot_path)
            except Exception:
                pass

            return None

        except Exception as e:
            logger.exception("IG Playwright strategy failed for %s", username)
            return ScrapeResult(
                status="error", platform="instagram", username=username,
                error_message=str(e),
            )
        finally:
            await browser.close()


async def _ig_strategy_meta_tags(username: str) -> ScrapeResult | None:
    """Strategy 3: Parse Instagram meta tags / og:description via simple HTTP."""
    import httpx

    url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 404:
                return ScrapeResult(
                    status="not_found", platform="instagram", username=username,
                    error_message="Profile not found.",
                )

            html = resp.text

            # Parse og:description: "1.2M Followers, 500 Following, 2,000 Posts - See Instagram photos..."
            og_desc = _extract_meta(html, "og:description")
            og_title = _extract_meta(html, "og:title")
            og_image = _extract_meta(html, "og:image")

            followers = following = posts_count = None
            if og_desc:
                parts = re.findall(r"([\d,.]+[KMB]?)\s+(Followers|Following|Posts)", og_desc, re.IGNORECASE)
                for value, label in parts:
                    parsed = _parse_count(value)
                    label_lower = label.lower()
                    if label_lower == "followers":
                        followers = parsed
                    elif label_lower == "following":
                        following = parsed
                    elif label_lower == "posts":
                        posts_count = parsed

            display_name = None
            if og_title:
                # Format: "Name (@username) • Instagram photos and videos"
                name_match = re.match(r"^(.+?)\s*\(@", og_title)
                if name_match:
                    display_name = name_match.group(1).strip()

            if followers is not None or display_name:
                return ScrapeResult(
                    status="success",
                    platform="instagram",
                    username=username,
                    display_name=display_name or username,
                    avatar=og_image,
                    followers=followers,
                    following=following,
                    posts_count=posts_count,
                    bio=None,
                    recent_posts=[],
                )

    except Exception as e:
        logger.debug("IG meta tag strategy failed for %s: %s", username, e)

    return None


def _extract_meta(html: str, prop: str) -> str | None:
    """Extract content from a meta tag by property or name."""
    pattern = rf'<meta\s+(?:property|name)=["\']?{re.escape(prop)}["\']?\s+content=["\']([^"\']*)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return match.group(1)
    # Try reversed attribute order
    pattern2 = rf'<meta\s+content=["\']([^"\']*)["\']?\s+(?:property|name)=["\']?{re.escape(prop)}["\']'
    match2 = re.search(pattern2, html, re.IGNORECASE)
    if match2:
        return match2.group(1)
    return None


def _parse_instagram_api_data(username: str, data: dict) -> ScrapeResult:
    """Parse Instagram profile from intercepted API JSON."""
    followers = data.get("edge_followed_by", {}).get("count") or data.get("follower_count")
    following = data.get("edge_follow", {}).get("count") or data.get("following_count")
    posts_count = data.get("edge_owner_to_timeline_media", {}).get("count") or data.get("media_count")

    display_name = data.get("full_name", username)
    bio = data.get("biography", "")
    avatar = data.get("profile_pic_url_hd") or data.get("profile_pic_url")
    is_verified = data.get("is_verified", False)

    # Extract recent posts from edge_owner_to_timeline_media
    posts: list[PostItem] = []
    edges = data.get("edge_owner_to_timeline_media", {}).get("edges", [])
    for edge in edges[:12]:
        node = edge.get("node", {})
        shortcode = node.get("shortcode", "")
        post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else None
        thumbnail = node.get("thumbnail_src") or node.get("display_url")
        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else None
        post_likes = node.get("edge_liked_by", {}).get("count") or node.get("edge_media_preview_like", {}).get("count")
        post_comments = node.get("edge_media_to_comment", {}).get("count")
        video_views = node.get("video_view_count")
        is_video = node.get("is_video", False)
        taken_at = node.get("taken_at_timestamp")
        created_at = None
        if taken_at:
            try:
                from datetime import datetime, timezone
                created_at = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat()
            except Exception:
                created_at = str(taken_at)

        # Determine post type
        typename = node.get("__typename", "")
        if "Video" in typename or is_video:
            post_type = "video"
        elif "Sidecar" in typename:
            post_type = "sidecar"
        else:
            post_type = "image"

        posts.append(PostItem(
            id=node.get("id", shortcode),
            url=post_url,
            thumbnail=thumbnail,
            description=caption[:200] if caption else None,
            type=post_type,
            views=video_views,
            likes=post_likes,
            comments=post_comments,
            created_at=created_at,
        ))

    return ScrapeResult(
        status="success",
        platform="instagram",
        username=username,
        display_name=display_name,
        avatar=avatar,
        followers=followers,
        following=following,
        posts_count=posts_count,
        bio=bio,
        is_verified=is_verified,
        recent_posts=posts,
    )


async def _parse_instagram_dom(page, username: str) -> ScrapeResult:
    """Fallback DOM parsing for Instagram profiles."""
    display_name = await _safe_text(page,
        "header h2, header span[class*='username'], "
        "[class*='ProfileHeader'] h2, section > main h2"
    )
    bio = await _safe_text(page,
        "header [class*='biography'], header section > div > span, "
        "[class*='ProfileBio'], [class*='-bio'] span"
    )
    avatar = await _safe_attr(page,
        "header img[alt*='profile'], header img[data-testid='user-avatar'], "
        "img[alt*=\"'s profile picture\"], header canvas + img",
        "src"
    )

    # Try to get stats from meta tags in page head first
    html_content = await page.content()
    og_desc = _extract_meta(html_content, "og:description")
    followers = following = posts_count = None
    if og_desc:
        parts = re.findall(r"([\d,.]+[KMB]?)\s+(Followers|Following|Posts)", og_desc, re.IGNORECASE)
        for value, label in parts:
            parsed = _parse_count(value)
            label_lower = label.lower()
            if label_lower == "followers":
                followers = parsed
            elif label_lower == "following":
                following = parsed
            elif label_lower == "posts":
                posts_count = parsed

    # If meta tags didn't work, try visible counters
    if followers is None:
        stats_elements = await page.query_selector_all(
            "header section ul li span, header section ul li a span, "
            "[class*='CountInfo'] span, [class*='_ac2a'] span"
        )
        stats_texts = []
        for el in stats_elements:
            t = await el.inner_text()
            if t and t.strip():
                stats_texts.append(t.strip())
        if len(stats_texts) >= 3:
            posts_count = _parse_count(stats_texts[0])
            followers = _parse_count(stats_texts[1])
            following = _parse_count(stats_texts[2])

    # Get post thumbnails – try multiple selectors for modern IG
    posts: list[PostItem] = []
    post_links = await page.query_selector_all(
        "article a[href*='/p/'], main a[href*='/p/'], "
        "a[href*='/reel/'], [class*='_aagu'] a, "
        "div[class*='_aagw'] a"
    )
    for link in post_links[:12]:
        href = await link.get_attribute("href")
        post_url = f"https://www.instagram.com{href}" if href and not href.startswith("http") else href
        img = await link.query_selector("img")
        thumbnail = await img.get_attribute("src") if img else None
        # Try srcset for higher-res image
        if img and not thumbnail:
            srcset = await img.get_attribute("srcset")
            if srcset:
                # Take the last (highest-res) URL from srcset
                parts = srcset.split(",")
                if parts:
                    thumbnail = parts[-1].strip().split(" ")[0]
        posts.append(PostItem(url=post_url, thumbnail=thumbnail))

    return ScrapeResult(
        status="success",
        platform="instagram",
        username=username,
        display_name=display_name or username,
        avatar=avatar,
        followers=followers,
        following=following,
        posts_count=posts_count,
        bio=bio,
        recent_posts=posts,
    )


# ─── Facebook Scraper ────────────────────────────────────────────────────────

async def _scrape_facebook(username: str) -> ScrapeResult:
    """Scrape a public Facebook page for basic stats and recent posts."""
    from playwright.async_api import async_playwright

    url = f"https://www.facebook.com/{username}"

    async with async_playwright() as pw:
        browser, page = await _get_stealth_page(pw)
        try:
            # First visit Facebook root to get cookies
            try:
                await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=15000)
                await _random_delay(1.5, 2.5)

                # Dismiss cookie consent on root
                for selector in [
                    "button[data-cookiebanner='accept_button']",
                    "button:has-text('Accept All')",
                    "button:has-text('Allow essential and optional cookies')",
                    "button:has-text('Allow All Cookies')",
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible(timeout=2000):
                            await btn.click()
                            await _random_delay(0.5, 1.0)
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            # Navigate to the target page
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await _random_delay(2.0, 4.0)

            # Dismiss cookie consent / login modals
            for selector in [
                "button[data-cookiebanner='accept_button']",
                "[data-testid='cookie-policy-manage-dialog-accept-button']",
                "button:has-text('Accept All')",
                "button:has-text('Not Now')",
                "[role='dialog'] [aria-label='Close']",
                "[aria-label='Close']",
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=1500):
                        await btn.click()
                        await _random_delay(0.5, 1.0)
                except Exception:
                    pass

            await _random_delay(1.0, 2.0)

            # Check for login wall - try to bypass
            login_wall = await page.query_selector("[id='login_popup_cta_form'], [class*='_585r'], form[action*='login']")
            if login_wall:
                # Try pressing Escape or clicking close button
                await page.keyboard.press("Escape")
                await _random_delay(0.5, 1.0)
                # Try close buttons
                for selector in ["[aria-label='Close']", "div[role='dialog'] button"]:
                    try:
                        btn = await page.query_selector(selector)
                        if btn:
                            await btn.click()
                            await _random_delay(0.5, 1.0)
                            break
                    except Exception:
                        pass

            # Check if page exists
            not_found = await page.query_selector("[class*='UINotFound'], [class*='not_found']")
            if not_found:
                return ScrapeResult(
                    status="not_found", platform="facebook", username=username,
                    error_message="Page not found."
                )

            # Extract page name
            display_name = await _safe_text(page, "h1, [class*='PageTitle'], [role='main'] h1")

            # Extract avatar
            avatar = await _safe_attr(
                page,
                "[aria-label='Profile photo'] img, [class*='profilePhoto'] img, "
                "[data-imgperflogname='profilePhoto'] img",
                "src"
            )

            # Extract category (usually below the page name)
            category = await _safe_text(
                page,
                "[data-testid='page_category'], "
                "a[href*='/pages/category/'], "
                "span:below(h1):has-text('·')"  # fallback
            )
            html_content = await page.content()
            if not category:
                # Try from meta or visible text
                cat_match = re.search(r'"category_name"\s*:\s*"([^"]+)"', html_content)
                if cat_match:
                    category = cat_match.group(1)

            # Extract about/bio/description text
            bio = await _safe_text(
                page,
                "[data-testid='page_about'], "
                "[class*='PageAbout'], "
                "[class*='profile_intro_card'] span"
            )

            # Try to extract about and description from page HTML
            about_text = None
            description_text = None
            about_match = re.search(r'"about"\s*:\s*"([^"]*)"', html_content)
            if about_match:
                about_text = about_match.group(1).encode().decode('unicode_escape', errors='ignore')
            desc_match = re.search(r'"page_about_fields".*?"text"\s*:\s*"([^"]*)"', html_content, re.DOTALL)
            if desc_match:
                description_text = desc_match.group(1).encode().decode('unicode_escape', errors='ignore')
            if not about_text:
                about_text = bio
            if not description_text:
                # Try meta description
                description_text = _extract_meta(html_content, "description")

            # Extract is_verified
            is_verified = False
            verified_el = await page.query_selector(
                "[aria-label='Verified'], [data-testid='verified-badge'], "
                "svg[aria-label*='erified']"
            )
            if verified_el:
                is_verified = True

            # Extract likes and followers from about section or visible text
            page_text = await page.inner_text("body")

            followers = _extract_fb_stat(page_text, r"([\d,.]+[KMB]?)\s*(?:followers|people follow)")
            likes = _extract_fb_stat(page_text, r"([\d,.]+[KMB]?)\s*(?:likes|people like)")
            fan_count = likes  # FB page likes = fan count
            following = _extract_fb_stat(page_text, r"([\d,.]+[KMB]?)\s*(?:following)")
            if following is None:
                # Facebook pages usually expose followers/likes, not following.
                following = followers

            # Scroll to load posts – more aggressive scrolling
            for _ in range(4):
                await page.evaluate("window.scrollBy(0, 800)")
                await _random_delay(1.5, 2.5)

            # Extract recent posts
            posts: list[PostItem] = []
            post_containers = await page.query_selector_all(
                "[role='article'], [data-ad-preview='message'], [class*='userContentWrapper']"
            )

            for container in post_containers[:10]:
                try:
                    # Get post text
                    text_el = await container.query_selector(
                        "[data-ad-preview='message'], [class*='userContent'], "
                        "[dir='auto']"
                    )
                    desc = await text_el.inner_text() if text_el else None
                    if desc and len(desc) > 200:
                        desc = desc[:200] + "..."

                    # Get post link (prefer canonical post/photo/video/reel URLs)
                    post_url = await _extract_fb_post_url(container)

                    # Get best possible thumbnail (skip small icons/avatars)
                    thumbnail = await _extract_fb_thumbnail(container)

                    # Try video poster as fallback for video posts
                    is_video_post = False
                    if not thumbnail:
                        video_el = await container.query_selector("video[poster]")
                        if video_el:
                            thumbnail = await video_el.get_attribute("poster")
                            is_video_post = True

                    # Try background-image CSS on divs (FB often uses this)
                    if not thumbnail:
                        thumbnail = await _extract_fb_bg_image(container)

                    # Determine post type
                    post_type = "post"
                    if is_video_post or (post_url and ("/video" in post_url or "/reel" in post_url)):
                        post_type = "video"
                    elif thumbnail or (post_url and "/photo" in post_url):
                        post_type = "image"
                    elif desc:
                        post_type = "text"

                    # Try to extract engagement metrics from the post
                    post_likes = None
                    post_comments = None
                    post_shares = None
                    post_reactions = None

                    # Try extracting from aria-labels or visible counters
                    try:
                        metrics_text = await container.inner_text()
                        like_m = re.search(r"(?i)([\d,.]+[KMB]?)\s*(?:reactions?|likes?)\b", metrics_text)
                        if not like_m:
                            like_m = re.search(r"(?i)\b(?:reactions?|likes?)\s*([\d,.]+[KMB]?)", metrics_text)

                        comment_m = re.search(r"(?i)([\d,.]+[KMB]?)\s*(?:comments?)\b", metrics_text)
                        if not comment_m:
                            comment_m = re.search(r"(?i)\b(?:comments?)\s*([\d,.]+[KMB]?)", metrics_text)

                        share_m = re.search(r"(?i)([\d,.]+[KMB]?)\s*(?:shares?)\b", metrics_text)
                        if not share_m:
                            share_m = re.search(r"(?i)\b(?:shares?)\s*([\d,.]+[KMB]?)", metrics_text)
                        if like_m:
                            post_likes = _parse_count(like_m.group(1))
                            post_reactions = post_likes  # FB merges these
                        if comment_m:
                            post_comments = _parse_count(comment_m.group(1))
                        if share_m:
                            post_shares = _parse_count(share_m.group(1))
                    except Exception:
                        pass

                    # Try to get timestamp
                    created_at = None
                    try:
                        time_el = await container.query_selector(
                            "abbr[data-utime], time[datetime], "
                            "a[href*='/posts/'] span[id], "
                            "span[class*='timestampContent']"
                        )
                        if time_el:
                            dt_attr = await time_el.get_attribute("datetime")
                            utime = await time_el.get_attribute("data-utime")
                            if dt_attr:
                                created_at = dt_attr
                            elif utime:
                                from datetime import datetime as dt, timezone
                                created_at = dt.fromtimestamp(int(utime), tz=timezone.utc).isoformat()
                    except Exception:
                        pass

                    if desc or post_url or thumbnail:
                        posts.append(PostItem(
                            url=post_url,
                            thumbnail=thumbnail,
                            description=desc,
                            type=post_type,
                            likes=post_likes,
                            comments=post_comments,
                            shares=post_shares,
                            reactions=post_reactions,
                            created_at=created_at,
                        ))
                except Exception:
                    continue

            # If we got no meaningful data, try extracting from HTML source
            if not display_name and not followers and not posts:
                html_raw = await page.content()

                # Try og:title for name
                if not display_name:
                    og_title = _extract_meta(html_raw, "og:title")
                    if og_title:
                        display_name = og_title.split(" - ")[0].split(" | ")[0].strip()

                # Try og:image for avatar
                if not avatar:
                    avatar = _extract_meta(html_raw, "og:image")

                # Try extracting follower/like counts from raw HTML
                followers_m = re.search(r'"follower_count"\s*:\s*(\d+)', html_raw)
                likes_m = re.search(r'"page_likers"\s*:\s*\{[^}]*"global_likers_count"\s*:\s*(\d+)', html_raw)
                if not likes_m:
                    likes_m = re.search(r'"overall_star_rating_count"\s*:\s*(\d+)', html_raw)
                    # Try another pattern for likes
                    likes_m2 = re.search(r'"fan_count"\s*:\s*(\d+)', html_raw)
                    if likes_m2:
                        likes_m = likes_m2

                if followers_m:
                    followers = int(followers_m.group(1))
                if likes_m:
                    likes = int(likes_m.group(1))
                    fan_count = likes

                # Try category from JSON
                if not category:
                    cat_m = re.search(r'"category_name"\s*:\s*"([^"]+)"', html_raw)
                    if cat_m:
                        category = cat_m.group(1)

                # Try description
                if not description_text:
                    description_text = _extract_meta(html_raw, "description")
                    if not description_text:
                        description_text = _extract_meta(html_raw, "og:description")

            # If still no data at all, save debug screenshot and indicate blocked
            if not display_name and not followers and not posts:
                try:
                    screenshot_path = os.path.join("static", "uploads", f"debug_fb_{username}.png")
                    await page.screenshot(path=screenshot_path)
                    logger.info("FB debug screenshot saved: %s", screenshot_path)
                except Exception:
                    pass
                return ScrapeResult(
                    status="blocked_by_challenge",
                    platform="facebook",
                    username=username,
                    error_message="Facebook blocked scraping. The page may require login or be restricted.",
                )

            return ScrapeResult(
                status="success",
                platform="facebook",
                username=username,
                display_name=display_name or username,
                avatar=avatar,
                followers=followers,
                following=following,
                likes=likes,
                bio=bio,
                is_verified=is_verified,
                category=category,
                about=about_text,
                description=description_text,
                fan_count=fan_count,
                page_url=url,
                recent_posts=posts,
            )

        except Exception as e:
            logger.exception("Facebook scrape failed for %s", username)
            return ScrapeResult(
                status="error", platform="facebook", username=username,
                error_message=str(e)
            )
        finally:
            await browser.close()


def _extract_fb_stat(text: str, pattern: str) -> int | None:
    """Extract a stat from page text using regex."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return _parse_count(match.group(1))
    return None


def _normalize_fb_url(raw_url: str | None) -> str | None:
    """Normalize Facebook URLs and unwrap redirect links."""
    if not raw_url:
        return None

    url = raw_url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://www.facebook.com" + url

    if "l.facebook.com/l.php" in url:
        parsed = urlparse(url)
        target = parse_qs(parsed.query).get("u", [None])[0]
        if target:
            url = unquote(target)

    url = url.replace("https://m.facebook.com", "https://www.facebook.com")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None

    # story.php requires query params, keep them.
    if parsed.path.endswith("/story.php"):
        if parsed.query:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{parsed.query}"
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


async def _extract_fb_post_url(container) -> str | None:
    """Extract the most likely direct URL for a Facebook post/reel/photo/video."""
    link_elements = await container.query_selector_all("a[href]")
    candidates: list[str] = []
    for link in link_elements:
        href = await link.get_attribute("href")
        if not href:
            continue
        normalized = _normalize_fb_url(href)
        if not normalized:
            continue
        candidates.append(normalized)

    priority_tokens = [
        "/posts/",
        "/reel/",
        "/reels/",
        "/videos/",
        "/photos/",
        "/story.php",
        "/permalink/",
    ]

    for token in priority_tokens:
        for candidate in candidates:
            if token in candidate:
                return candidate

    return candidates[0] if candidates else None


async def _extract_fb_thumbnail(container) -> str | None:
    """Extract the best image candidate for a post container, skipping reactions/emoji/icons."""
    images = await container.query_selector_all("img[src], img[data-src], img[srcset]")
    best_src = None
    best_score = -10

    # Patterns that indicate reaction/emoji/icon images, NOT post content
    _SKIP_SRC_TOKENS = (
        "emoji", "reaction", "/rsrc.php", "/images/icons/",
        "static.xx.fbcdn.net", "/images/like", "/images/love",
        "/images/haha", "/images/wow", "/images/sad", "/images/angry",
        "data:image/svg", "/rsrc/", "/assets/",
    )

    for image in images:
        src = await image.get_attribute("src") or await image.get_attribute("data-src")
        if not src:
            srcset = await image.get_attribute("srcset")
            if srcset:
                srcset_parts = [p.strip() for p in srcset.split(",") if p.strip()]
                if srcset_parts:
                    src = srcset_parts[-1].split(" ")[0]
        if not src:
            continue

        src = src.replace("&amp;", "&")

        src_lower = src.lower()
        alt = (await image.get_attribute("alt") or "").lower()
        width_attr = await image.get_attribute("width")
        height_attr = await image.get_attribute("height")

        # Skip profile/avatar images
        if "profile" in alt or "avatar" in alt:
            continue

        # Skip reaction emoji, icons, and static assets
        if src_lower.startswith("data:") or src_lower.startswith("blob:"):
            continue

        if any(token in src_lower for token in _SKIP_SRC_TOKENS):
            continue

        # Skip tiny inline images (reactions are typically 18x18 or 16x16)
        try:
            width = int(width_attr) if width_attr else 0
            height = int(height_attr) if height_attr else 0
        except ValueError:
            width = height = 0

        if width and height and (width < 100 or height < 100):
            continue

        # Also check element bounding box for actual rendered size
        try:
            box = await image.bounding_box()
            if box and (box["width"] < 100 or box["height"] < 100):
                continue
        except Exception:
            pass

        # Score remaining candidates
        score = 0
        if "scontent" in src_lower:
            score += 5
        if "fbcdn" in src_lower and "static" not in src_lower:
            score += 3

        if width >= 300 and height >= 300:
            score += 4
        elif width >= 180 and height >= 180:
            score += 2

        if score > best_score:
            best_score = score
            best_src = src

    return best_src


async def _extract_fb_bg_image(container) -> str | None:
    """Extract background-image URL from divs inside a Facebook post container."""
    try:
        divs = await container.query_selector_all("div[style*='background-image']")
        for div in divs:
            style = await div.get_attribute("style")
            if not style:
                continue
            match = re.search(r"background-image:\s*url\(['\"]?([^'\")\s]+)['\"]?\)", style)
            if match:
                url = match.group(1)
                if "scontent" in url or "fbcdn" in url:
                    # Verify size
                    try:
                        box = await div.bounding_box()
                        if box and box["width"] >= 100 and box["height"] >= 100:
                            return url
                    except Exception:
                        return url
    except Exception:
        pass
    return None


# ─── Helper Functions ────────────────────────────────────────────────────────

async def _safe_text(page, selector: str) -> str | None:
    """Safely get text from first matching element."""
    try:
        el = await page.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()
    except Exception:
        pass
    return None


async def _safe_attr(page, selector: str, attr: str) -> str | None:
    """Safely get attribute from first matching element."""
    try:
        el = await page.query_selector(selector)
        if el:
            return await el.get_attribute(attr)
    except Exception:
        pass
    return None


# ─── Main Entry Point ────────────────────────────────────────────────────────

async def manual_scrape(platform: str, username: str) -> ScrapeResult:
    """
    Route to the appropriate platform scraper.

    Args:
        platform: One of 'tiktok', 'instagram', 'facebook'
        username: Username or handle (@ prefix is stripped automatically)
    """
    # Clean username - strip @ and extract from URL if needed
    username = username.strip().lstrip("@")

    # Handle full URLs
    url_patterns = {
        "tiktok": r"tiktok\.com/@?([\w.]+)",
        "instagram": r"instagram\.com/([\w.]+)",
        "facebook": r"facebook\.com/([\w.]+)",
    }
    if "/" in username:
        pattern = url_patterns.get(platform)
        if pattern:
            match = re.search(pattern, username)
            if match:
                username = match.group(1)

    # Remove trailing slashes or query params
    username = username.split("?")[0].rstrip("/")

    if not username:
        return ScrapeResult(
            status="error", platform=platform, username="",
            error_message="Username is required."
        )

    platform = platform.lower()

    # On Windows, always run Playwright in a separate thread with Proactor loop
    # to prevent "Task exception was never retrieved" from selector-based loops.
    if sys.platform.startswith("win"):
        return await _manual_scrape_thread_fallback(platform, username)

    try:
        if platform == "tiktok":
            return await _scrape_tiktok(username)
        elif platform == "instagram":
            return await _scrape_instagram(username)
        elif platform == "facebook":
            return await _scrape_facebook(username)
        else:
            return ScrapeResult(
                status="error", platform=platform, username=username,
                error_message=f"Unsupported platform: {platform}"
            )
    except NotImplementedError:
        # Fallback for Windows/selector-loop environments: run scraper in a
        # dedicated thread with a fresh Proactor loop.
        return await _manual_scrape_thread_fallback(platform, username)
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "Please run the following command" in msg:
            msg = "Playwright browser is not installed. Run: python -m playwright install chromium"
        return ScrapeResult(
            status="error",
            platform=platform,
            username=username,
            error_message=msg,
        )


async def _manual_scrape_thread_fallback(platform: str, username: str) -> ScrapeResult:
    """Run Playwright scraping in a separate thread using a Proactor loop."""

    def _runner() -> ScrapeResult:
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        if platform == "tiktok":
            return asyncio.run(_scrape_tiktok(username))
        if platform == "instagram":
            return asyncio.run(_scrape_instagram(username))
        if platform == "facebook":
            return asyncio.run(_scrape_facebook(username))

        return ScrapeResult(
            status="error",
            platform=platform,
            username=username,
            error_message=f"Unsupported platform: {platform}",
        )

    try:
        return await asyncio.to_thread(_runner)
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" in msg or "Please run the following command" in msg:
            msg = "Playwright browser is not installed. Run: python -m playwright install chromium"
        return ScrapeResult(
            status="error",
            platform=platform,
            username=username,
            error_message=msg,
        )
