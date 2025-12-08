from typing import Optional

from .ingest import run_ingest
from .metrics import compute_latest_week_metrics
from .query import get_last_weekly_metrics
from .agents import generate_weekly_summary, answer_question_with_metrics
from .config import get_settings


def run_full_analysis(owner: str, repo: str, days_back: Optional[int] = None) -> str:
    settings = get_settings()
    lookback = days_back if days_back is not None else settings.default_days_back

    # 1) Ingest fresh data from GitHub → SQLite
    run_ingest(owner, repo, lookback)

    # 2) Compute weekly metrics for last 7 days
    metrics = compute_latest_week_metrics(owner, repo)

    # 3) Generate a human-readable weekly summary
    summary = generate_weekly_summary(metrics)
    return summary


def answer_user_question(owner: str, repo: str, question: str) -> str:
    metrics: Optional[dict] = get_last_weekly_metrics(owner, repo)
    if metrics is None:
        return (
            "I don't have any metrics yet for this repo. "
            "Try running a fresh analysis from the sidebar first."
        )

    return answer_question_with_metrics(question, metrics)
