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


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def compute_data_sufficiency(
    metrics: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ctx = context or {}
    weekly_history = ctx.get("weekly_history") or []
    recent_prs = ctx.get("recent_pull_requests") or []

    history_weeks = len(weekly_history)
    recent_pr_count = len(recent_prs)

    # Approximate recent commit volume from history when available.
    recent_commit_count = 0
    for row in weekly_history[-4:]:
        if isinstance(row, dict):
            recent_commit_count += _to_int(row.get("commits_per_week"), 0)
    if recent_commit_count == 0:
        recent_commit_count = _to_int(metrics.get("commits_per_week"), 0)

    is_low = history_weeks < 4 or (recent_pr_count < 3 and recent_commit_count < 10)
    is_medium = history_weeks < 8 or recent_pr_count < 8

    level = "low" if is_low else ("medium" if is_medium else "high")
    return {
        "history_weeks": history_weeks,
        "recent_pr_count": recent_pr_count,
        "recent_commit_count": recent_commit_count,
        "level": level,
    }


def _context_signals(context: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not context:
        return {
            "ci_failures": 0,
            "ci_successes": 0,
            "large_prs": 0,
            "recent_release_count": 0,
        }

    recent_prs = context.get("recent_pull_requests") or []
    ci_rows = context.get("recent_ci_statuses") or []
    releases = context.get("recent_releases") or []

    ci_failures = sum(1 for row in ci_rows if (row.get("state") or "").lower() == "failure")
    ci_successes = sum(1 for row in ci_rows if (row.get("state") or "").lower() == "success")

    large_prs = 0
    for pr in recent_prs:
        adds = _to_int(pr.get("additions"), 0)
        dels = _to_int(pr.get("deletions"), 0)
        if adds + dels >= 500:
            large_prs += 1

    return {
        "ci_failures": ci_failures,
        "ci_successes": ci_successes,
        "large_prs": large_prs,
        "recent_release_count": len(releases),
    }


def _context_bullets(context: Optional[Dict[str, Any]]) -> List[str]:
    """
    Produce a short context readout based on richer context:
      - rough CI failure count
      - large PRs
      - recent releases
    """
    sig = _context_signals(context)
    lines: List[str] = []
    if sig["ci_failures"] > 0:
        lines.append(
            f"CI saw {sig['ci_failures']} failing runs and {sig['ci_successes']} successful ones in recent changes."
        )
    if sig["large_prs"] > 0:
        lines.append(f"There were {sig['large_prs']} relatively large PRs (500+ LOC touched) recently.")
    if sig["recent_release_count"] > 0:
        lines.append(f"{sig['recent_release_count']} releases/tags were published recently.")
    return lines


def _build_recommendations(
    metrics: Dict[str, Any],
    data_sufficiency: Dict[str, Any],
    context: Optional[Dict[str, Any]],
) -> List[str]:
    recommendations: List[str] = []
    sig = _context_signals(context)

    if data_sufficiency.get("level") == "low":
        recommendations.append(
            "Instrument baseline delivery signals first: ensure PR labels, CI statuses, and weekly metrics are consistently captured."
        )
        recommendations.append(
            "Avoid strong trend decisions from a single week; review at least 4-8 weeks before committing to process changes."
        )

    if _to_int(metrics.get("wip_prs"), 0) > 20 or _to_int(metrics.get("aging_prs_7d_plus"), 0) > 3:
        recommendations.append("Reduce active WIP and clear aging PRs before taking on new parallel work.")
    if metrics.get("pr_lead_time_p90") is not None and float(metrics.get("pr_lead_time_p90")) > 7:
        recommendations.append("Break large changes into smaller PRs and enforce review SLAs to reduce long-tail lead time.")
    if _to_int(metrics.get("net_bug_delta"), 0) > 0:
        recommendations.append("Run a weekly bug-triage with explicit owners until net bug delta returns to neutral or negative.")
    if sig["ci_failures"] > max(2, sig["ci_successes"] // 2):
        recommendations.append("Prioritize CI stabilization to reduce rework and review churn.")
    if sig["large_prs"] > 0:
        recommendations.append("Set a soft PR-size guideline to improve review speed and merge predictability.")

    # Keep the section actionable even in quiet periods.
    if len(recommendations) < 3:
        recommendations.append("Preserve current cadence with weekly metrics review and anomaly follow-up.")
    if len(recommendations) < 3:
        recommendations.append("Track one bottleneck metric per week and assign a concrete owner for remediation.")

    # De-duplicate while preserving order.
    seen = set()
    deduped: List[str] = []
    for rec in recommendations:
        if rec not in seen:
            deduped.append(rec)
            seen.add(rec)
    return deduped[:5]


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
    llm_context = dict(context or {})
    llm_context["data_sufficiency"] = compute_data_sufficiency(metrics, llm_context)

    llm_text = generate_weekly_summary_llm(metrics, anomalies, llm_context)
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
    suff = llm_context.get("data_sufficiency", {"level": "medium"})

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

    if suff.get("level") == "low":
        bullets.insert(
            0,
            "Data confidence is low this week due to limited recent history and activity; treat trend claims as tentative.",
        )
    elif suff.get("level") == "medium":
        bullets.insert(0, "Data confidence is moderate; validate large conclusions with a few more weeks of data.")

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

    summary += "### Additional context and recommendations\n"
    context_lines = _context_bullets(llm_context)
    if context_lines:
        for line in context_lines:
            summary += f"- {line}\n"
    else:
        summary += "- Context is limited this week; use this summary as directional, not definitive.\n"

    if suff.get("level") == "low":
        summary += "- Confidence note: low data sufficiency; prioritize improving data coverage before major process changes.\n"

    for rec in _build_recommendations(metrics, suff, llm_context):
        summary += f"- {rec}\n"
    summary += "\n"

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
