from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

GITHUB_API_BASE = "https://api.github.com"


def get_github_session(token: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    headers = {
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def _paginated_get(
    session: requests.Session,
    url: str,
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        results.extend(data)

        link = resp.headers.get("Link", "")
        next_url = None
        if link:
            parts = link.split(",")
            for part in parts:
                if 'rel="next"' in part:
                    next_url = part[part.find("<") + 1 : part.find(">")]
                    break
        url = next_url
        params = {}
    return results


def fetch_issues(
    session: requests.Session,
    owner: str,
    repo: str,
    since: datetime,
) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    params = {
        "state": "all",
        "since": since.isoformat() + "Z",
        "per_page": 100,
    }
    raw = _paginated_get(session, url, params)
    issues = [item for item in raw if "pull_request" not in item]
    return issues


def fetch_pulls(
    session: requests.Session,
    owner: str,
    repo: str,
) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
    params = {
        "state": "all",
        "per_page": 100,
        "sort": "updated",
        "direction": "desc",
    }
    raw = _paginated_get(session, url, params)
    return raw


def fetch_commits(
    session: requests.Session,
    owner: str,
    repo: str,
    since: datetime,
) -> List[Dict[str, Any]]:
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
    params = {
        "since": since.isoformat() + "Z",
        "per_page": 100,
    }
    raw = _paginated_get(session, url, params)
    return raw
