"""
Snapchat-specific FastAPI router.

Handles OAuth flow, token refresh, Marketing API data fetching,
and paid ad creation – all separated from the main Meta routes.
"""

import os
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Form, File, UploadFile, Request
from fastapi.responses import RedirectResponse

from database import save_account, get_account, update_account_tokens
from services.snapchat_service import (
    get_snap_auth_url,
    exchange_code_for_tokens,
    refresh_access_token,
    get_authenticated_user,
)
from connectors.snapchat import SnapchatConnector
from schemas.snapchat import (
    SnapAdCreate,
    SnapCampaignCreate,
    SnapAdSquadCreate,
)

router = APIRouter(prefix="/snap", tags=["snapchat"])

_connector = SnapchatConnector()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
SNAP_REDIRECT_URI = os.getenv("SNAP_REDIRECT_URI", f"{PUBLIC_BACKEND_URL}/snap/auth/callback")


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/auth/login")
def snap_login():
    """Redirect user to Snapchat's OAuth2 consent screen."""
    url = get_snap_auth_url(redirect_uri=SNAP_REDIRECT_URI)
    return RedirectResponse(url)


@router.get("/auth/callback")
async def snap_callback(code: str = Query(...)):
    """
    Handle Snapchat OAuth2 callback:
    1. Exchange code → access_token + refresh_token
    2. Fetch user info & organizations
    3. Discover ad accounts and persist them
    """
    token_data = await exchange_code_for_tokens(code, SNAP_REDIRECT_URI)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    # Fetch user & org info
    user_info = await get_authenticated_user(access_token)
    org_id = user_info.get("organization_id")

    # Discover ad accounts under the organization
    if org_id:
        ad_accounts = await _connector.get_ad_accounts(org_id, access_token)
        for acct in ad_accounts:
            save_account(
                account_id=acct["id"],
                account_type="snapchat",
                name=acct.get("name", "Snap Ad Account"),
                access_token=access_token,
                refresh_token=refresh_token,
                org_id=org_id,
            )
    else:
        # No org found – store user-level entry so we still have the token
        save_account(
            account_id=user_info.get("id", "snap_user"),
            account_type="snapchat",
            name=user_info.get("display_name", "Snapchat User"),
            access_token=access_token,
            refresh_token=refresh_token,
        )

    return RedirectResponse(f"{FRONTEND_URL}?connected=true&platform=snapchat")


@router.post("/auth/refresh")
async def snap_refresh_token(account_id: str = Form(...)):
    """
    Manually trigger a token refresh for a Snapchat account.
    Useful when the frontend detects a 401 from the API.
    """
    account = get_account(account_id)
    if not account or account["type"] != "snapchat":
        raise HTTPException(404, "Snapchat account not found")

    stored_refresh = account.get("refresh_token")
    if not stored_refresh:
        raise HTTPException(400, "No refresh token stored for this account")

    token_data = await refresh_access_token(stored_refresh)
    new_access = token_data["access_token"]
    new_refresh = token_data.get("refresh_token", stored_refresh)

    update_account_tokens(account_id, new_access, new_refresh)

    return {"status": "ok", "message": "Token refreshed successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# Data Fetching – Organizations / Ad Accounts / Campaigns / Ad Squads
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/organizations")
async def list_organizations(account_id: str = Query(...)):
    """Fetch all Snapchat organizations visible to this account's token."""
    account = _get_snap_account(account_id)
    return await _connector.get_organizations(account["access_token"])


@router.get("/adaccounts")
async def list_ad_accounts(account_id: str = Query(...), org_id: str = Query(...)):
    """Fetch ad accounts under a Snapchat organization."""
    account = _get_snap_account(account_id)
    return await _connector.get_ad_accounts(org_id, account["access_token"])


@router.get("/campaigns")
async def list_campaigns(account_id: str = Query(...)):
    """Fetch campaigns under a Snapchat ad account."""
    account = _get_snap_account(account_id)
    return await _connector.get_campaigns(account_id, account["access_token"])


@router.get("/adsquads")
async def list_ad_squads(campaign_id: str = Query(...), account_id: str = Query(...)):
    """Fetch ad squads under a Snapchat campaign."""
    account = _get_snap_account(account_id)
    return await _connector.get_ad_squads(campaign_id, account["access_token"])


@router.get("/insights")
async def snap_insights(account_id: str = Query(...)):
    """Fetch ad-level performance insights for a Snapchat ad account."""
    account = _get_snap_account(account_id)
    return await _connector.get_insights(account_id, account["access_token"])


# ═══════════════════════════════════════════════════════════════════════════════
# Paid Ad Creation
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/ads/create")
async def create_snap_ad(
    request: Request,
    account_id: str = Form(...),
    campaign_id: str = Form(...),
    message: str = Form(...),
    images: List[UploadFile] = File(default=[]),
):
    """
    Full paid ad creation pipeline:
    Upload media → Create Creative → Create Ad Squad → Create Ad
    """
    account = _get_snap_account(account_id)
    base_url = os.getenv("PUBLIC_BACKEND_URL") or str(request.base_url)
    return await _connector.publish_post(
        account_id,
        account["access_token"],
        message,
        images,
        campaign_id=campaign_id,
        ad_account_id=account_id,
        base_url=base_url,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _get_snap_account(account_id: str) -> dict:
    account = get_account(account_id)
    if not account or account["type"] != "snapchat":
        raise HTTPException(404, "Snapchat account not found")
    return account
