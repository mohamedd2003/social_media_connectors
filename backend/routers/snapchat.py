"""
Snapchat FastAPI Router

All /snap/* endpoints: OAuth flow, token management, data fetching,
profile overview, and ad creation.

Architecture:
- _get_snap_account()  : Dependency helper — loads & validates account from DB
- _handle_dns_error()  : Translates DNS/network errors to clear 502 responses
- ensure_fresh_token() : Called before API operations to auto-refresh tokens
- SnapchatConnector    : All HTTP calls to adsapi.snapchat.com
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse

from connectors.snapchat import SnapchatConnector
from database import get_account, get_manual_metrics, save_account, save_manual_metrics, update_account_tokens
from schemas.snapchat import (
    SnapAdCreate,
    SnapAdSquadCreate,
    SnapCampaignCreate,
    SnapProfileOverview,
)
from services.snapchat_service import (
    ensure_fresh_token,
    exchange_code_for_tokens,
    get_authenticated_user,
    get_snap_auth_url,
    refresh_access_token,
    save_tokens_to_db,
)

logger = logging.getLogger("snapchat.router")

router = APIRouter(prefix="/snap", tags=["snapchat"])
_connector = SnapchatConnector()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _get_snap_redirect_uri() -> str:
    """Load latest .env values and return the Snapchat OAuth redirect URI."""
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)
    public_backend_url = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
    return os.getenv("SNAP_REDIRECT_URI", f"{public_backend_url}/snap/auth/callback")


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0 Flow
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/auth/login")
def snap_login():
    """
    Step 1: Redirect user to Snapchat's OAuth2 consent screen.

    GET /snap/auth/login → 302 → accounts.snapchat.com/login/oauth2/authorize
    """
    url = get_snap_auth_url(redirect_uri=_get_snap_redirect_uri())
    return RedirectResponse(url)


@router.get("/auth/callback")
async def snap_callback(code: str = Query(...)):
    """
    Step 2: Handle OAuth2 callback.

    1. Exchange authorization code → access_token + refresh_token
    2. Save tokens immediately (never lose them)
    3. Best-effort: fetch /me, discover org & ad accounts
    """
    # ── Token exchange (accounts.snapchat.com — always reachable) ──
    token_data = await exchange_code_for_tokens(code, _get_snap_redirect_uri())
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    # ── Save placeholder so tokens are never lost ──
    save_tokens_to_db(
        account_id="snap_pending",
        access_token=access_token,
        refresh_token=refresh_token,
        name="Snapchat (connecting...)",
    )

    # ── Best-effort: discover user & ad accounts (may fail if DNS blocked) ──
    try:
        user_info = await get_authenticated_user(access_token)
        org_id = user_info.get("organization_id")
        user_id = user_info.get("id") or "snap_user"
        user_name = user_info.get("display_name") or "Snapchat User"

        # Remove placeholder
        from database import get_db
        conn = get_db()
        conn.execute("DELETE FROM accounts WHERE id = 'snap_pending'")
        conn.commit()
        conn.close()

        if org_id:
            ad_accounts = await _connector.get_ad_accounts(org_id, access_token)
            if ad_accounts:
                for acct in ad_accounts:
                    save_tokens_to_db(
                        account_id=acct["id"],
                        access_token=access_token,
                        refresh_token=refresh_token,
                        name=acct.get("name", "Snap Ad Account"),
                        org_id=org_id,
                    )
            else:
                save_tokens_to_db(
                    account_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    name=user_name,
                    org_id=org_id,
                )
        else:
            save_tokens_to_db(
                account_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                name=user_name,
            )
    except Exception as exc:
        logger.warning("OAuth callback: API discovery failed: %s", exc)
        from database import get_db
        conn = get_db()
        conn.execute(
            "UPDATE accounts SET name = ? WHERE id = 'snap_pending'",
            ("Snapchat (API unreachable – check DNS)",),
        )
        conn.commit()
        conn.close()

    return RedirectResponse(f"{FRONTEND_URL}?connected=true&platform=snapchat")


@router.post("/discover")
async def snap_discover(account_id: str = Form(...)):
    """Retry ad account discovery after fixing DNS."""
    account = _get_snap_account(account_id)
    access_token = account["access_token"]

    user_info = await get_authenticated_user(access_token)
    org_id = user_info.get("organization_id")
    user_id = user_info.get("id") or account_id
    user_name = user_info.get("display_name") or "Snapchat User"

    discovered: list[str] = []
    if org_id:
        ad_accounts = await _connector.get_ad_accounts(org_id, access_token)
        for acct in ad_accounts:
            save_tokens_to_db(
                account_id=acct["id"],
                access_token=access_token,
                refresh_token=account.get("refresh_token", ""),
                name=acct.get("name", "Snap Ad Account"),
                org_id=org_id,
            )
            discovered.append(acct["id"])

    if account_id == "snap_pending":
        from database import get_db
        conn = get_db()
        conn.execute("DELETE FROM accounts WHERE id = 'snap_pending'")
        conn.commit()
        conn.close()
        if not discovered:
            save_tokens_to_db(
                account_id=user_id,
                access_token=access_token,
                refresh_token=account.get("refresh_token", ""),
                name=user_name,
                org_id=org_id,
            )

    return {"status": "ok", "discovered": len(discovered), "accounts": discovered}


@router.post("/auth/refresh")
async def snap_refresh_token(account_id: str = Form(...)):
    """Manually trigger token refresh for a Snapchat account."""
    account = _get_snap_account(account_id)
    stored_refresh = account.get("refresh_token")
    if not stored_refresh:
        raise HTTPException(400, "No refresh token stored for this account")

    token_data = await refresh_access_token(stored_refresh)
    update_account_tokens(
        account_id,
        token_data["access_token"],
        token_data.get("refresh_token", stored_refresh),
    )
    return {"status": "ok", "message": "Token refreshed successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# Data Fetching – Organizations / Ad Accounts / Campaigns / Ad Squads
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/organizations")
async def list_organizations(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_organizations(account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/adaccounts")
async def list_ad_accounts(account_id: str = Query(...), org_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_ad_accounts(org_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/campaigns")
async def list_campaigns(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_campaigns(account_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/adsquads")
async def list_ad_squads(campaign_id: str = Query(...), account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_ad_squads(campaign_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/insights")
async def snap_insights(account_id: str = Query(...)):
    """
    GET /snap/insights?account_id=...

    Fetches ad-level performance stats from the Snapchat Marketing API.
    Walks: ad_account → campaigns → ad_squads → ads → /ads/{id}/stats
    """
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_insights(account_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Organic Stories (Ad Account Media)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/stories")
async def list_stories(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    org_id = _get_org_id(account)
    try:
        return await _connector.get_stories(org_id, account_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.post("/stories/create")
async def create_story(
    account_id: str = Form(...),
    caption: str = Form(""),
    image: UploadFile = File(...),
):
    account = _get_snap_account(account_id)
    org_id = _get_org_id(account)
    image_data = await image.read()
    try:
        return await _connector.create_story(
            org_id, account_id, account["access_token"],
            caption=caption or image.filename,
            image_data=image_data,
            filename=image.filename,
            content_type=image.content_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.delete("/media/{media_id}")
async def delete_media(media_id: str, account_id: str = Query(...)):
    """Delete a media entity (saved story) from the ad account."""
    account = _get_snap_account(account_id)
    try:
        return await _connector.delete_media(media_id, account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile – Dashboard Overview (aggregated)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/profile/overview", response_model=SnapProfileOverview)
async def profile_overview(account_id: str = Query(...)):
    """
    Aggregated dashboard endpoint matching Snapchat Creator Portal.

    Returns: profile details, overview metrics (followers/reach/views),
    public stories, saved stories (ad media), spotlight, campaign count.

    Endpoints used internally:
    - GET /v1/me                                    → user info
    - GET /v1/organizations/{org_id}                → org name
    - GET /v1/organizations/{org_id}/public_profiles → profile check
    - GET /v1/profiles/{profile_id}/stats           → metrics
    - GET /v1/profiles/{profile_id}/stories         → public stories
    - GET /v1/profiles/{profile_id}/spotlights      → spotlight
    - GET /v1/adaccounts/{id}/media                 → saved stories
    - GET /v1/adaccounts/{id}/campaigns             → campaign count
    """
    account = _get_snap_account(account_id)
    org_id = _get_org_id(account)
    try:
        me_info = await get_authenticated_user(account["access_token"])
        return await _connector.get_profile_overview(
            org_id, account_id, account["access_token"], me_info,
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Manual Metrics (backend-persisted fallback for gRPC-blocked stats)
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/manual-metrics")
async def get_metrics(account_id: str = Query(...)):
    """Get stored manual metrics for a Snapchat account."""
    _get_snap_account(account_id)  # validate account exists
    return get_manual_metrics(account_id)


@router.put("/manual-metrics")
async def put_metrics(
    account_id: str = Query(...),
    followers: int = Query(default=0, ge=0),
    reach: int = Query(default=0, ge=0),
    views: int = Query(default=0, ge=0),
):
    """Save manual metrics for a Snapchat account (persisted in DB)."""
    _get_snap_account(account_id)  # validate account exists
    save_manual_metrics(account_id, followers, reach, views)
    return get_manual_metrics(account_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Public Profile – Individual Endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/profile/stories")
async def profile_stories(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_profile_stories(_get_org_id(account), account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.post("/profile/stories/create")
async def profile_story_create(
    account_id: str = Form(...),
    caption: str = Form(""),
    file: UploadFile = File(...),
):
    """Post story with fallback to ad-account media when profile API is unavailable."""
    account = _get_snap_account(account_id)
    org_id = _get_org_id(account)
    data = await file.read()
    try:
        # Try posting to Public Profile first
        from connectors.snapchat import SnapchatConnector as SC
        profiles = await _connector.get_public_profiles(org_id, account["access_token"])
        if profiles:
            # Use the profile posting flow
            pass  # Falls through to create_story which handles both paths
        return await _connector.create_story(
            org_id, account_id, account["access_token"],
            caption=caption or file.filename,
            image_data=data,
            filename=file.filename,
            content_type=file.content_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/profile/spotlight")
async def profile_spotlight(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_profile_spotlight(_get_org_id(account), account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/profile/promotions")
async def profile_promotions(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_profile_promotions(
            _get_org_id(account), account_id, account["access_token"],
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.get("/profile/insights")
async def profile_insights(account_id: str = Query(...)):
    account = _get_snap_account(account_id)
    try:
        return await _connector.get_profile_insights(_get_org_id(account), account["access_token"])
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Paid Ad Creation
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/campaigns/create")
async def create_campaign(
    account_id: str = Form(...),
    name: str = Form(...),
    daily_budget: float = Form(20.0),
    status: str = Form("PAUSED"),
):
    account = _get_snap_account(account_id)
    try:
        return await _connector.create_campaign(
            account_id, account["access_token"],
            name=name, status=status,
            daily_budget_micro=int(daily_budget * 1_000_000),
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


@router.post("/ads/create")
async def create_snap_ad(
    request: Request,
    account_id: str = Form(...),
    campaign_id: str = Form(...),
    message: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    """Full paid ad creation: media → creative → ad squad → ad"""
    account = _get_snap_account(account_id)
    base_url = os.getenv("PUBLIC_BACKEND_URL") or str(request.base_url)
    try:
        return await _connector.publish_post(
            account_id, account["access_token"], message, images,
            campaign_id=campaign_id, ad_account_id=account_id, base_url=base_url,
        )
    except HTTPException:
        raise
    except Exception as e:
        _handle_dns_error(e)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _get_snap_account(account_id: str) -> dict:
    """Load a Snapchat account from DB or raise 404."""
    account = get_account(account_id)
    if not account or account["type"] != "snapchat":
        raise HTTPException(404, "Snapchat account not found")
    return account


def _get_org_id(account: dict) -> str:
    """Extract org_id from account or raise 400."""
    org_id = account.get("org_id")
    if not org_id:
        raise HTTPException(400, "No organization linked. Try re-connecting.")
    return org_id


def _handle_dns_error(e: Exception) -> None:
    """Translate DNS/network errors to a clear 502 response."""
    msg = str(e)
    if "getaddrinfo" in msg or "ConnectError" in msg or "NameResolutionError" in msg:
        raise HTTPException(
            502,
            "DNS lookup failed for adsapi.snapchat.com. "
            "Disable DNS/ad-block filtering or switch DNS to 8.8.8.8 / 1.1.1.1, then retry.",
        )
    raise HTTPException(500, f"Snapchat API error: {msg}")
