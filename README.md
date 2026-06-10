# Meta Insights Dashboard – Prototype

A minimal prototype that connects to Meta's Graph API (v22.0) to retrieve and display post insights for Facebook Pages and Instagram Business accounts.

## Project Structure

```
meta/
├── backend/
│   ├── main.py            # FastAPI app (OAuth + insights endpoints)
│   ├── database.py        # SQLite helper
│   ├── requirements.txt
│   └── .env.example       # Template for credentials
└── frontend/
    ├── src/
    │   ├── App.jsx        # Single-page dashboard
    │   ├── main.jsx
    │   └── index.css
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── postcss.config.js
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- A **Meta Developer App** with:
  - Facebook Login product added
  - Valid OAuth redirect URI set to `http://localhost:8000/auth/callback`
  - Permissions configured: `pages_show_list`, `pages_read_engagement`, `read_insights`, `instagram_basic`, `instagram_manage_insights`

---

## Setup Instructions

### 1. Configure Credentials

```bash
cd backend
copy .env.example .env
```

Open `backend/.env` and paste your credentials:

```env
META_APP_ID=123456789012345
META_APP_SECRET=abcdef1234567890abcdef1234567890
REDIRECT_URI=http://localhost:8000/auth/callback
FRONTEND_URL=http://localhost:5173
```

> Get these from https://developers.facebook.com → Your App → Settings → Basic.

---

### 2. Start the Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

---

### 3. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be at `http://localhost:5173`.

---

## How to Use

1. Open `http://localhost:5173` in your browser.
2. Click **"Connect Facebook / Instagram"** – you'll be redirected to Meta's login screen.
3. Authorize the app and grant the requested permissions.
4. After redirect, you'll see a green **"Connected"** badge.
5. Select a Page or Instagram account from the dropdown.
6. Post insights will load in the table with calculated engagement rates.

---

## Engagement Rate Formula

$$
\text{Engagement Rate} = \frac{\text{Likes} + \text{Comments} + \text{Saves}}{\text{Reach}} \times 100
$$

If Reach is unavailable, Impressions is used as the denominator.

---

## Alerts

| Badge                  | Condition            |
| ---------------------- | -------------------- |
| 🔴 **Needs attention** | Engagement Rate < 1% |
| 🟢 **High Engagement** | Engagement Rate > 5% |

---

## Notes

- Tokens are stored in a local `app.db` SQLite file (created automatically).
- Long-lived user tokens expire after 60 days. Re-connect to refresh.
- This is a prototype – not production-ready. Do not expose to the public internet without adding proper security.

npx localtunnel --port 8000 --subdomain miraf-meta
