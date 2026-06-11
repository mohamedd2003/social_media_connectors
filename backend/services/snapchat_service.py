"""
Snapchat OAuth 2.0 & Token Management Service

Handles:
- Building the authorization URL with correct scopes
- Exchanging authorization codes for access + refresh tokens
- Automatic token refresh (Snapchat access tokens expire every 30 min)
- Fetching authenticated user info from /me
- Database CRUD stubs for token persistence

All HTTP calls use async httpx for non-blocking operation.
"""

from __future__ import annotations

import logging
import os
from base64 import b64encode
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from database import get_account, save_account, update_account_tokens

logger = logging.getLogger("snapchat.service")

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration (loaded from environment)
# ═══════════════════════════════════════════════════════════════════════════════

SNAP_AUTH_URL = "https://accounts.snapchat.com/login/oauth2/authorize"
SNAP_TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"


def _get_snap_credentials() -> tuple[str, str]:
    """Read SNAP_CLIENT_ID and SNAP_CLIENT_SECRET from environment."""
    client_id = os.getenv("SNAP_CLIENT_ID")
    client_secret = os.getenv("SNAP_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(500, "Snapchat credentials not configured in .env")
    return client_id, client_secret


def _get_basic_auth_header() -> str:
    """Snapchat uses HTTP Basic Auth (client_id:client_secret) for token endpoints."""
    client_id, client_secret = _get_snap_credentials()
    return b64encode(f"{client_id}:{client_secret}".encode()).decode()


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0 – Authorization URL
# ═══════════════════════════════════════════════════════════════════════════════


def get_snap_auth_url(redirect_uri: str, state: Optional[str] = None) -> str:
    """
    Build the Snapchat OAuth2 authorization URL.

    Scopes:
    - snapchat-marketing-api : Ads API (orgs, ad accounts, campaigns, stats).
    - snapchat-profile-api   : Public Profile endpoints (stories, spotlight,
      followers, reach).

    Both scopes are sent in the OAuth flow via SNAP_OAUTH_SCOPE env var.
    """
    client_id, _ = _get_snap_credentials()
    scope = os.getenv("SNAP_OAUTH_SCOPE", "snapchat-marketing-api")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
    }
    if state:
        params["state"] = state
    return f"{SNAP_AUTH_URL}?{urlencode(params)}"


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0 – Token Exchange
# ═══════════════════════════════════════════════════════════════════════════════


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """
    Exchange the authorization code for access + refresh tokens.

    POST https://accounts.snapchat.com/login/oauth2/access_token
    Authorization: Basic base64(client_id:client_secret)
    Content-Type: application/x-www-form-urlencoded

    Returns dict with: access_token, refresh_token, token_type, expires_in, scope
    """
    basic = _get_basic_auth_header()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SNAP_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        if resp.status_code != 200:
            logger.error("Token exchange failed: %s", resp.text)
            raise HTTPException(400, f"Snapchat token exchange failed: {resp.text}")
        return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# OAuth 2.0 – Token Refresh
# ═══════════════════════════════════════════════════════════════════════════════


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh a Snapchat access token using the refresh token.

    Access tokens expire in ~30 minutes; refresh tokens last much longer.
    Returns dict with: access_token, refresh_token (rotated), expires_in
    """
    basic = _get_basic_auth_header()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            SNAP_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if resp.status_code != 200:
            logger.error("Token refresh failed: %s", resp.text)
            raise HTTPException(400, f"Snapchat token refresh failed: {resp.text}")
        return resp.json()


async def ensure_fresh_token(account_id: str) -> str:
    """
    Proactively refresh the access token for a stored account.

    Snapchat access tokens expire every 30 minutes. Rather than checking
    expiry time (which Snapchat doesn't store reliably), we always refresh
    before making API calls if a refresh_token is available.

    This is the recommended dependency helper — call it before any API call:
        token = await ensure_fresh_token(account_id)

    Returns the (possibly refreshed) access_token.
    Persists the new tokens in the database.
    """
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Snapchat account not found")

    stored_refresh = account.get("refresh_token")
    if not stored_refresh:
        # No refresh token — return existing access token as-is
        return account["access_token"]

    try:
        token_data = await refresh_access_token(stored_refresh)
        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", stored_refresh)
        # Persist the rotated tokens
        update_account_tokens(account_id, new_access, new_refresh)
        logger.info("Token refreshed for account %s", account_id)
        return new_access
    except HTTPException:
        # Refresh failed — token may still be valid for a few more minutes
        logger.warning("Token refresh failed for %s, using existing token", account_id)
        return account["access_token"]


# ═══════════════════════════════════════════════════════════════════════════════
# Authenticated User Info
# ═══════════════════════════════════════════════════════════════════════════════


async def get_authenticated_user(access_token: str) -> dict:
    """
    Fetch the authenticated user's info from Snapchat /me endpoint.

    GET https://adsapi.snapchat.com/v1/me
    Authorization: Bearer <access_token>

    Returns dict with: id, display_name, email, organization_id
    """
    from connectors.snapchat import _ensure_dns, _api, _make_headers, _snap_verify

    await _ensure_dns()
    async with httpx.AsyncClient(timeout=30.0, verify=_snap_verify) as client:
        resp = await client.get(
            _api("/me"),
            headers=_make_headers(access_token),
        )
        if resp.status_code != 200:
            raise HTTPException(400, f"Failed to fetch Snap user: {resp.text}")
        me = resp.json().get("me", {})
        return {
            "id": me.get("id"),
            "display_name": me.get("display_name"),
            "email": me.get("email"),
            "organization_id": me.get("organization_id"),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Database CRUD Stubs
# ═══════════════════════════════════════════════════════════════════════════════
# These wrap the existing database.py functions to provide a clean API
# that can be swapped to any ORM/database (SQLAlchemy, MongoDB, etc.)


def save_tokens_to_db(
    account_id: str,
    access_token: str,
    refresh_token: str,
    name: str = "Snapchat User",
    org_id: Optional[str] = None,
) -> None:
    """Persist Snapchat OAuth tokens to the database."""
    save_account(
        account_id=account_id,
        account_type="snapchat",
        name=name,
        access_token=access_token,
        refresh_token=refresh_token,
        org_id=org_id,
    )


def get_tokens_from_db(account_id: str) -> Optional[dict]:
    """Retrieve stored tokens for a Snapchat account. Returns None if not found."""
    account = get_account(account_id)
    if not account or account.get("type") != "snapchat":
        return None
    return {
        "id": account["id"],
        "access_token": account["access_token"],
        "refresh_token": account.get("refresh_token", ""),
        "org_id": account.get("org_id"),
        "name": account.get("name", ""),
    }
