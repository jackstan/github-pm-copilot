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
    user_login TEXT,
    labels TEXT,
    additions INTEGER,
    deletions INTEGER,
    changed_files INTEGER,
    head_sha TEXT
);

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT,
    repo_owner TEXT,
    repo_name TEXT,
    author_login TEXT,
    author_date TEXT,
    message TEXT
);

-- New: PR reviews
CREATE TABLE IF NOT EXISTS pr_reviews (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number INTEGER,
    user_login TEXT,
    state TEXT,
    submitted_at TEXT
);

-- New: CI statuses per PR head commit
CREATE TABLE IF NOT EXISTS ci_statuses (
    sha TEXT,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number INTEGER,
    state TEXT,
    last_updated TEXT
);

-- New: Releases / tags
CREATE TABLE IF NOT EXISTS releases (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    tag_name TEXT,
    name TEXT,
    created_at TEXT,
    published_at TEXT
);

-- Weekly metrics already defined earlier in your project;
-- we keep the richer version you've been using (no change here).
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
    aging_prs_7d_plus INTEGER,
    open_issues_count INTEGER,
    new_issues_count INTEGER,
    closed_issues_count INTEGER,
    new_bugs_created INTEGER,
    bugs_closed INTEGER,
    net_bug_delta INTEGER,
    commits_per_week INTEGER,
    active_contributors_per_week INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.executescript(SCHEMA)
    return conn
