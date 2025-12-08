from datetime import datetime, timedelta

import pandas as pd

from .config import get_settings
from .db import get_db
from .github_client import (
    get_github_session,
    fetch_issues,
    fetch_pulls,
    fetch_commits,
)


def run_ingest(owner: str, repo: str, days_back: int) -> None:
    settings = get_settings()
    session = get_github_session(settings.github_token)

    since = datetime.utcnow() - timedelta(days=days_back)

    print(f"[ingest] Fetching data for {owner}/{repo} since {since.isoformat()}")

    issues = fetch_issues(session, owner, repo, since)
    pulls = fetch_pulls(session, owner, repo)
    commits = fetch_commits(session, owner, repo, since)

    conn = get_db()
    cur = conn.cursor()

    # For now, wipe existing rows for this repo (simple strategy)
    cur.execute(
        "DELETE FROM issues WHERE repo_owner=? AND repo_name=?", (owner, repo)
    )
    cur.execute(
        "DELETE FROM pull_requests WHERE repo_owner=? AND repo_name=?",
        (owner, repo),
    )
    cur.execute(
        "DELETE FROM commits WHERE repo_owner=? AND repo_name=?", (owner, repo)
    )

    # Insert new data
    if issues:
        issues_df = pd.json_normalize(issues)
        issues_df["repo_owner"] = owner
        issues_df["repo_name"] = repo
        issues_df.rename(
            columns={
                "id": "id",
                "number": "number",
                "title": "title",
                "state": "state",
                "created_at": "created_at",
                "closed_at": "closed_at",
            },
            inplace=True,
        )
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
        issues_df[cols].to_sql("issues", conn, if_exists="append", index=False)

    if pulls:
        pulls_df = pd.json_normalize(pulls)
        pulls_df["repo_owner"] = owner
        pulls_df["repo_name"] = repo
        pulls_df.rename(
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
        cols = [
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
        pulls_df[cols].to_sql("pull_requests", conn, if_exists="append", index=False)

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
        commits_df[cols].to_sql("commits", conn, if_exists="append", index=False)

    conn.commit()
    conn.close()

    print(
        f"[ingest] Completed ingest for {owner}/{repo} "
        f"(issues={len(issues)}, pulls={len(pulls)}, commits={len(commits)})"
    )
