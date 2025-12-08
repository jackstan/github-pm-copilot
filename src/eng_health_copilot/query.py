from typing import Optional, Dict, Any

import pandas as pd

from .db import get_db


def get_last_weekly_metrics(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT *
        FROM weekly_metrics
        WHERE repo_owner = ?
          AND repo_name = ?
        ORDER BY week_end DESC
        LIMIT 1
        """,
        conn,
        params=(owner, repo),
    )
    conn.close()
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_weekly_metrics_history(owner: str, repo: str) -> pd.DataFrame:
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT
            week_start,
            pr_throughput,
            pr_lead_time_p50,
            pr_lead_time_p90,
            open_bugs_count,
            wip_prs,
            aging_prs_7d_plus,
            open_issues_count,
            new_issues_count,
            closed_issues_count,
            new_bugs_created,
            bugs_closed,
            net_bug_delta,
            commits_per_week,
            active_contributors_per_week
        FROM weekly_metrics
        WHERE repo_owner = ?
          AND repo_name = ?
        ORDER BY week_start
        """,
        conn,
        params=(owner, repo),
    )
    conn.close()
    return df
