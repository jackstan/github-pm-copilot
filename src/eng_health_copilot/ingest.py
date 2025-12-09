from datetime import datetime, timedelta

import pandas as pd

from .config import get_settings
from .db import get_db
from .github_client import (
    get_github_session,
    fetch_issues,
    fetch_pulls_for_metrics,
    fetch_pulls,
    fetch_commits,
    fetch_releases,
    enrich_pulls_with_details_reviews_and_ci,
)


def run_ingest(owner: str, repo: str, days_back: int) -> None:
    settings = get_settings()
    session = get_github_session(settings.github_token)

    since = datetime.utcnow() - timedelta(days=days_back)

    print(f"[ingest] Fetching data for {owner}/{repo} since {since.isoformat()}")

    issues = fetch_issues(session, owner, repo, since)
    metrics_pulls = fetch_pulls_for_metrics(session, owner, repo, since)
    commits = fetch_commits(session, owner, repo, since)
    releases = fetch_releases(session, owner, repo)

    # Enrich only recent PRs for agent context (reviews, CI, size, labels)
    recent_pulls = fetch_pulls(session, owner, repo)
    pr_enriched = enrich_pulls_with_details_reviews_and_ci(session, owner, repo, recent_pulls)
    enriched_pulls = pr_enriched["pulls"]
    pr_reviews = pr_enriched["reviews"]
    ci_statuses = pr_enriched["ci_statuses"]

    conn = get_db()
    try:
        cur = conn.cursor()

        # For now, wipe existing rows for this repo (simple strategy)
        cur.execute("DELETE FROM issues WHERE repo_owner=? AND repo_name=?", (owner, repo))
        cur.execute("DELETE FROM pull_requests WHERE repo_owner=? AND repo_name=?", (owner, repo))
        cur.execute("DELETE FROM commits WHERE repo_owner=? AND repo_name=?", (owner, repo))
        cur.execute("DELETE FROM pr_reviews WHERE repo_owner=? AND repo_name=?", (owner, repo))
        cur.execute("DELETE FROM ci_statuses WHERE repo_owner=? AND repo_name=?", (owner, repo))
        cur.execute("DELETE FROM releases WHERE repo_owner=? AND repo_name=?", (owner, repo))

        # ---------------- Issues ----------------
        if issues:
            only_issues = [it for it in issues if "pull_request" not in it]
            if only_issues:
                issues_df = pd.json_normalize(only_issues)
                issues_df["repo_owner"] = owner
                issues_df["repo_name"] = repo
                issues_df["labels"] = issues_df.get("labels", []).apply(
                    lambda lbls: ",".join([l.get("name", "") for l in lbls])
                    if isinstance(lbls, list)
                    else ""
                )
                cols = [
                    "id",
                    "repo_owner",
                    "repo_name",
                    "number",
                    "title",
                    "state",
                    "created_at",
                    "closed_at",
                    "labels",
                ]
                for c in cols:
                    if c not in issues_df.columns:
                        issues_df[c] = None
                issues_df[cols].to_sql("issues", conn, if_exists="append", index=False)

        # ---------------- Pull Requests for metrics ----------------
        if metrics_pulls:
            pr_df = pd.json_normalize(metrics_pulls)
            pr_df["repo_owner"] = owner
            pr_df["repo_name"] = repo

            pr_df.rename(
                columns={
                    "id": "id",
                    "number": "number",
                    "title": "title",
                    "state": "state",
                    "created_at": "created_at",
                    "merged_at": "merged_at",
                    "closed_at": "closed_at",
                    "user.login": "user_login",
                },
                inplace=True,
            )

            # Make sure base columns exist
            base_cols = [
                "id",
                "repo_owner",
                "repo_name",
                "number",
                "title",
                "state",
                "created_at",
                "merged_at",
                "closed_at",
                "user_login",
            ]
            for c in base_cols:
                if c not in pr_df.columns:
                    pr_df[c] = None

            # Ensure extended columns exist (will be updated for recent PRs)
            pr_df["labels"] = ""
            pr_df["additions"] = None
            pr_df["deletions"] = None
            pr_df["changed_files"] = None
            pr_df["head_sha"] = None

            cols = base_cols + ["labels", "additions", "deletions", "changed_files", "head_sha"]

            pr_df[cols].to_sql("pull_requests", conn, if_exists="append", index=False)

        # ---------------- Commits ----------------
        if commits:
            commits_df = pd.json_normalize(commits)
            commits_df["repo_owner"] = owner
            commits_df["repo_name"] = repo
            commits_df.rename(
                columns={
                    "sha": "sha",
                    "commit.author.name": "author_login",
                    "commit.author.date": "author_date",
                    "commit.message": "message",
                },
                inplace=True,
            )
            cols = [
                "sha",
                "repo_owner",
                "repo_name",
                "author_login",
                "author_date",
                "message",
            ]
            for c in cols:
                if c not in commits_df.columns:
                    commits_df[c] = None
            commits_df[cols].to_sql("commits", conn, if_exists="append", index=False)

        # ---------------- PR Reviews ----------------
        if pr_reviews:
            reviews_df = pd.DataFrame(pr_reviews)
            cols = [
                "id",
                "repo_owner",
                "repo_name",
                "pr_number",
                "user_login",
                "state",
                "submitted_at",
            ]
            for c in cols:
                if c not in reviews_df.columns:
                    reviews_df[c] = None
            reviews_df[cols].to_sql("pr_reviews", conn, if_exists="append", index=False)

        # ---------------- CI Statuses ----------------
        if ci_statuses:
            ci_df = pd.DataFrame(ci_statuses)
            cols = [
                "sha",
                "repo_owner",
                "repo_name",
                "pr_number",
                "state",
                "last_updated",
            ]
            for c in cols:
                if c not in ci_df.columns:
                    ci_df[c] = None
            ci_df[cols].to_sql("ci_statuses", conn, if_exists="append", index=False)

        # ---------------- Releases ----------------
        if releases:
            rel_df = pd.json_normalize(releases)
            rel_df["repo_owner"] = owner
            rel_df["repo_name"] = repo
            rel_df.rename(
                columns={
                    "id": "id",
                    "tag_name": "tag_name",
                    "name": "name",
                    "created_at": "created_at",
                    "published_at": "published_at",
                },
                inplace=True,
            )
            cols = [
                "id",
                "repo_owner",
                "repo_name",
                "tag_name",
                "name",
                "created_at",
                "published_at",
            ]
            for c in cols:
                if c not in rel_df.columns:
                    rel_df[c] = None
            rel_df[cols].to_sql("releases", conn, if_exists="append", index=False)

        # ---------------- Update recent PRs with enriched fields ----------------
        if enriched_pulls and metrics_pulls:
            enriched_df = pd.json_normalize(enriched_pulls)
            # We expect number, labels_flat, additions, deletions, changed_files, head_sha
            for _, row in enriched_df.iterrows():
                number = row.get("number")
                if pd.isna(number):
                    continue

                labels_flat = row.get("labels_flat") or ""
                additions = row.get("additions")
                deletions = row.get("deletions")
                changed_files = row.get("changed_files")
                head_sha = row.get("head_sha")

                cur.execute(
                    """
                    UPDATE pull_requests
                    SET labels = ?, additions = ?, deletions = ?, changed_files = ?, head_sha = ?
                    WHERE repo_owner = ? AND repo_name = ? AND number = ?
                    """,
                    (
                        str(labels_flat),
                        int(additions) if pd.notna(additions) else None,
                        int(deletions) if pd.notna(deletions) else None,
                        int(changed_files) if pd.notna(changed_files) else None,
                        head_sha,
                        owner,
                        repo,
                        int(number),
                    ),
                )

        conn.commit()
    finally:
        conn.close()

    print(
        f"[ingest] Completed ingest for {owner}/{repo} "
        f"(issues={len(issues)}, metrics_pulls={len(metrics_pulls)}, "
        f"commits={len(commits)}, reviews={len(pr_reviews)}, "
        f"ci_rows={len(ci_statuses)}, releases={len(releases)})"
    )
