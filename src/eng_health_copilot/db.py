import os
import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

DEFAULT_DB_PATH = Path("data") / "eng_health.db"

SCHEMA_SQLITE = """
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

CREATE TABLE IF NOT EXISTS pr_reviews (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number INTEGER,
    user_login TEXT,
    state TEXT,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS ci_statuses (
    sha TEXT,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number INTEGER,
    state TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS releases (
    id INTEGER,
    repo_owner TEXT,
    repo_name TEXT,
    tag_name TEXT,
    name TEXT,
    created_at TEXT,
    published_at TEXT
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

CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    last_sync_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (repo_owner, repo_name)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    days_back INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER,
    model TEXT,
    temperature REAL,
    data_sufficiency_level TEXT,
    input_hash TEXT,
    metrics_json TEXT,
    anomalies_json TEXT,
    context_json TEXT,
    summary_markdown TEXT,
    error_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    eval_id TEXT,
    eval_run_id TEXT,
    eval_name TEXT,
    run_name TEXT,
    model TEXT,
    grading_model TEXT,
    dataset_path TEXT,
    static_count INTEGER,
    production_count INTEGER,
    total_count INTEGER,
    ran_count INTEGER,
    skipped_count INTEGER,
    baseline_present INTEGER,
    soft_gate_failed INTEGER,
    overall_average REAL,
    sparse_average REAL,
    sparse_calibration_average REAL,
    output_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    run_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT,
    tags_json TEXT,
    scores_json TEXT,
    criterion_pass_json TEXT,
    deterministic_json TEXT,
    anomaly_count INTEGER,
    model_all_pass INTEGER,
    PRIMARY KEY (run_key, case_id)
);

CREATE INDEX IF NOT EXISTS idx_issues_repo_number
ON issues(repo_owner, repo_name, number);

CREATE INDEX IF NOT EXISTS idx_pull_requests_repo_number
ON pull_requests(repo_owner, repo_name, number);

CREATE INDEX IF NOT EXISTS idx_commits_repo_author_date
ON commits(repo_owner, repo_name, author_date);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo_pr
ON pr_reviews(repo_owner, repo_name, pr_number);

CREATE INDEX IF NOT EXISTS idx_ci_statuses_repo_pr
ON ci_statuses(repo_owner, repo_name, pr_number);

CREATE INDEX IF NOT EXISTS idx_releases_repo_published
ON releases(repo_owner, repo_name, published_at);

CREATE INDEX IF NOT EXISTS idx_weekly_metrics_repo_week
ON weekly_metrics(repo_owner, repo_name, week_start);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_repo_completed
ON analysis_runs(repo_owner, repo_name, completed_at);

CREATE INDEX IF NOT EXISTS idx_eval_runs_created
ON eval_runs(created_at);

CREATE INDEX IF NOT EXISTS idx_eval_case_results_run
ON eval_case_results(run_key);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS issues (
    id BIGINT,
    repo_owner TEXT,
    repo_name TEXT,
    number BIGINT,
    title TEXT,
    state TEXT,
    created_at TEXT,
    closed_at TEXT,
    labels TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id BIGINT,
    repo_owner TEXT,
    repo_name TEXT,
    number BIGINT,
    title TEXT,
    state TEXT,
    created_at TEXT,
    merged_at TEXT,
    closed_at TEXT,
    user_login TEXT,
    labels TEXT,
    additions BIGINT,
    deletions BIGINT,
    changed_files BIGINT,
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

CREATE TABLE IF NOT EXISTS pr_reviews (
    id BIGINT,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number BIGINT,
    user_login TEXT,
    state TEXT,
    submitted_at TEXT
);

CREATE TABLE IF NOT EXISTS ci_statuses (
    sha TEXT,
    repo_owner TEXT,
    repo_name TEXT,
    pr_number BIGINT,
    state TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS releases (
    id BIGINT,
    repo_owner TEXT,
    repo_name TEXT,
    tag_name TEXT,
    name TEXT,
    created_at TEXT,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS weekly_metrics (
    id BIGSERIAL PRIMARY KEY,
    repo_owner TEXT,
    repo_name TEXT,
    week_start TEXT,
    week_end TEXT,
    pr_throughput BIGINT,
    pr_lead_time_p50 DOUBLE PRECISION,
    pr_lead_time_p90 DOUBLE PRECISION,
    open_bugs_count BIGINT,
    wip_prs BIGINT,
    aging_prs_7d_plus BIGINT,
    open_issues_count BIGINT,
    new_issues_count BIGINT,
    closed_issues_count BIGINT,
    new_bugs_created BIGINT,
    bugs_closed BIGINT,
    net_bug_delta BIGINT,
    commits_per_week BIGINT,
    active_contributors_per_week BIGINT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    last_sync_at TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (repo_owner, repo_name)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    days_back BIGINT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    duration_ms BIGINT,
    model TEXT,
    temperature DOUBLE PRECISION,
    data_sufficiency_level TEXT,
    input_hash TEXT,
    metrics_json TEXT,
    anomalies_json TEXT,
    context_json TEXT,
    summary_markdown TEXT,
    error_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    eval_id TEXT,
    eval_run_id TEXT,
    eval_name TEXT,
    run_name TEXT,
    model TEXT,
    grading_model TEXT,
    dataset_path TEXT,
    static_count BIGINT,
    production_count BIGINT,
    total_count BIGINT,
    ran_count BIGINT,
    skipped_count BIGINT,
    baseline_present BOOLEAN,
    soft_gate_failed BOOLEAN,
    overall_average DOUBLE PRECISION,
    sparse_average DOUBLE PRECISION,
    sparse_calibration_average DOUBLE PRECISION,
    output_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_case_results (
    run_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT,
    tags_json TEXT,
    scores_json TEXT,
    criterion_pass_json TEXT,
    deterministic_json TEXT,
    anomaly_count BIGINT,
    model_all_pass BOOLEAN,
    PRIMARY KEY (run_key, case_id)
);

CREATE INDEX IF NOT EXISTS idx_issues_repo_number
ON issues(repo_owner, repo_name, number);

CREATE INDEX IF NOT EXISTS idx_pull_requests_repo_number
ON pull_requests(repo_owner, repo_name, number);

CREATE INDEX IF NOT EXISTS idx_commits_repo_author_date
ON commits(repo_owner, repo_name, author_date);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo_pr
ON pr_reviews(repo_owner, repo_name, pr_number);

CREATE INDEX IF NOT EXISTS idx_ci_statuses_repo_pr
ON ci_statuses(repo_owner, repo_name, pr_number);

CREATE INDEX IF NOT EXISTS idx_releases_repo_published
ON releases(repo_owner, repo_name, published_at);

CREATE INDEX IF NOT EXISTS idx_weekly_metrics_repo_week
ON weekly_metrics(repo_owner, repo_name, week_start);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_repo_completed
ON analysis_runs(repo_owner, repo_name, completed_at);

CREATE INDEX IF NOT EXISTS idx_eval_runs_created
ON eval_runs(created_at);

CREATE INDEX IF NOT EXISTS idx_eval_case_results_run
ON eval_case_results(run_key);
"""


def _detect_backend() -> str:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url.startswith("postgres://") or db_url.startswith("postgresql://"):
        return "postgres"
    return "sqlite"


def _convert_placeholders(sql: str, backend: str) -> str:
    if backend == "postgres":
        return sql.replace("?", "%s")
    return sql


class CursorWrapper:
    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self.backend = backend

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> "CursorWrapper":
        converted = _convert_placeholders(sql, self.backend)
        if params is None:
            self._cursor.execute(converted)
        else:
            self._cursor.execute(converted, tuple(params))
        return self

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class DBConnection:
    def __init__(self, conn: Any, backend: str):
        self._conn = conn
        self.backend = backend

    def cursor(self) -> CursorWrapper:
        return CursorWrapper(self._conn.cursor(), self.backend)

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None) -> CursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params=params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @property
    def raw(self) -> Any:
        return self._conn


def get_db_path() -> Path:
    env_path = os.getenv("ENG_HEALTH_DB_PATH", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def _init_sqlite(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQLITE)


def _init_postgres(conn: Any) -> None:
    cur = conn.cursor()
    try:
        for stmt in SCHEMA_POSTGRES.split(";"):
            trimmed = stmt.strip()
            if trimmed:
                cur.execute(trimmed)
        conn.commit()
    finally:
        cur.close()


def get_db() -> DBConnection:
    backend = _detect_backend()
    if backend == "postgres":
        # Local import keeps sqlite-only users from needing psycopg2 installed at import time.
        import psycopg2  # type: ignore

        conn = psycopg2.connect(os.getenv("DATABASE_URL", ""))
        _init_postgres(conn)
        return DBConnection(conn, backend="postgres")

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5)
    _init_sqlite(conn)
    return DBConnection(conn, backend="sqlite")


def read_sql_query(sql: str, conn: DBConnection, params: Optional[Sequence[Any]] = None) -> pd.DataFrame:
    converted = _convert_placeholders(sql, conn.backend)
    return pd.read_sql_query(converted, conn.raw, params=tuple(params) if params is not None else None)
