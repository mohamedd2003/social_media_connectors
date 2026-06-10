"""
Snapchat OAuth2 & Marketing API service layer.

Handles token exchange, refresh, and high-level business operations that
sit between the FastAPI router and the raw SnapchatConnector.
"""

import os
from base64 import b64encode
from typing import Optional

import httpx
from fastapi import HTTPException

SNAP_AUTH_URL = "https://accounts.snapchat.com/login/oauth2/authorize"
SNAP_TOKEN_URL = "https://accounts.snapchat.com/login/oauth2/access_token"
SNAP_ADS_API = "https://adsapi.snapchat.com/v1"


def _get_snap_credentials():
    """Get Confidential OAuth credentials (for token exchange)."""
    client_id = os.getenv("SNAP_CLIENT_ID")
    client_secret = os.getenv("SNAP_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(500, "Snapchat credentials not configured")
    return client_id, client_secret


def get_snap_auth_url(redirect_uri: str, state: Optional[str] = None) -> str:
    """Build the Snapchat OAuth2 authorization URL using the PUBLIC client ID."""
    # Authorization URL uses the PUBLIC Client ID
    # Token exchange uses the CONFIDENTIAL Client ID + Secret
    public_client_id = os.getenv("SNAP_PUBLIC_CLIENT_ID")
    if not public_client_id:
        raise HTTPException(500, "SNAP_PUBLIC_CLIENT_ID not configured")
    params = {
        "client_id": public_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "snapchat-marketing-api",
    }
    if state:
        params["state"] = state
    from urllib.parse import urlencode
    return f"{SNAP_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """
    Exchange the authorization code for access + refresh tokens.
    Snapchat uses HTTP Basic Auth (client_id:client_secret) for the token endpoint.
    """
    client_id, client_secret = _get_snap_credentials()
    basic = b64encode(f"{client_id}:{client_secret}".encode()).decode()

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
            raise HTTPException(400, f"Snapchat token exchange failed: {resp.text}")
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """
    Refresh a Snapchat access token using the refresh token.
    Access tokens expire in ~30 minutes; refresh tokens last much longer.
    """
    client_id, client_secret = _get_snap_credentials()
    basic = b64encode(f"{client_id}:{client_secret}".encode()).decode()

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
            raise HTTPException(400, f"Snapchat token refresh failed: {resp.text}")
        return resp.json()


async def get_authenticated_user(access_token: str) -> dict:
    """Fetch the authenticated user's info from Snapchat."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{SNAP_ADS_API}/me",
            headers={"Authorization": f"Bearer {access_token}"},
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


async def ensure_fresh_token(account: dict) -> str:
    """
    Given a stored account dict, check if the token needs refresh.
    If a refresh_token exists, proactively refresh and return the new access_token.
    The caller is responsible for persisting the updated token.
    """
    refresh_token = account.get("refresh_token")
    if not refresh_token:
        # No refresh token available; return existing token as-is
        return account["access_token"]

    try:
        token_data = await refresh_access_token(refresh_token)
        return token_data["access_token"], token_data.get("refresh_token", refresh_token)
    except HTTPException:
        # Refresh failed – return existing token; it may still be valid
        return account["access_token"], refresh_token
