from typing import Dict, Any


def generate_weekly_summary(metrics: Dict[str, Any]) -> str:
    owner = metrics["repo_owner"]
    repo = metrics["repo_name"]

    throughput = metrics["pr_throughput"]
    p50 = metrics["pr_lead_time_p50"]
    p90 = metrics["pr_lead_time_p90"]
    open_bugs = metrics["open_bugs_count"]
    wip_prs = metrics["wip_prs"]

    lines = [
        f"### Weekly Eng Health Summary for `{owner}/{repo}`",
        "",
        f"- **PR throughput (last 7 days):** {throughput} merged PR(s)",
        f"- **Lead time p50 (days):** {p50:.1f} days" if p50 is not None else "- **Lead time p50 (days):** N/A",
        f"- **Lead time p90 (days):** {p90:.1f} days" if p90 is not None else "- **Lead time p90 (days):** N/A",
        f"- **Open bugs (label contains 'bug'):** {open_bugs}",
        f"- **WIP PRs (currently open):** {wip_prs}",
        "",
        "#### High-level read:",
    ]

    commentary = []
    if throughput == 0:
        commentary.append("• No PRs merged in the last week – shipping is stalled.")
    elif throughput < 3:
        commentary.append("• Low throughput – a small trickle of changes is landing.")
    else:
        commentary.append("• Healthy PR throughput – changes are moving.")

    if open_bugs > 20:
        commentary.append("• Bug backlog is high; consider a bug-fix sprint or triage.")
    elif open_bugs > 0:
        commentary.append("• There are some open bugs; regular triage is important.")
    else:
        commentary.append("• No open bugs detected (at least with 'bug' label).")

    if wip_prs > 10:
        commentary.append("• High WIP PR count – review bottlenecks or too much in progress.")
    elif wip_prs > 0:
        commentary.append("• Some WIP PRs – normal, but keep an eye on aging PRs.")
    else:
        commentary.append("• No open PRs right now.")

    lines.extend(commentary)
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
