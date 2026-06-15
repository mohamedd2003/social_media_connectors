import os
import glob
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Form, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import List, Optional

from database import init_db, save_account, get_accounts, get_account, has_accounts

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

from routers.snapchat import router as snapchat_router
from routers.snapchat_v1 import router as snapchat_v1_router
from routers.tiktok import router as tiktok_router
from routers.tiktok_competitor import router as tiktok_competitor_router

APP_ID = os.getenv("META_APP_ID")
APP_SECRET = os.getenv("META_APP_SECRET")
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000")
REDIRECT_URI = os.getenv("REDIRECT_URI", f"{PUBLIC_BACKEND_URL}/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
GRAPH_API = "https://graph.facebook.com/v22.0"


@asynccontextmanager
async def lifespan(app):
    # Startup
    init_db()
    yield
    # Shutdown: clean up any leftover uploaded files
    cleanup_uploads()


def cleanup_uploads():
    """Remove all files from static/uploads."""
    upload_dir = os.path.join("static", "uploads")
    for f in glob.glob(os.path.join(upload_dir, "*")):
        try:
            os.remove(f)
        except OSError:
            pass


app = FastAPI(title="Meta Insights Prototype", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── Snapchat Router ─────────────────────────────────────────────────────
app.include_router(snapchat_router)
app.include_router(snapchat_v1_router)

# ─── TikTok Router ───────────────────────────────────────────────────────
app.include_router(tiktok_router)
app.include_router(tiktok_competitor_router)


# ─── Step 1: OAuth Flow ─────────────────────────────────────────────────────

@app.get("/auth/login")
def login():
    """Redirect user to Meta's OAuth dialog."""
    params = urlencode({
        "client_id": APP_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "pages_show_list,pages_read_engagement,pages_read_user_content,pages_manage_posts,instagram_basic,instagram_manage_insights,instagram_content_publish,business_management",
        "response_type": "code",
    })
    return RedirectResponse(f"https://www.facebook.com/v22.0/dialog/oauth?{params}")


@app.get("/auth/callback")
async def callback(code: str = Query(...)):
    """Exchange code for tokens, resolve accounts, and store them."""
    async with httpx.AsyncClient() as client:
        # Exchange code for short-lived token
        resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        })
        if resp.status_code != 200:
            raise HTTPException(400, f"Token exchange failed: {resp.text}")
        short_token = resp.json()["access_token"]

        # Exchange for long-lived user token (60 days)
        resp = await client.get(f"{GRAPH_API}/oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": APP_ID,
            "client_secret": APP_SECRET,
            "fb_exchange_token": short_token,
        })
        if resp.status_code != 200:
            raise HTTPException(
                400, f"Long-lived token exchange failed: {resp.text}")
        long_token = resp.json()["access_token"]

        # Get pages
        resp = await client.get(f"{GRAPH_API}/me/accounts", params={
            "access_token": long_token,
        })
        if resp.status_code != 200:
            raise HTTPException(400, f"Failed to fetch pages: {resp.text}")
        pages = resp.json().get("data", [])

        for page in pages:
            page_id = page["id"]
            page_token = page["access_token"]
            page_name = page.get("name", "Unnamed Page")

            # Resolve linked Instagram Business Account
            ig_resp = await client.get(f"{GRAPH_API}/{page_id}", params={
                "fields": "instagram_business_account",
                "access_token": page_token,
            })
            ig_account_id = None
            if ig_resp.status_code == 200:
                ig_data = ig_resp.json().get("instagram_business_account")
                if ig_data:
                    ig_account_id = ig_data["id"]

            # Save page
            save_account(page_id, "facebook_page", page_name,
                         page_token, ig_account_id, long_token)

            # Save IG account separately if exists
            if ig_account_id:
                save_account(ig_account_id, "instagram",
                             f"{page_name} (IG)", page_token, None, long_token)

    return RedirectResponse(f"{FRONTEND_URL}?connected=true")


# ─── Step 1 helpers ──────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    """Check if any accounts are connected."""
    return {"connected": has_accounts()}


@app.get("/api/accounts")
def list_accounts():
    """List all connected accounts."""
    accounts = get_accounts()
    return [{"id": a["id"], "name": a["name"], "type": a["type"]} for a in accounts]


@app.post("/api/publish")
async def publish_post(
    request: Request,
    account_id: str = Form(...),
    message: str = Form(...),
    images: List[UploadFile] = File(default=[])
):
    """Publish a post."""
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Account not found")
    
    from connectors import get_connector
    try:
        connector = get_connector(account["type"])
    except ValueError as e:
        raise HTTPException(400, str(e))

    base_url = os.getenv("PUBLIC_BACKEND_URL") or str(request.base_url)
    return await connector.publish_post(account_id, account["access_token"], message, images, base_url=base_url)


# ─── Step 2: Fetch & Calculate Insights ──────────────────────────────────────

@app.get("/api/insights")
async def get_insights(account_id: str = Query(...)):
    """Fetch posts and calculate engagement for a given account."""
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    from connectors import get_connector
    try:
        connector = get_connector(account["type"])
    except ValueError as e:
        raise HTTPException(400, str(e))

    return await connector.get_insights(account_id, account["access_token"])

@app.get("/api/comments")
async def get_comments(account_id: str = Query(...), post_id: str = Query(...)):
    """Fetch comments for a specific post."""
    account = get_account(account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    from connectors import get_connector
    try:
        connector = get_connector(account["type"])
    except ValueError as e:
        raise HTTPException(400, str(e))

    return await connector.get_comments(post_id, account["access_token"])
