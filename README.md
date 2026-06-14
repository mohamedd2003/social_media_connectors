# Meta + Snapchat Insights Dashboard

FastAPI + React dashboard for connected social accounts, including:

- Facebook Pages (Meta Graph API)
- Instagram Business Accounts (Meta Graph API)
- Snapchat Ad Accounts / Public Profile data (Snapchat APIs)

The app supports OAuth connection, account storage in SQLite, insights retrieval, and Snapchat-specific dashboard views.

## Project Structure

```text
meta/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── connectors/
│   │   ├── facebook.py
│   │   ├── instagram.py
│   │   └── snapchat.py
│   ├── routers/
│   │   ├── snapchat.py
│   │   └── snapchat_v1.py
│   ├── services/
│   │   ├── snapchat_service.py
│   │   └── snapchat_api_service.py
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   └── components/
    │       ├── SnapchatOAuthButton.jsx
    │       ├── SnapchatDashboard.jsx
    │       └── SnapchatShareButton.jsx
    └── package.json
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- Meta developer app (for Facebook/Instagram)
- Snapchat app credentials (for OAuth + ads/profile endpoints)

## Environment Variables

Create backend/.env and configure at least:

```env
# Common
PUBLIC_BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173

# Meta
META_APP_ID=...
META_APP_SECRET=...
REDIRECT_URI=http://localhost:8000/auth/callback

# Snapchat
SNAP_CLIENT_ID=...
SNAP_CLIENT_SECRET=...
SNAP_REDIRECT_URI=http://localhost:8000/snap/auth/callback
SNAP_OAUTH_SCOPE=snapchat-marketing-api snapchat-profile-api
```

Notes:
- Snapchat token endpoints use HTTP Basic auth with SNAP_CLIENT_ID:SNAP_CLIENT_SECRET.
- Access token refresh is handled automatically before API calls when refresh_token exists.
- Snapchat access tokens are short-lived (around 30 minutes), so refresh flow is required.

## Run Locally

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

App URLs:
- Frontend: http://localhost:5173
- Backend: http://localhost:8000

## Snapchat Integration Overview

### OAuth Flow

1. Frontend button calls /snap/auth/login.
2. User authorizes on Snapchat.
3. Snapchat redirects to /snap/auth/callback.
4. Backend exchanges code for access_token + refresh_token.
5. Account is stored in SQLite accounts table with type=snapchat.

Primary router prefix for Snapchat routes: /snap

### Main Snapchat Endpoints

OAuth and account setup:
- GET /snap/auth/login
- GET /snap/auth/callback
- POST /snap/discover
- POST /snap/auth/refresh

Insights and profile dashboard:
- GET /snap/profile/overview
- GET /snap/insights
- GET /snap/profile/insights
- GET /snap/profile/stories
- GET /snap/profile/spotlight
- GET /snap/profile/promotions

Manual metrics fallback:
- GET /snap/manual-metrics
- PUT /snap/manual-metrics

Stories/media:
- GET /snap/stories
- POST /snap/stories/create
- POST /snap/profile/stories/create
- DELETE /snap/media/{media_id}

Campaign/ad creation:
- POST /snap/campaigns/create
- POST /snap/ads/create

### Versioned Snapchat Analytics API

Additional production-style endpoints are available under:

- GET /api/v1/snapchat/profile-insights/{profile_id}
- GET /api/v1/snapchat/profile-insights/{profile_id}/stories/{story_id}/stats
- GET /api/v1/snapchat/ads-insights/{ad_account_id}

These endpoints are implemented via services/snapchat_api_service.py and include structured error handling for 401/403/404/429/5xx cases.

### DNS / Network Troubleshooting

If Snapchat requests fail with DNS-related errors (getaddrinfo/NameResolutionError/ConnectError), the backend returns clear 502 messages.

Typical fixes:
- Disable DNS/ad-block filtering tools.
- Switch DNS resolver to 8.8.8.8 or 1.1.1.1.
- Retry /snap/discover after connectivity is fixed.

## Frontend Snapchat Behavior

- Snapchat connection button: + Add Snapchat
- If selected account type is snapchat, UI renders SnapchatDashboard instead of the FB/IG post composer.
- Dashboard supports:
  - Profile header and overview metrics
  - Public stories / saved stories / spotlight tabs
  - Optional ads campaign insight section
  - Manual metric editing and persistence

## Data Storage

SQLite database file: backend/app.db

Tables:
- accounts: stores tokens and account metadata (including refresh_token and org_id)
- manual_metrics: Snapchat fallback metrics (followers, reach, views)

## Security Notes

- Do not commit .env with real secrets.
- This project is a prototype and not hardened for public production use.
- Protect callback URLs, token storage, and CORS settings before deployment.
