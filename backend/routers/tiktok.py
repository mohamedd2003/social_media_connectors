"""
TikTok FastAPI Router

All /tiktok/* endpoints: OAuth flow, token management, profile analytics,
video listing, and video publishing.

Architecture:
  - Mock DB helpers (save_tiktok_tokens, get_tiktok_tokens) for token persistence
  - TikTokAPIService for all TikTok API calls
  - Clean error mapping: 401 (auth), 403 (scope), 429 (rate limit)

Endpoints:
  GET  /tiktok/auth/login          → Redirect to TikTok OAuth consent
  GET  /tiktok/auth/callback       → Handle OAuth callback, exchange code
  GET  /tiktok/profile/analytics   → Full profile + video analytics
  GET  /tiktok/videos              → List user's published videos
  POST /tiktok/videos/publish      → Publish video via public URL
  POST /tiktok/videos/publish/status → Check publish job status
  GET  /tiktok/accounts            → List connected TikTok accounts
  DELETE /tiktok/accounts/{id}     → Disconnect a TikTok account
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uuid

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse

from database import get_db, save_account, get_account
from schemas.tiktok import (
    TikTokProfileInsightsResponse,
    TikTokPublishRequest,
    TikTokPublishResponse,
    TikTokPublishStatusResponse,
    TikTokVideoItem,
)
from services.tiktok_api_service import TikTokAPIService

logger = logging.getLogger("tiktok.router")

router = APIRouter(prefix="/tiktok", tags=["tiktok"])
_service = TikTokAPIService()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ═══════════════════════════════════════════════════════════════════════════════
# Mock DB Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _get_tiktok_redirect_uri() -> str:
    """Load latest .env values and return the TikTok OAuth redirect URI."""
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
    public_backend_url = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
    return os.getenv("TIKTOK_REDIRECT_URI", f"{public_backend_url}/tiktok/auth/callback")


def save_tiktok_tokens(
    account_id: str,
    access_token: str,
    refresh_token: str = "",
    name: str = "TikTok User",
    open_id: str = "",
) -> None:
    """
    Persist TikTok OAuth tokens to the database.

    Uses the shared accounts table with type='tiktok'.
    The open_id is stored in the org_id column for convenience.
    """
    save_account(
        account_id=account_id,
        account_type="tiktok",
        name=name,
        access_token=access_token,
        refresh_token=refresh_token,
        org_id=open_id,  # Reuse org_id column for TikTok open_id
    )
    logger.info("Saved TikTok tokens for account %s (open_id=%s)", account_id, open_id)


def get_tiktok_tokens(account_id: str) -> dict | None:
    """
    Retrieve stored TikTok tokens from the database.

    Returns dict with access_token, refresh_token, open_id or None if not found.
    """
    account = get_account(account_id)
    if not account or account.get("type") != "tiktok":
        return None
    return {
        "access_token": account["access_token"],
        "refresh_token": account.get("refresh_token", ""),
        "open_id": account.get("org_id", ""),  # We stored open_id in org_id
        "name": account.get("name", ""),
    }


def _require_tiktok_account(account_id: str) -> dict:
    """Load and validate a TikTok account from the DB, or raise 404."""
    tokens = get_tiktok_tokens(account_id)
    if not tokens:
        raise HTTPException(404, f"TikTok account '{account_id}' not found. Connect via /tiktok/auth/login.")
    return tokens


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0 Flow
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/auth/login")
def tiktok_login():
    """
    Step 1: Redirect user to TikTok's OAuth2 consent screen.

    GET /tiktok/auth/login → 302 → www.tiktok.com/v2/auth/authorize/
    """
    redirect_uri = _get_tiktok_redirect_uri()
    url = _service.get_auth_url(redirect_uri=redirect_uri)
    return RedirectResponse(url)


@router.get("/auth/callback")
async def tiktok_callback(code: str = Query(...), state: str = Query(default="")):
    """
    Step 2: Handle OAuth2 callback from TikTok.

    1. Exchange authorization code → access_token + refresh_token + open_id
    2. Fetch user profile info (display_name, avatar)
    3. Save tokens to DB
    4. Redirect to frontend with success indicator

    GET /tiktok/auth/callback?code=xxx&state=tiktok_oauth
    """
    redirect_uri = _get_tiktok_redirect_uri()

    # ── Exchange code for tokens ──
    token_data = await _service.get_tokens(code, redirect_uri)
    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    open_id = token_data.get("open_id", "")

    if not access_token:
        raise HTTPException(400, "TikTok token exchange returned no access_token.")

    # ── Fetch user profile for display name ──
    try:
        profile = await _service.fetch_user_info(access_token)
        display_name = profile.display_name or "TikTok User"
        account_id = open_id or "tiktok_user"
    except Exception as e:
        logger.warning("Could not fetch TikTok profile after auth: %s", e)
        display_name = "TikTok User"
        account_id = open_id or "tiktok_user"

    # ── Save tokens ──
    save_tiktok_tokens(
        account_id=account_id,
        access_token=access_token,
        refresh_token=refresh_token,
        name=display_name,
        open_id=open_id,
    )

    logger.info("TikTok OAuth complete: account=%s, name=%s", account_id, display_name)

    # ── Redirect to frontend ──
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(f"{frontend_url}/?connected=true&platform=tiktok")


# ═══════════════════════════════════════════════════════════════════════════════
# Profile Analytics
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/profile/analytics", response_model=TikTokProfileInsightsResponse)
async def tiktok_profile_analytics(account_id: str = Query(...)):
    """
    Fetch full TikTok profile analytics: user info + video metrics.

    GET /tiktok/profile/analytics?account_id=xxx

    Returns profile details, aggregate metrics (followers, views, engagement),
    and a list of recent videos with per-video stats.
    """
    tokens = _require_tiktok_account(account_id)
    return await _service.fetch_profile_analytics(tokens["access_token"])


# ═══════════════════════════════════════════════════════════════════════════════
# Video List
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/videos", response_model=list[TikTokVideoItem])
async def tiktok_videos(
    account_id: str = Query(...),
    max_count: int = Query(default=20, le=20),
):
    """
    List the user's published TikTok videos with metrics.

    GET /tiktok/videos?account_id=xxx&max_count=20
    """
    tokens = _require_tiktok_account(account_id)
    return await _service.fetch_video_list(tokens["access_token"], max_count=max_count)


# ═══════════════════════════════════════════════════════════════════════════════
# Video Publishing
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/videos/upload")
async def tiktok_upload_video(file: UploadFile = File(...)):
    """
    Upload a local video file and return a publicly accessible URL.

    POST /tiktok/videos/upload  (multipart/form-data with 'file' field)

    Saves the file to static/uploads/ and returns the public URL
    that TikTok can download from.
    """
    # Validate file type
    allowed = {".mp4", ".mov", ".avi", ".webm"}
    ext = Path(file.filename).suffix.lower() if file.filename else ".mp4"
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported video format '{ext}'. Allowed: {', '.join(allowed)}")

    # Generate unique filename to avoid collisions
    unique_name = f"{uuid.uuid4().hex}{ext}"
    upload_dir = Path(__file__).resolve().parent.parent / "static" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / unique_name

    # Stream file to disk
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Build public URL using the tunnel/public backend URL
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
    public_url = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
    video_url = f"{public_url}/static/uploads/{unique_name}"

    logger.info("Uploaded video: %s → %s", file.filename, video_url)
    return {"video_url": video_url, "filename": unique_name}


@router.post("/videos/publish", response_model=TikTokPublishResponse)
async def tiktok_publish_video(
    account_id: str = Query(...),
    body: TikTokPublishRequest = ...,
):
    """
    Publish a video to TikTok using the Direct Post (URL) method.

    POST /tiktok/videos/publish?account_id=xxx
    Body: { "title": "...", "video_url": "https://...", "privacy_level": "PUBLIC_TO_EVERYONE" }

    The video_url must be a publicly accessible URL (e.g., S3 presigned URL).
    TikTok will download the video from this URL and process it.
    """
    tokens = _require_tiktok_account(account_id)
    return await _service.publish_video(
        access_token=tokens["access_token"],
        title=body.title,
        video_url=body.video_url,
        privacy_level=body.privacy_level.value,
        disable_duet=body.disable_duet,
        disable_stitch=body.disable_stitch,
        disable_comment=body.disable_comment,
    )


@router.post("/videos/publish/status", response_model=TikTokPublishStatusResponse)
async def tiktok_publish_status(
    account_id: str = Query(...),
    publish_id: str = Query(...),
):
    """
    Check the status of a TikTok video publish job.

    POST /tiktok/videos/publish/status?account_id=xxx&publish_id=yyy
    """
    tokens = _require_tiktok_account(account_id)
    return await _service.check_publish_status(
        access_token=tokens["access_token"],
        publish_id=publish_id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Account Management
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/accounts")
def tiktok_accounts():
    """
    List all connected TikTok accounts.

    GET /tiktok/accounts
    """
    conn = get_db()
    rows = conn.execute("SELECT id, name, type FROM accounts WHERE type = 'tiktok'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.delete("/accounts/{account_id}")
def tiktok_disconnect(account_id: str):
    """
    Disconnect (remove) a TikTok account.

    DELETE /tiktok/accounts/{account_id}
    """
    existing = get_tiktok_tokens(account_id)
    if not existing:
        raise HTTPException(404, f"TikTok account '{account_id}' not found.")

    conn = get_db()
    conn.execute("DELETE FROM accounts WHERE id = ? AND type = 'tiktok'", (account_id,))
    conn.commit()
    conn.close()

    logger.info("Disconnected TikTok account: %s", account_id)
    return {"status": "disconnected", "account_id": account_id}
