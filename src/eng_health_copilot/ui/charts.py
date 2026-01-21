from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from .theme import ACCENT, ACCENT_2

LABELS = {
    "pr_lead_time_p50": "Lead time p50",
    "pr_lead_time_p90": "Lead time p90",
    "open_bugs_count": "Open bugs",
    "wip_prs": "WIP PRs",
}

X_AXIS = alt.Axis(format="%b %d", labelAngle=0, title="Week start")


def _section_title(text: str, accent: bool = False) -> None:
    cls = "section-title accent" if accent else "section-title"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


def render_overview_charts(df: pd.DataFrame) -> None:
    left, right = st.columns([1.1, 1.0])

    with left:
        _section_title("PR throughput", accent=False)
        throughput = df[["week_start", "pr_throughput"]]
        chart = (
            alt.Chart(throughput)
            .mark_line(point=True, color=ACCENT)
            .encode(
                x=alt.X("week_start:T", axis=X_AXIS),
                y=alt.Y("pr_throughput:Q", title="Merged PRs"),
            )
            .properties(height=260, padding={"bottom": 40})
        )
        st.altair_chart(chart, use_container_width=True)

    with right:
        _section_title("Open bugs vs WIP PRs", accent=False)
        bw = df[["week_start", "open_bugs_count", "wip_prs"]].melt(
            "week_start",
            ["open_bugs_count", "wip_prs"],
            var_name="metric",
            value_name="value",
        )
        bw["metric_label"] = bw["metric"].map(LABELS).fillna(bw["metric"])
        chart = (
            alt.Chart(bw)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", axis=X_AXIS),
                y=alt.Y("value:Q", title="Count"),
                color=alt.Color(
                    "metric_label:N",
                    title="",
                    scale=alt.Scale(range=[ACCENT, ACCENT_2]),
                ),
            )
            .properties(height=260, padding={"bottom": 40})
        )
        st.altair_chart(chart, use_container_width=True)


def render_trend_charts(df: pd.DataFrame) -> None:
    zoom = alt.selection_interval(bind="scales", encodings=["x"])

    _section_title("PR throughput (merged PRs per week)", accent=True)
    throughput = df[["week_start", "pr_throughput"]]
    c1 = (
        alt.Chart(throughput)
        .mark_line(point=True, color=ACCENT)
        .encode(
            x=alt.X("week_start:T", axis=X_AXIS),
            y=alt.Y("pr_throughput:Q", title="Merged PRs"),
        )
        .properties(height=260, padding={"bottom": 44})
        .add_params(zoom)
    )
    st.altair_chart(c1, use_container_width=True)

    _section_title("Lead time (p50 vs p90)", accent=True)
    lead = df[["week_start", "pr_lead_time_p50", "pr_lead_time_p90"]].melt(
        "week_start",
        ["pr_lead_time_p50", "pr_lead_time_p90"],
        var_name="metric",
        value_name="value",
    )
    lead["metric_label"] = lead["metric"].map(LABELS).fillna(lead["metric"])
    c2 = (
        alt.Chart(lead)
        .mark_line(point=True)
        .encode(
            x=alt.X("week_start:T", axis=X_AXIS),
            y=alt.Y("value:Q", title="Days"),
            color=alt.Color(
                "metric_label:N",
                title="",
                scale=alt.Scale(range=[ACCENT, ACCENT_2]),
            ),
        )
        .properties(height=260, padding={"bottom": 44})
        .add_params(zoom)
    )
    st.altair_chart(c2, use_container_width=True)

    _section_title("Open bugs vs WIP PRs", accent=True)
    bw = df[["week_start", "open_bugs_count", "wip_prs"]].melt(
        "week_start",
        ["open_bugs_count", "wip_prs"],
        var_name="metric",
        value_name="value",
    )
    bw["metric_label"] = bw["metric"].map(LABELS).fillna(bw["metric"])
    c3 = (
        alt.Chart(bw)
        .mark_line(point=True)
        .encode(
            x=alt.X("week_start:T", axis=X_AXIS),
            y=alt.Y("value:Q", title="Count"),
            color=alt.Color(
                "metric_label:N",
                title="",
                scale=alt.Scale(range=[ACCENT, ACCENT_2]),
            ),
        )
        .properties(height=260, padding={"bottom": 44})
        .add_params(zoom)
    )
    st.altair_chart(c3, use_container_width=True)
