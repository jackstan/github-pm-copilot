from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pandas as pd
import streamlit as st

from .charts import render_overview_charts, render_trend_charts
from .components import render_ai_summary, render_kpi_row


# -----------------------------
# Data helpers
# -----------------------------
def _sorted_weekly_df(history_df: pd.DataFrame) -> pd.DataFrame:
    df = history_df.copy()
    df["week_start"] = pd.to_datetime(df["week_start"])
    return df.sort_values("week_start")


# -----------------------------
# Overview tab
# -----------------------------
def render_overview(
    has_run: bool,
    owner: Optional[str],
    repo: Optional[str],
    history_df: Optional[pd.DataFrame],
    summary: Optional[str],
    on_go_to_ask: Callable[[], None],
) -> None:
    if not (has_run and owner and repo):
        st.markdown(
            """
<div class="empty-state">
  <div class="empty-title">Start with a weekly health scan</div>
  <div class="empty-subtitle">
    Pick a repo and timeframe in the sidebar, then run analysis to generate your report.
  </div>
  <div class="empty-steps">
    <div class="empty-step">
      <span>Step 1</span>
      <strong>Choose owner and repo</strong>
    </div>
    <div class="empty-step">
      <span>Step 2</span>
      <strong>Set the lookback window</strong>
    </div>
    <div class="empty-step">
      <span>Step 3</span>
      <strong>Run analysis to generate insights</strong>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        return

    st.subheader("This week", anchor=False)

    if isinstance(history_df, pd.DataFrame) and not history_df.empty:
        df = _sorted_weekly_df(history_df)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else None

        def _pct_delta(curr: float, prior: float) -> Optional[float]:
            if prior == 0:
                return None
            return ((curr - prior) / prior) * 100

        if prev is not None:
            merged_delta = _pct_delta(latest["pr_throughput"], prev["pr_throughput"])
            p50_delta = _pct_delta(latest["pr_lead_time_p50"], prev["pr_lead_time_p50"])
            p90_delta = _pct_delta(latest["pr_lead_time_p90"], prev["pr_lead_time_p90"])
            bugs_delta = _pct_delta(latest["open_bugs_count"], prev["open_bugs_count"])
        else:
            merged_delta = None
            p50_delta = None
            p90_delta = None
            bugs_delta = None

        render_kpi_row(
            merged_prs=int(latest["pr_throughput"]),
            merged_delta=merged_delta,
            p50_days=float(latest["pr_lead_time_p50"]),
            p50_delta=p50_delta,
            p90_days=float(latest["pr_lead_time_p90"]),
            p90_delta=p90_delta,
            open_bugs=int(latest["open_bugs_count"]),
            bugs_delta=bugs_delta,
        )

        st.divider()
        render_overview_charts(df)

    st.divider()

    left, right = st.columns([2.6, 1.2])
    with left:
        st.subheader("AI weekly report", anchor=False)
        render_ai_summary(summary or "")
    with right:
        st.caption("Want to dig in?")
        if st.button("Go to Ask →", use_container_width=True):
            on_go_to_ask()
        st.caption("Ask about spikes, bottlenecks, or what changed week-over-week.")


# -----------------------------
# Trends tab
# -----------------------------
def render_trends(history_df: Optional[pd.DataFrame]) -> None:
    st.subheader("Weekly metrics", anchor=False)

    if not (isinstance(history_df, pd.DataFrame) and not history_df.empty):
        st.info("Run an analysis to see weekly metrics and charts.")
        return

    df = _sorted_weekly_df(history_df)
    st.caption("Zoom/pan enabled here (drag to zoom, scroll to pan).")
    render_trend_charts(df)

    st.divider()
    with st.expander("Raw weekly data"):
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="weekly_metrics.csv",
            mime="text/csv",
        )


# -----------------------------
# Ask tab
# -----------------------------
def render_ask(
    has_run: bool,
    owner: Optional[str],
    repo: Optional[str],
    summary: Optional[str],
    chat_history: List[Dict[str, str]],
    answer_fn: Callable[[str], str],
    disabled: bool = False,
) -> None:
    st.subheader("Ask about engineering health", anchor=False)

    with st.expander("Show weekly summary", expanded=False):
        if summary:
            render_ai_summary(summary)
        else:
            st.caption("Run an analysis to generate a weekly summary.")

    st.markdown('<div class="ask-wrap">', unsafe_allow_html=True)
    st.caption("Try one:")
    suggestions = [
        "Who were the top contributors this week?",
        "Which PRs saw the longest review times?",
        "Did bug backlog move up or down?",
        "What is the single biggest bottleneck right now?",
    ]
    cols = st.columns(len(suggestions))
    for i, s in enumerate(suggestions):
        if cols[i].button(s, use_container_width=True, disabled=disabled):
            chat_history.append({"role": "user", "content": s})
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if disabled:
        st.info("Analysis is running… please wait.")
        return

    st.markdown(
        """
<div class="ask-input-header">Ask a question</div>
<div class="ask-input-sub">Type a question about trends, throughput, or bottlenecks.</div>
""",
        unsafe_allow_html=True,
    )
    prompt = st.chat_input("Ask about repo health, trends, or metrics…")
    if prompt:
        chat_history.append({"role": "user", "content": prompt})

    if chat_history and chat_history[-1]["role"] == "user":
        if has_run and owner and repo:
            user_q = chat_history[-1]["content"]
            with st.spinner("Thinking…"):
                answer = answer_fn(user_q)
            chat_history.append({"role": "assistant", "content": answer})
        else:
            fallback = "I don't have any metrics yet. Run an analysis first."
            chat_history.append({"role": "assistant", "content": fallback})

    st.divider()

    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
