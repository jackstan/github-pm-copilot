from typing import Optional, Dict, Any

import pandas as pd

from .db import get_db, read_sql_query


def get_last_weekly_metrics(owner: str, repo: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    df = read_sql_query(
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
    df = read_sql_query(
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


def get_llm_context(
    owner: str,
    repo: str,
    weeks_back: int = 12,
    recent_items: int = 25,
) -> Dict[str, Any]:
    """
    Build a compact context payload for LLM-based agents.

    Includes:
      - Recent weekly metrics history (last `weeks_back` weeks)
      - Recent pull requests (with size + labels)
      - Recent PR reviews
      - Recent CI statuses
      - Recent releases
    """
    conn = get_db()
    try:
        # ---------- Weekly metrics history ----------
        hist_df = read_sql_query(
            """
            SELECT *
            FROM weekly_metrics
            WHERE repo_owner = ?
              AND repo_name = ?
            ORDER BY week_start
            """,
            conn,
            params=(owner, repo),
        )

        weekly_history = []
        if not hist_df.empty:
            hist_df["week_start"] = pd.to_datetime(hist_df["week_start"])
            # Keep only last `weeks_back` weeks of history
            cutoff = hist_df["week_start"].max() - pd.Timedelta(weeks=weeks_back)
            recent_hist = hist_df[hist_df["week_start"] >= cutoff]
            weekly_history = recent_hist.to_dict(orient="records")

        # ---------- Recent pull requests ----------
        pr_df = read_sql_query(
            """
            SELECT
                number,
                title,
                state,
                created_at,
                merged_at,
                closed_at,
                labels,
                additions,
                deletions,
                changed_files,
                head_sha
            FROM pull_requests
            WHERE repo_owner = ?
              AND repo_name = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            conn,
            params=(owner, repo, recent_items),
        )
        recent_prs = pr_df.to_dict(orient="records") if not pr_df.empty else []

        # ---------- Recent PR reviews ----------
        reviews_df = read_sql_query(
            """
            SELECT
                pr_number,
                user_login,
                state,
                submitted_at
            FROM pr_reviews
            WHERE repo_owner = ?
              AND repo_name = ?
            ORDER BY datetime(submitted_at) DESC
            LIMIT ?
            """,
            conn,
            params=(owner, repo, recent_items),
        )
        recent_reviews = reviews_df.to_dict(orient="records") if not reviews_df.empty else []

        # ---------- Recent CI statuses ----------
        ci_df = read_sql_query(
            """
            SELECT
                sha,
                pr_number,
                state,
                last_updated
            FROM ci_statuses
            WHERE repo_owner = ?
              AND repo_name = ?
            ORDER BY datetime(last_updated) DESC
            LIMIT ?
            """,
            conn,
            params=(owner, repo, recent_items),
        )
        recent_ci = ci_df.to_dict(orient="records") if not ci_df.empty else []

        # ---------- Recent releases ----------
        rel_df = read_sql_query(
            """
            SELECT
                tag_name,
                name,
                created_at,
                published_at
            FROM releases
            WHERE repo_owner = ?
              AND repo_name = ?
            ORDER BY
                COALESCE(datetime(published_at), datetime(created_at)) DESC
            LIMIT ?
            """,
            conn,
            params=(owner, repo, recent_items),
        )
        recent_releases = rel_df.to_dict(orient="records") if not rel_df.empty else []

    finally:
        conn.close()

    return {
        "weekly_history": weekly_history,
        "recent_pull_requests": recent_prs,
        "recent_pr_reviews": recent_reviews,
        "recent_ci_statuses": recent_ci,
        "recent_releases": recent_releases,
    }
