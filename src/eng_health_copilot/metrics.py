from datetime import datetime, timedelta
from typing import Dict, Any, List

import numpy as np
import pandas as pd

from .db import get_db


def recompute_weekly_metrics(owner: str, repo: str, weeks_back: int = 12) -> Dict[str, Any]:
    """
    Recompute weekly metrics for the last `weeks_back` weeks and store them
    in the weekly_metrics table. Returns the most recent week's metrics.
    """
    conn = get_db()

    now = datetime.utcnow()
    start = now - timedelta(weeks=weeks_back)

    # Load raw PRs and issues for this repo
    pr_df = pd.read_sql_query(
        """
        SELECT created_at, merged_at, closed_at, state
        FROM pull_requests
        WHERE repo_owner = ?
          AND repo_name = ?
          AND created_at >= ?
        """,
        conn,
        params=(owner, repo, start.isoformat()),
    )

    issues_df = pd.read_sql_query(
        """
        SELECT created_at, closed_at, state, labels
        FROM issues
        WHERE repo_owner = ?
          AND repo_name = ?
          AND created_at >= ?
        """,
        conn,
        params=(owner, repo, start.isoformat()),
    )

    # Normalize datetimes to tz-naive (UTC) so we can safely subtract
    if not pr_df.empty:
        pr_df["created_at"] = pd.to_datetime(pr_df["created_at"], utc=True).dt.tz_convert(None)
        pr_df["merged_at"] = pd.to_datetime(pr_df["merged_at"], utc=True).dt.tz_convert(None)
        pr_df["closed_at"] = pd.to_datetime(pr_df["closed_at"], utc=True).dt.tz_convert(None)

    if not issues_df.empty:
        issues_df["created_at"] = pd.to_datetime(issues_df["created_at"], utc=True).dt.tz_convert(None)
        issues_df["closed_at"] = pd.to_datetime(issues_df["closed_at"], utc=True).dt.tz_convert(None)

    # Pre-filter bug issues
    if not issues_df.empty:
        bug_mask = issues_df["labels"].astype(str).str.contains("bug", case=False, na=False)
        bug_issues = issues_df[bug_mask].copy()
    else:
        bug_issues = pd.DataFrame(columns=["created_at", "closed_at", "state", "labels"])

    # Clear existing weekly metrics for this repo (simple approach)
    conn.execute(
        "DELETE FROM weekly_metrics WHERE repo_owner = ? AND repo_name = ?",
        (owner, repo),
    )

    weekly_rows: List[Dict[str, Any]] = []

    # Walk week by week
    week_start = start
    while week_start < now:
        week_end = week_start + timedelta(weeks=1)

        # --- PR metrics for this week ---
        if not pr_df.empty:
            # PRs that were merged in this week
            merged_in_week = pr_df[
                (pr_df["merged_at"].notna())
                & (pr_df["merged_at"] >= week_start)
                & (pr_df["merged_at"] < week_end)
            ].copy()

            throughput = len(merged_in_week)

            if throughput > 0:
                lead_times_days = (
                    (merged_in_week["merged_at"] - merged_in_week["created_at"])
                    .dt.total_seconds()
                    / 86400.0
                )
                p50 = float(np.percentile(lead_times_days, 50))
                p90 = float(np.percentile(lead_times_days, 90))
            else:
                p50 = None
                p90 = None

            # WIP PRs at week_end: created before end and still open
            wip_prs = pr_df[
                (pr_df["created_at"] <= week_end)
                & (pr_df["state"] == "open")
            ].shape[0]
        else:
            throughput = 0
            p50 = None
            p90 = None
            wip_prs = 0

        # --- Bug backlog at week_end ---
        if not bug_issues.empty:
            open_bugs = bug_issues[
                (bug_issues["created_at"] <= week_end)
                & (
                    bug_issues["closed_at"].isna()
                    | (bug_issues["closed_at"] > week_end)
                )
            ].shape[0]
        else:
            open_bugs = 0
        row = {
            "repo_owner": owner,
            "repo_name": repo,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "pr_throughput": int(throughput),
            "pr_lead_time_p50": float(p50) if p50 is not None else None,
            "pr_lead_time_p90": float(p90) if p90 is not None else None,
            "open_bugs_count": int(open_bugs),
            "wip_prs": int(wip_prs),
        }
        weekly_rows.append(row)

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
                row["repo_owner"],
                row["repo_name"],
                row["week_start"],
                row["week_end"],
                row["pr_throughput"],
                row["pr_lead_time_p50"],
                row["pr_lead_time_p90"],
                row["open_bugs_count"],
                row["wip_prs"],
            ),
        )

        week_start = week_end

    conn.commit()
    conn.close()

    if weekly_rows:
        return weekly_rows[-1]

    # Fallback if no data at all
    latest = {
        "repo_owner": owner,
        "repo_name": repo,
        "week_start": (now - timedelta(days=7)).isoformat(),
        "week_end": now.isoformat(),
        "pr_throughput": 0,
        "pr_lead_time_p50": None,
        "pr_lead_time_p90": None,
        "open_bugs_count": 0,
        "wip_prs": 0,
    }
    return latest