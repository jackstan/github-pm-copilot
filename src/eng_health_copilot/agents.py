from typing import Dict, Any, List


def _pretty_metric_name(metric_key: str) -> str:
    mapping = {
        "pr_throughput": "PR throughput",
        "pr_lead_time_p50": "Lead time p50",
        "pr_lead_time_p90": "Lead time p90",
        "open_bugs_count": "Open bugs",
        "wip_prs": "WIP PRs",
    }
    return mapping.get(metric_key, metric_key)


def generate_weekly_summary(metrics: Dict[str, Any], anomalies: List[Dict[str, Any]]) -> str:
    """
    Core weekly metrics + simple commentary + an optional anomalies section.
    Anomalies are additive, not the main focus.
    """
    owner = metrics.get("repo_owner", "")
    repo = metrics.get("repo_name", "")

    throughput = metrics.get("pr_throughput")
    p50 = metrics.get("pr_lead_time_p50")
    p90 = metrics.get("pr_lead_time_p90")
    open_bugs = metrics.get("open_bugs_count")
    wip_prs = metrics.get("wip_prs")

    # --- Core metrics section ---
    lines: List[str] = []

    title = f"### Weekly Eng Health Summary for `{owner}/{repo}`" if owner and repo else "### Weekly Eng Health Summary"
    lines.append(title)
    lines.append("")
    lines.append(f"- **PR throughput (last week):** {throughput} merged PR(s)")
    lines.append(f"- **Lead time p50 (days):** {p50:.1f} days" if p50 is not None else "- **Lead time p50 (days):** N/A")
    lines.append(f"- **Lead time p90 (days):** {p90:.1f} days" if p90 is not None else "- **Lead time p90 (days):** N/A")
    lines.append(f"- **Open bugs (label contains 'bug'):** {open_bugs}")
    lines.append(f"- **WIP PRs (currently open):** {wip_prs}")
    lines.append("")
    lines.append("#### High-level read:")

    # --- Rule-based commentary (the stuff you liked) ---
    commentary: List[str] = []

    # Throughput commentary
    if throughput is None or throughput == 0:
        commentary.append("• No PRs merged in the last week – shipping is effectively paused.")
    elif throughput < 3:
        commentary.append("• Low throughput – only a small number of changes landed.")
    elif throughput < 10:
        commentary.append("• Moderate throughput – a steady stream of changes is landing.")
    else:
        commentary.append("• High throughput – the team is shipping a lot of changes.")

    # Bug backlog commentary
    if open_bugs is None:
        pass
    elif open_bugs == 0:
        commentary.append("• No open bugs detected (with a 'bug' label).")
    elif open_bugs <= 10:
        commentary.append("• Bug backlog is manageable but worth watching.")
    else:
        commentary.append("• Bug backlog is on the high side; consider targeted bug-fix time or triage.")

    # WIP commentary
    if wip_prs is None:
        pass
    elif wip_prs == 0:
        commentary.append("• No open PRs right now – the queue is clear.")
    elif wip_prs <= 5:
        commentary.append("• WIP PR count looks reasonable.")
    elif wip_prs <= 15:
        commentary.append("• WIP PRs are elevated; there may be some review or merge friction.")
    else:
        commentary.append("• WIP PRs are very high – likely review bottlenecks or too much work in progress.")

    if not commentary:
        commentary.append("• Metrics are available, but there isn't a strong signal either way this week.")

    lines.extend(commentary)

    # --- Anomalies as an extra section, if any ---
    if anomalies:
        lines.append("")
        lines.append("#### Notable anomalies vs recent history")
        for a in anomalies:
            metric_name = _pretty_metric_name(a.get("metric", ""))
            z = a.get("z_score")
            direction = "higher than usual" if a.get("type") == "high" else "lower than usual"
            value = a.get("value")
            mean = a.get("mean")

            if z is not None and value is not None and mean is not None:
                lines.append(
                    f"- **{metric_name}** is {direction} this week "
                    f"({value:.2f} vs ~{mean:.2f}, z={z:.2f})."
                )
            else:
                # Fallback to whatever message was provided
                msg = a.get("message", "")
                if msg:
                    lines.append(f"- {msg}")
    else:
        lines.append("")
        lines.append("_No unusual patterns vs the last few weeks._")

    return "\n".join(lines)

def answer_question_with_metrics(
    question: str,
    metrics: Dict[str, Any],
) -> str:
    q = question.lower()
    parts = []

    if "lead time" in q or "cycle time" in q:
        parts.append(
            f"- p50 lead time: {metrics['pr_lead_time_p50']:.1f} days"
            if metrics["pr_lead_time_p50"] is not None
            else "- p50 lead time: N/A"
        )
        parts.append(
            f"- p90 lead time: {metrics['pr_lead_time_p90']:.1f} days"
            if metrics["pr_lead_time_p90"] is not None
            else "- p90 lead time: N/A"
        )

    if "throughput" in q or "merged" in q:
        parts.append(
            f"- PR throughput (last 7 days): {metrics['pr_throughput']} merged PR(s)"
        )

    if "bug" in q:
        parts.append(
            f"- Open bugs (label contains 'bug'): {metrics['open_bugs_count']}"
        )

    if "wip" in q or "open pr" in q:
        parts.append(
            f"- WIP PRs (currently open): {metrics['wip_prs']}"
        )

    if not parts:
        # Default: show full summary
        return (
            "Here's the latest snapshot, then we can refine your question:\n\n"
            + generate_weekly_summary(metrics)
        )

    return "Here's what I see related to your question:\n\n" + "\n".join(parts)
