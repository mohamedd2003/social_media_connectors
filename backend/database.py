import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "app.db"


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT,
            access_token TEXT NOT NULL,
            ig_account_id TEXT,
            user_token TEXT,
            refresh_token TEXT,
            org_id TEXT
        );
    """)
    # Migrate: add columns if upgrading from older schema
    cursor = conn.execute("PRAGMA table_info(accounts)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "refresh_token" not in existing_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN refresh_token TEXT")
    if "org_id" not in existing_cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN org_id TEXT")
    conn.commit()
    conn.close()


def save_account(account_id: str, account_type: str, name: str, access_token: str, ig_account_id: str = None, user_token: str = None, refresh_token: str = None, org_id: str = None):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO accounts (id, type, name, access_token, ig_account_id, user_token, refresh_token, org_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, account_type, name, access_token, ig_account_id, user_token, refresh_token, org_id),
    )
    conn.commit()
    conn.close()


def update_account_tokens(account_id: str, access_token: str, refresh_token: str = None):
    """Update only the tokens for an existing account (used by Snapchat token refresh)."""
    conn = get_db()
    if refresh_token:
        conn.execute(
            "UPDATE accounts SET access_token = ?, refresh_token = ? WHERE id = ?",
            (access_token, refresh_token, account_id),
        )
    else:
        conn.execute(
            "UPDATE accounts SET access_token = ? WHERE id = ?",
            (access_token, account_id),
        )
    conn.commit()
    conn.close()


def get_accounts():
    conn = get_db()
    rows = conn.execute("SELECT * FROM accounts").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_account(account_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM accounts WHERE id = ?",
                       (account_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def has_accounts():
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()
    conn.close()
    return row["cnt"] > 0
