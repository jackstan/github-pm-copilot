from typing import Dict, Any, List, Optional

from .llm_client import generate_weekly_summary_llm, answer_question_llm


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    try:
        if isinstance(value, (float, int)):
            return f"{value:.{digits}f}" if isinstance(value, float) else str(int(value))
        return str(value)
    except Exception:
        return str(value)


def _summarize_context(context: Optional[Dict[str, Any]]) -> str:
    """
    Produce a short, optional add-on summary based on richer context:
      - rough CI failure count
      - large PRs
      - recent releases
    """
    if not context:
        return ""

    recent_prs = context.get("recent_pull_requests") or []
    ci_rows = context.get("recent_ci_statuses") or []
    releases = context.get("recent_releases") or []

    ci_failures = sum(1 for row in ci_rows if (row.get("state") or "").lower() == "failure")
    ci_successes = sum(1 for row in ci_rows if (row.get("state") or "").lower() == "success")

    large_prs = 0
    for pr in recent_prs:
        adds = pr.get("additions") or 0
        dels = pr.get("deletions") or 0
        try:
            total = int(adds) + int(dels)
        except Exception:
            total = 0
        if total >= 500:
            large_prs += 1

    recent_release_count = len(releases)

    lines: List[str] = []
    if ci_failures > 0:
        lines.append(
            f"- CI saw {ci_failures} failing runs and {ci_successes} successful ones in recent changes."
        )
    if large_prs > 0:
        lines.append(f"- There were {large_prs} relatively large PRs (500+ LOC touched) recently.")
    if recent_release_count > 0:
        lines.append(f"- {recent_release_count} releases/tags were published recently.")

    if not lines:
        return ""

    return "#### Additional context\n" + "\n".join(lines) + "\n\n"


def generate_weekly_summary(
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Weekly summary:
      - First try OpenAI with rich context
      - If no API key / error, fall back to deterministic summary
    """
    llm_text = generate_weekly_summary_llm(metrics, anomalies, context or {})
    if llm_text:
        return llm_text

    # -------- Fallback deterministic summary --------
    throughput = metrics.get("pr_throughput", 0)
    p50 = metrics.get("pr_lead_time_p50")
    p90 = metrics.get("pr_lead_time_p90")
    open_bugs = metrics.get("open_bugs_count", 0)
    wip_prs = metrics.get("wip_prs", 0)
    aging = metrics.get("aging_prs_7d_plus", 0)
    net_bug_delta = metrics.get("net_bug_delta", 0)

    commits_per_week = metrics.get("commits_per_week", 0)
    active_contrib = metrics.get("active_contributors_per_week", 0)

    summary = "### Weekly Engineering Summary\n\n"

    summary += (
        f"- **Throughput:** {throughput} PRs merged this week\n"
        f"- **Lead time (p50):** {_fmt(p50)} days\n"
        f"- **Lead time (p90):** {_fmt(p90)} days\n"
        f"- **Open bugs:** {open_bugs}\n"
        f"- **WIP PRs:** {wip_prs} (aging 7d+: {aging})\n"
        f"- **Net bug delta:** {net_bug_delta} (positive = backlog growing)\n"
        f"- **Commits:** {commits_per_week} this week from {active_contrib} active contributors\n\n"
    )

    bullets: List[str] = []

    if throughput < 3:
        bullets.append("Throughput is on the low side – only a small number of PRs merged.")
    else:
        bullets.append("Throughput looks healthy – a steady stream of PRs merged.")

    if p90 is not None and p90 > 7:
        bullets.append("Lead time p90 is high (over a week), indicating long-tail PRs.")
    elif p90 is not None:
        bullets.append("Lead time p90 is reasonable for most PRs.")

    if open_bugs == 0:
        bullets.append("No open bugs with a 'bug' label at the moment.")
    elif net_bug_delta > 0:
        bullets.append("Bug backlog grew this week (more bugs opened than closed).")
    elif net_bug_delta < 0:
        bullets.append("Bug backlog shrank this week (more bugs closed than opened).")

    if wip_prs > 20:
        bullets.append("WIP PR count is high – risk of context-switching and stalled reviews.")
    elif wip_prs > 0:
        bullets.append("WIP PR count looks manageable.")

    if aging > 0:
        bullets.append(f"{aging} PR(s) have been open for more than 7 days.")

    summary += "### High-level read\n"
    if bullets:
        for b in bullets:
            summary += f"- {b}\n"
    else:
        summary += "- No major signals stand out in the current metrics.\n"
    summary += "\n"

    if anomalies:
        summary += "### Notable anomalies vs recent history\n"
        for a in anomalies:
            msg = a.get("message") or ""
            metric = a.get("metric", "metric")
            value = a.get("value")
            summary += f"- **{metric}**: {msg} (value={_fmt(value)})\n"
        summary += "\n"

    summary += _summarize_context(context)

    return summary


def answer_question_with_metrics(
    question: str,
    metrics: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Q&A:
      - First try OpenAI
      - If not available, use rule-based responses
    """
    llm_text = answer_question_llm(question, metrics, anomalies, context or {})
    if llm_text:
        return llm_text

    # -------- Fallback deterministic Q&A --------
    q_lower = question.lower()

    if "throughput" in q_lower or "velocity" in q_lower:
        thr = metrics.get("pr_throughput", 0)
        commits = metrics.get("commits_per_week", 0)
        contrib = metrics.get("active_contributors_per_week", 0)
        return (
            f"Throughput this week is {thr} merged PRs. "
            f"That came from {commits} commits across {contrib} active contributors. "
            "Look at throughput trends over multiple weeks to see if this is a one-off or part of a pattern."
        )

    if "lead time" in q_lower or "cycle time" in q_lower:
        p50 = metrics.get("pr_lead_time_p50")
        p90 = metrics.get("pr_lead_time_p90")
        extra = ""
        lead_anoms = [a for a in anomalies if a.get("metric") == "pr_lead_time_p90"]
        if lead_anoms:
            extra = " There is also a recent anomaly flag on p90, indicating an unusual jump."
        return (
            f"Current lead time is about {_fmt(p50)} days at p50 and {_fmt(p90)} days at p90."
            f"{extra} To understand *why*, you’d look at PR size, review cycles, and CI health."
        )

    if "bug" in q_lower:
        open_bugs = metrics.get("open_bugs_count", 0)
        net_bug_delta = metrics.get("net_bug_delta", 0)
        msg = (
            f"There are currently {open_bugs} open bugs. "
            f"Net bug delta this week is {net_bug_delta} "
            "(positive means the backlog is growing)."
        )
        bug_anoms = [a for a in anomalies if a.get("metric") in ("open_bugs_count", "net_bug_delta")]
        if bug_anoms:
            msg += " Recent anomalies suggest bug-related metrics are behaving unusually."
        return msg

    if "wip" in q_lower or "work in progress" in q_lower or "aging" in q_lower:
        wip = metrics.get("wip_prs", 0)
        aging = metrics.get("aging_prs_7d_plus", 0)
        return (
            f"There are {wip} PRs currently in progress, with {aging} open for more than 7 days. "
            "High WIP and aging PRs usually point to review bottlenecks or overly large changes."
        )

    base = (
        f"Here's the latest snapshot for this repo:\n"
        f"- Throughput: {metrics.get('pr_throughput', 0)} PRs merged\n"
        f"- Lead time (p50/p90): {_fmt(metrics.get('pr_lead_time_p50'))} / "
        f"{_fmt(metrics.get('pr_lead_time_p90'))} days\n"
        f"- Open bugs: {metrics.get('open_bugs_count', 0)} (net bug delta {metrics.get('net_bug_delta', 0)})\n"
        f"- WIP PRs: {metrics.get('wip_prs', 0)} (aging 7d+: {metrics.get('aging_prs_7d_plus', 0)})\n"
    )

    if anomalies:
        base += "\nRecent anomalies:\n"
        for a in anomalies:
            msg = a.get("message") or ""
            metric = a.get("metric", "metric")
            base += f"- {metric}: {msg}\n"

    if context:
        recent_prs = context.get("recent_pull_requests") or []
        ci_rows = context.get("recent_ci_statuses") or []
        base += (
            f"\nI also have context on about {len(recent_prs)} recent PRs and "
            f"{len(ci_rows)} recent CI status entries, which can help explain trends "
            "in lead time, WIP, and quality."
        )

    return base
