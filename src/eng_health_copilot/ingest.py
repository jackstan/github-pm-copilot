from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import get_settings
from .db import get_db
from .github_client import (
    enrich_pulls_with_details_reviews_and_ci,
    fetch_commits,
    fetch_issues,
    fetch_pulls,
    fetch_pulls_for_metrics,
    fetch_releases,
    get_github_session,
)


def _as_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _labels_to_csv(labels: Any) -> str:
    if isinstance(labels, str):
        return labels
    if not isinstance(labels, list):
        return ""
    names: List[str] = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return ",".join(names)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _get_checkpoint_last_sync(cur, owner: str, repo: str) -> Optional[datetime]:
    row = cur.execute(
        """
        SELECT last_sync_at
        FROM ingest_checkpoints
        WHERE repo_owner = ? AND repo_name = ?
        """,
        (owner, repo),
    ).fetchone()
    if not row:
        return None
    return _parse_datetime(row[0])


def _update_checkpoint(cur, owner: str, repo: str, synced_at: datetime) -> None:
    synced_at_iso = synced_at.replace(microsecond=0).isoformat() + "Z"
    cur.execute(
        """
        INSERT INTO ingest_checkpoints (repo_owner, repo_name, last_sync_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(repo_owner, repo_name) DO UPDATE SET
            last_sync_at = excluded.last_sync_at,
            updated_at = CURRENT_TIMESTAMP
        """,
        (owner, repo, synced_at_iso),
    )


def _get_oldest_repo_timestamp(cur, owner: str, repo: str) -> Optional[datetime]:
    candidates: List[Optional[datetime]] = []
    queries = [
        ("SELECT MIN(created_at) FROM issues WHERE repo_owner = ? AND repo_name = ?", (owner, repo)),
        ("SELECT MIN(created_at) FROM pull_requests WHERE repo_owner = ? AND repo_name = ?", (owner, repo)),
        ("SELECT MIN(author_date) FROM commits WHERE repo_owner = ? AND repo_name = ?", (owner, repo)),
    ]
    for sql, params in queries:
        row = cur.execute(sql, params).fetchone()
        value = row[0] if row else None
        parsed = _parse_datetime(value)
        if parsed is not None:
            candidates.append(parsed)
    if not candidates:
        return None
    return min(candidates)


def _select_since_for_ingest(
    base_since: datetime,
    incremental_since: datetime,
    oldest_existing: Optional[datetime],
) -> datetime:
    # If data already covers the requested lookback window, use incremental sync.
    if oldest_existing is not None and oldest_existing <= base_since:
        return max(base_since, incremental_since)
    # Otherwise backfill from requested lookback start.
    return base_since


def _upsert_issue(cur, owner: str, repo: str, issue: Dict[str, Any]) -> None:
    issue_id = issue.get("id")
    if issue_id is None:
        return

    number = _as_int(issue.get("number"))
    title = issue.get("title")
    state = issue.get("state")
    created_at = issue.get("created_at")
    closed_at = issue.get("closed_at")
    labels = _labels_to_csv(issue.get("labels"))

    cur.execute(
        """
        UPDATE issues
        SET number = ?, title = ?, state = ?, created_at = ?, closed_at = ?, labels = ?
        WHERE repo_owner = ? AND repo_name = ? AND id = ?
        """,
        (number, title, state, created_at, closed_at, labels, owner, repo, issue_id),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO issues (
                id, repo_owner, repo_name, number, title, state, created_at, closed_at, labels
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (issue_id, owner, repo, number, title, state, created_at, closed_at, labels),
        )


def _pull_row(owner: str, repo: str, pr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    number = _as_int(pr.get("number"))
    if number is None:
        return None

    head = pr.get("head") if isinstance(pr.get("head"), dict) else {}
    user = pr.get("user") if isinstance(pr.get("user"), dict) else {}

    labels = pr.get("labels_flat")
    if labels is None:
        labels = _labels_to_csv(pr.get("labels"))

    return {
        "id": pr.get("id"),
        "repo_owner": owner,
        "repo_name": repo,
        "number": number,
        "title": pr.get("title"),
        "state": pr.get("state"),
        "created_at": pr.get("created_at"),
        "merged_at": pr.get("merged_at"),
        "closed_at": pr.get("closed_at"),
        "user_login": user.get("login"),
        "labels": labels or "",
        "additions": _as_int(pr.get("additions")),
        "deletions": _as_int(pr.get("deletions")),
        "changed_files": _as_int(pr.get("changed_files")),
        "head_sha": pr.get("head_sha") or head.get("sha"),
    }


def _upsert_pull_request(cur, row: Dict[str, Any]) -> None:
    cur.execute(
        """
        UPDATE pull_requests
        SET
            id = ?,
            title = ?,
            state = ?,
            created_at = ?,
            merged_at = ?,
            closed_at = ?,
            user_login = ?,
            labels = ?,
            additions = ?,
            deletions = ?,
            changed_files = ?,
            head_sha = ?
        WHERE repo_owner = ? AND repo_name = ? AND number = ?
        """,
        (
            row.get("id"),
            row.get("title"),
            row.get("state"),
            row.get("created_at"),
            row.get("merged_at"),
            row.get("closed_at"),
            row.get("user_login"),
            row.get("labels"),
            row.get("additions"),
            row.get("deletions"),
            row.get("changed_files"),
            row.get("head_sha"),
            row.get("repo_owner"),
            row.get("repo_name"),
            row.get("number"),
        ),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO pull_requests (
                id, repo_owner, repo_name, number, title, state,
                created_at, merged_at, closed_at, user_login,
                labels, additions, deletions, changed_files, head_sha
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("id"),
                row.get("repo_owner"),
                row.get("repo_name"),
                row.get("number"),
                row.get("title"),
                row.get("state"),
                row.get("created_at"),
                row.get("merged_at"),
                row.get("closed_at"),
                row.get("user_login"),
                row.get("labels"),
                row.get("additions"),
                row.get("deletions"),
                row.get("changed_files"),
                row.get("head_sha"),
            ),
        )


def _upsert_commit(cur, owner: str, repo: str, commit: Dict[str, Any]) -> None:
    sha = commit.get("sha")
    if not isinstance(sha, str) or not sha:
        return
    commit_obj = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
    author_obj = commit_obj.get("author") if isinstance(commit_obj.get("author"), dict) else {}

    author_login = author_obj.get("name")
    author_date = author_obj.get("date")
    message = commit_obj.get("message")

    cur.execute(
        """
        UPDATE commits
        SET author_login = ?, author_date = ?, message = ?
        WHERE repo_owner = ? AND repo_name = ? AND sha = ?
        """,
        (author_login, author_date, message, owner, repo, sha),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO commits (sha, repo_owner, repo_name, author_login, author_date, message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sha, owner, repo, author_login, author_date, message),
        )


def _upsert_pr_review(cur, review: Dict[str, Any]) -> None:
    review_id = review.get("id")
    owner = review.get("repo_owner")
    repo = review.get("repo_name")
    if review_id is None or not owner or not repo:
        return

    cur.execute(
        """
        UPDATE pr_reviews
        SET pr_number = ?, user_login = ?, state = ?, submitted_at = ?
        WHERE repo_owner = ? AND repo_name = ? AND id = ?
        """,
        (
            _as_int(review.get("pr_number")),
            review.get("user_login"),
            review.get("state"),
            review.get("submitted_at"),
            owner,
            repo,
            review_id,
        ),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO pr_reviews (
                id, repo_owner, repo_name, pr_number, user_login, state, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                owner,
                repo,
                _as_int(review.get("pr_number")),
                review.get("user_login"),
                review.get("state"),
                review.get("submitted_at"),
            ),
        )


def _upsert_ci_status(cur, row: Dict[str, Any]) -> None:
    sha = row.get("sha")
    owner = row.get("repo_owner")
    repo = row.get("repo_name")
    pr_number = _as_int(row.get("pr_number"))
    if not sha or not owner or not repo or pr_number is None:
        return

    cur.execute(
        """
        UPDATE ci_statuses
        SET state = ?, last_updated = ?
        WHERE repo_owner = ? AND repo_name = ? AND sha = ? AND pr_number = ?
        """,
        (row.get("state"), row.get("last_updated"), owner, repo, sha, pr_number),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO ci_statuses (
                sha, repo_owner, repo_name, pr_number, state, last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sha, owner, repo, pr_number, row.get("state"), row.get("last_updated")),
        )


def _upsert_release(cur, owner: str, repo: str, rel: Dict[str, Any]) -> None:
    rel_id = rel.get("id")
    if rel_id is None:
        return

    cur.execute(
        """
        UPDATE releases
        SET tag_name = ?, name = ?, created_at = ?, published_at = ?
        WHERE repo_owner = ? AND repo_name = ? AND id = ?
        """,
        (
            rel.get("tag_name"),
            rel.get("name"),
            rel.get("created_at"),
            rel.get("published_at"),
            owner,
            repo,
            rel_id,
        ),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO releases (
                id, repo_owner, repo_name, tag_name, name, created_at, published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel_id,
                owner,
                repo,
                rel.get("tag_name"),
                rel.get("name"),
                rel.get("created_at"),
                rel.get("published_at"),
            ),
        )


def run_ingest(
    owner: str,
    repo: str,
    days_back: int,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    settings = get_settings()
    now = datetime.utcnow()

    conn = get_db()
    try:
        cur = conn.cursor()
        checkpoint_last_sync = _get_checkpoint_last_sync(cur, owner, repo)
        oldest_existing = _get_oldest_repo_timestamp(cur, owner, repo)
        base_since = now - timedelta(days=days_back)
        needs_backfill = oldest_existing is None or oldest_existing > base_since

        freshness_cutoff = timedelta(minutes=max(0, settings.ingest_freshness_minutes))
        if (
            not force_refresh
            and checkpoint_last_sync is not None
            and now - checkpoint_last_sync < freshness_cutoff
            and not needs_backfill
        ):
            return {
                "skipped": True,
                "since": checkpoint_last_sync.isoformat() + "Z",
                "last_sync_at": checkpoint_last_sync.isoformat() + "Z",
            }

        overlap = timedelta(hours=max(0, settings.ingest_overlap_hours))
        incremental_since = checkpoint_last_sync - overlap if checkpoint_last_sync is not None else base_since
        if force_refresh:
            since = base_since
        else:
            since = _select_since_for_ingest(base_since, incremental_since, oldest_existing)
    finally:
        conn.close()

    print(f"[ingest] Fetching incremental data for {owner}/{repo} since {since.isoformat()}Z")

    session = get_github_session(settings.github_token)

    issues = fetch_issues(session, owner, repo, since)
    metrics_pulls = fetch_pulls_for_metrics(session, owner, repo, since)
    commits = fetch_commits(session, owner, repo, since)
    releases = fetch_releases(session, owner, repo)

    recent_pulls = fetch_pulls(session, owner, repo)
    pr_enriched = enrich_pulls_with_details_reviews_and_ci(session, owner, repo, recent_pulls)
    enriched_pulls = pr_enriched["pulls"]
    pr_reviews = pr_enriched["reviews"]
    ci_statuses = pr_enriched["ci_statuses"]

    conn = get_db()
    try:
        cur = conn.cursor()

        only_issues = [it for it in issues if isinstance(it, dict) and "pull_request" not in it]
        for issue in only_issues:
            _upsert_issue(cur, owner, repo, issue)

        for pr in metrics_pulls:
            if not isinstance(pr, dict):
                continue
            row = _pull_row(owner, repo, pr)
            if row is not None:
                _upsert_pull_request(cur, row)

        for pr in enriched_pulls:
            if not isinstance(pr, dict):
                continue
            row = _pull_row(owner, repo, pr)
            if row is not None:
                _upsert_pull_request(cur, row)

        for commit in commits:
            if isinstance(commit, dict):
                _upsert_commit(cur, owner, repo, commit)

        for review in pr_reviews:
            if isinstance(review, dict):
                _upsert_pr_review(cur, review)

        for row in ci_statuses:
            if isinstance(row, dict):
                _upsert_ci_status(cur, row)

        for rel in releases:
            if isinstance(rel, dict):
                _upsert_release(cur, owner, repo, rel)

        _update_checkpoint(cur, owner, repo, now)

        conn.commit()
    finally:
        conn.close()

    print(
        f"[ingest] Completed ingest for {owner}/{repo} "
        f"(issues={len(only_issues)}, metrics_pulls={len(metrics_pulls)}, "
        f"commits={len(commits)}, reviews={len(pr_reviews)}, "
        f"ci_rows={len(ci_statuses)}, releases={len(releases)})"
    )

    return {
        "skipped": False,
        "since": since.isoformat() + "Z",
        "last_sync_at": now.replace(microsecond=0).isoformat() + "Z",
    }
