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

    # --- Load raw PRs, issues, and commits for this repo ---
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

    commits_df = pd.read_sql_query(
        """
        SELECT author_date, author_login
        FROM commits
        WHERE repo_owner = ?
          AND repo_name = ?
          AND author_date >= ?
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

    if not commits_df.empty:
        commits_df["author_date"] = pd.to_datetime(commits_df["author_date"], utc=True).dt.tz_convert(None)

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

            # Correct WIP: PRs created before week_end and not yet closed by week_end
            wip_prs = pr_df[
                (pr_df["created_at"] <= week_end)
                & (
                    pr_df["closed_at"].isna()
                    | (pr_df["closed_at"] > week_end)
                )
            ].shape[0]

            # Aging PRs: open > 7 days at week_end
            seven_days_ago = week_end - timedelta(days=7)
            aging_prs = pr_df[
                (pr_df["created_at"] <= seven_days_ago)
                & (
                    pr_df["closed_at"].isna()
                    | (pr_df["closed_at"] > week_end)
                )
            ].shape[0]
        else:
            throughput = 0
            p50 = None
            p90 = None
            wip_prs = 0
            aging_prs = 0

        # --- Bug backlog & bug flow ---
        if not bug_issues.empty:
            # Bugs open at week_end
            open_bugs = bug_issues[
                (bug_issues["created_at"] <= week_end)
                & (
                    bug_issues["closed_at"].isna()
                    | (bug_issues["closed_at"] > week_end)
                )
            ].shape[0]

            # Bugs created during this week
            new_bugs = bug_issues[
                (bug_issues["created_at"] >= week_start)
                & (bug_issues["created_at"] < week_end)
            ].shape[0]

            # Bugs closed during this week
            closed_bugs = bug_issues[
                (bug_issues["closed_at"].notna())
                & (bug_issues["closed_at"] >= week_start)
                & (bug_issues["closed_at"] < week_end)
            ].shape[0]
        else:
            open_bugs = 0
            new_bugs = 0
            closed_bugs = 0

        net_bug_delta = new_bugs - closed_bugs

        # --- Issue backlog & flow (all issues, not just bugs) ---
        if not issues_df.empty:
            open_issues = issues_df[
                (issues_df["created_at"] <= week_end)
                & (
                    issues_df["closed_at"].isna()
                    | (issues_df["closed_at"] > week_end)
                )
            ].shape[0]

            new_issues = issues_df[
                (issues_df["created_at"] >= week_start)
                & (issues_df["created_at"] < week_end)
            ].shape[0]

            closed_issues = issues_df[
                (issues_df["closed_at"].notna())
                & (issues_df["closed_at"] >= week_start)
                & (issues_df["closed_at"] < week_end)
            ].shape[0]
        else:
            open_issues = 0
            new_issues = 0
            closed_issues = 0

        # --- Commits & contributors ---
        if not commits_df.empty:
            commits_in_week = commits_df[
                (commits_df["author_date"] >= week_start)
                & (commits_df["author_date"] < week_end)
            ].copy()

            commits_per_week = len(commits_in_week)
            active_contributors = (
                commits_in_week["author_login"].nunique()
                if not commits_in_week.empty
                else 0
            )
        else:
            commits_per_week = 0
            active_contributors = 0

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
            "aging_prs_7d_plus": int(aging_prs),
            "open_issues_count": int(open_issues),
            "new_issues_count": int(new_issues),
            "closed_issues_count": int(closed_issues),
            "new_bugs_created": int(new_bugs),
            "bugs_closed": int(closed_bugs),
            "net_bug_delta": int(net_bug_delta),
            "commits_per_week": int(commits_per_week),
            "active_contributors_per_week": int(active_contributors),
        }
        weekly_rows.append(row)

        conn.execute(
            """
            INSERT INTO weekly_metrics (
                repo_owner, repo_name, week_start, week_end,
                pr_throughput, pr_lead_time_p50, pr_lead_time_p90,
                open_bugs_count, wip_prs, aging_prs_7d_plus,
                open_issues_count, new_issues_count, closed_issues_count,
                new_bugs_created, bugs_closed, net_bug_delta,
                commits_per_week, active_contributors_per_week
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row["aging_prs_7d_plus"],
                row["open_issues_count"],
                row["new_issues_count"],
                row["closed_issues_count"],
                row["new_bugs_created"],
                row["bugs_closed"],
                row["net_bug_delta"],
                row["commits_per_week"],
                row["active_contributors_per_week"],
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
        "aging_prs_7d_plus": 0,
        "open_issues_count": 0,
        "new_issues_count": 0,
        "closed_issues_count": 0,
        "new_bugs_created": 0,
        "bugs_closed": 0,
        "net_bug_delta": 0,
        "commits_per_week": 0,
        "active_contributors_per_week": 0,
    }
    return latest
