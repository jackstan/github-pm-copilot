from datetime import datetime, timedelta
from typing import Dict, Any

import numpy as np
import pandas as pd

from .db import get_db


def compute_latest_week_metrics(owner: str, repo: str) -> Dict[str, Any]:
    """Compute simple metrics for the last 7 days."""
    conn = get_db()

    now = datetime.utcnow()
    week_start = now - timedelta(days=7)

    week_start_iso = week_start.isoformat()
    # Pull requests
    pr_query = """
        SELECT created_at, merged_at, state
        FROM pull_requests
        WHERE repo_owner = ?
          AND repo_name = ?
          AND created_at >= ?
    """
    pr_df = pd.read_sql_query(
        pr_query,
        conn,
        params=(owner, repo, week_start_iso),
    )

    if not pr_df.empty:
        # Parse as UTC-aware, then drop timezone so everything is tz-naive but consistent
        pr_df["created_at"] = pd.to_datetime(pr_df["created_at"], utc=True).dt.tz_convert(None)
        pr_df["merged_at"] = pd.to_datetime(pr_df["merged_at"], utc=True).dt.tz_convert(None)

        merged = pr_df.dropna(subset=["merged_at"]).copy()
        merged["lead_time_days"] = (
            merged["merged_at"] - merged["created_at"]
        ).dt.total_seconds() / 86400

        pr_throughput = len(merged)
        p50 = float(np.percentile(merged["lead_time_days"], 50)) if len(merged) else None
        p90 = float(np.percentile(merged["lead_time_days"], 90)) if len(merged) else None
    else:
        pr_throughput = 0
        p50 = None
        p90 = None


    # Open bugs (simple heuristic: label contains 'bug')
    bugs_query = """
        SELECT COUNT(*) as cnt
        FROM issues
        WHERE repo_owner = ?
          AND repo_name = ?
          AND state = 'open'
          AND labels LIKE '%bug%'
    """
    open_bugs = pd.read_sql_query(
        bugs_query,
        conn,
        params=(owner, repo),
    )["cnt"].iloc[0]

    # WIP PRs = currently open PRs
    wip_query = """
        SELECT COUNT(*) as cnt
        FROM pull_requests
        WHERE repo_owner = ?
          AND repo_name = ?
          AND state = 'open'
    """
    wip_prs = pd.read_sql_query(
        wip_query,
        conn,
        params=(owner, repo),
    )["cnt"].iloc[0]

    metrics = {
        "repo_owner": owner,
        "repo_name": repo,
        "week_start": week_start.isoformat(),
        "week_end": now.isoformat(),
        "pr_throughput": pr_throughput,
        "pr_lead_time_p50": p50,
        "pr_lead_time_p90": p90,
        "open_bugs_count": int(open_bugs),
        "wip_prs": int(wip_prs),
    }

    # Persist into weekly_metrics
    conn.execute(
        """
        INSERT INTO weekly_metrics (
            repo_owner, repo_name, week_start, week_end,
            pr_throughput, pr_lead_time_p50, pr_lead_time_p90,
            open_bugs_count, wip_prs
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner,
            repo,
            metrics["week_start"],
            metrics["week_end"],
            metrics["pr_throughput"],
            metrics["pr_lead_time_p50"],
            metrics["pr_lead_time_p90"],
            metrics["open_bugs_count"],
            metrics["wip_prs"],
        ),
    )
    conn.commit()
    conn.close()

    return metrics
