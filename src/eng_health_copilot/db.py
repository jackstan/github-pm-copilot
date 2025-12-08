import sqlite3
from pathlib import Path

DB_PATH = Path("data") / "eng_health.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS issues (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    number INTEGER,
    title TEXT,
    state TEXT,
    created_at TEXT,
    closed_at TEXT,
    labels TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    number INTEGER,
    title TEXT,
    state TEXT,
    created_at TEXT,
    merged_at TEXT,
    closed_at TEXT,
    user_login TEXT
);

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT,
    repo_owner TEXT,
    repo_name TEXT,
    author_login TEXT,
    author_date TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS weekly_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_owner TEXT,
    repo_name TEXT,
    week_start TEXT,
    week_end TEXT,
    pr_throughput INTEGER,
    pr_lead_time_p50 REAL,
    pr_lead_time_p90 REAL,
    open_bugs_count INTEGER,
    wip_prs INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn
