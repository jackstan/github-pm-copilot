from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


GITHUB_API_BASE = "https://api.github.com"


def get_github_session(token: Optional[str]) -> requests.Session:
    session = requests.Session()
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def _paginated_get(session: requests.Session, url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            items.extend(data)
        else:
            items.extend(data.get("items", []))

        link = resp.headers.get("Link", "")
        next_url = None
        if link:
            parts = link.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1 : part.find(">")]
                    break
        if next_url:
            url = next_url
            params = {}
        else:
            url = None
    return items


def fetch_issues(session: requests.Session, owner: str, repo: str, since) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    params = {
        "state": "all",
        "since": since.isoformat() + "Z",
        "per_page": 100,
    }
    # This endpoint returns both issues and PRs; we'll filter PRs out in ingest
    return _paginated_get(session, url, params)


def fetch_commits(session: requests.Session, owner: str, repo: str, since) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
    params = {
        "since": since.isoformat() + "Z",
        "per_page": 100,
    }
    return _paginated_get(session, url, params)


def fetch_releases(session: requests.Session, owner: str, repo: str) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases"
    params = {
        "per_page": 100,
    }
    return _paginated_get(session, url, params)


def fetch_pulls_for_metrics(
    session: requests.Session, owner: str, repo: str, since: datetime
) -> List[Dict[str, Any]]:
    """
    Fetch PRs for metrics computation.

    Uses pagination and stops once PRs are older than `since` based on created_at
    (sorted by created desc). This can fetch many PRs, but only within the
    desired lookback window.

    We treat `since` as naive UTC, and convert GitHub timestamps to naive UTC
    before comparing.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
    params: Dict[str, Any] = {
        "state": "all",
        "per_page": 100,
        "sort": "created",
        "direction": "desc",
    }

    # Ensure `since` is naive UTC (which datetime.utcnow() already is)
    since_naive_utc = since  # datetime.utcnow() gives naive UTC

    all_pulls: List[Dict[str, Any]] = []

    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            break

        stop = False
        for pr in data:
            created_at = pr.get("created_at")
            if created_at:
                try:
                    # GitHub timestamps are ISO 8601 with Z
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    # Convert to naive UTC to match since_naive_utc
                    created_dt = created_dt.astimezone(timezone.utc).replace(tzinfo=None)
                except ValueError:
                    created_dt = None
            else:
                created_dt = None

            # If this PR is older than our lookback window, we can stop (list is sorted desc)
            if created_dt is not None and created_dt < since_naive_utc:
                stop = True
                break

            all_pulls.append(pr)

        if stop:
            break

        link = resp.headers.get("Link", "")
        next_url = None
        if link:
            parts = link.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1 : part.find(">")]
                    break

        if next_url:
            url = next_url
            params = {}
        else:
            break

    return all_pulls


def fetch_pulls(session: requests.Session, owner: str, repo: str) -> List[Dict[str, Any]]:
    """
    Fetch only the most recent page of PRs (up to 50).
    This is used for enrichment (reviews/CI/size) so we don't blow up API calls.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
    params = {
        "state": "all",
        "per_page": 50,  # latest 50 PRs
    }
    resp = session.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def enrich_pulls_with_details_reviews_and_ci(
    session: requests.Session, owner: str, repo: str, pulls: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    For each PR:
      - Fetch detailed PR (size, labels, head_sha)
      - Fetch reviews
      - Fetch CI status for head commit

    Returns a dict with:
      {
        "pulls": [enriched_pr_dict, ...],
        "reviews": [review_row, ...],
        "ci_statuses": [ci_row, ...],
      }

    We cap the number of enriched PRs to keep API usage reasonable.
    """
    MAX_ENRICHED_PRS = 30
    pulls = pulls[:MAX_ENRICHED_PRS]

    enriched_pulls: List[Dict[str, Any]] = []
    all_reviews: List[Dict[str, Any]] = []
    all_ci_rows: List[Dict[str, Any]] = []

    for pr in pulls:
        number = pr.get("number")
        if number is None:
            continue

        # 1) Detailed PR
        pr_detail_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{number}"
        pr_resp = session.get(pr_detail_url)
        pr_resp.raise_for_status()
        pr_detail = pr_resp.json()

        # Merge base fields with details
        merged = {**pr, **pr_detail}

        # Extract labels as comma-separated
        labels = merged.get("labels", [])
        if isinstance(labels, list):
            label_names = [lb.get("name", "") for lb in labels if isinstance(lb, dict)]
            merged["labels_flat"] = ",".join(label_names)
        else:
            merged["labels_flat"] = ""

        # Size
        merged["additions"] = merged.get("additions")
        merged["deletions"] = merged.get("deletions")
        merged["changed_files"] = merged.get("changed_files")

        # Head SHA (for CI)
        head = merged.get("head") or {}
        merged["head_sha"] = head.get("sha")

        enriched_pulls.append(merged)

        # 2) Reviews for this PR
        reviews_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{number}/reviews"
        reviews_resp = session.get(reviews_url)
        reviews_resp.raise_for_status()
        reviews_data = reviews_resp.json()
        for rv in reviews_data:
            all_reviews.append(
                {
                    "id": rv.get("id"),
                    "repo_owner": owner,
                    "repo_name": repo,
                    "pr_number": number,
                    "user_login": (rv.get("user") or {}).get("login"),
                    "state": rv.get("state"),
                    "submitted_at": rv.get("submitted_at"),
                }
            )

        # 3) CI status for head commit (if we have sha)
        head_sha = merged.get("head_sha")
        if head_sha:
            status_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{head_sha}/status"
            status_resp = session.get(status_url)
            status_resp.raise_for_status()
            status_data = status_resp.json()
            state = status_data.get("state")
            last_updated = status_data.get("updated_at")
            all_ci_rows.append(
                {
                    "sha": head_sha,
                    "repo_owner": owner,
                    "repo_name": repo,
                    "pr_number": number,
                    "state": state,
                    "last_updated": last_updated,
                }
            )

    return {
        "pulls": enriched_pulls,
        "reviews": all_reviews,
        "ci_statuses": all_ci_rows,
    }
