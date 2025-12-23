import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import altair as alt

# Make `src` importable
ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from eng_health_copilot.orchestrator import (
    run_full_analysis,
    answer_user_question,
)
from eng_health_copilot.query import get_weekly_metrics_history

# ---------------------------------------------------------
# Page & session state setup
# ---------------------------------------------------------

st.set_page_config(page_title="GitHub PM Copilot", layout="wide")

if "has_run_analysis" not in st.session_state:
    st.session_state["has_run_analysis"] = False
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "last_owner" not in st.session_state:
    st.session_state["last_owner"] = None
if "last_repo" not in st.session_state:
    st.session_state["last_repo"] = None

# ---------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------

st.sidebar.title("Repo Settings")
owner_input = st.sidebar.text_input("Owner", value="rustfs")
repo_input = st.sidebar.text_input("Repo", value="rustfs")
days_back = st.sidebar.number_input(
    "Days back",
    min_value=7,
    max_value=365,
    value=90,
    step=7,
)

if st.sidebar.button("Run analysis"):
    with st.spinner("Analyzing repo activity..."):
        summary = run_full_analysis(owner_input, repo_input, days_back=days_back)

    # Mark that we have fresh data and remember which repo it was for
    st.session_state["has_run_analysis"] = True
    st.session_state["last_owner"] = owner_input
    st.session_state["last_repo"] = repo_input

    # Start a fresh chat for this run, seeded with the summary
    st.session_state["chat_history"] = [
        {"role": "assistant", "content": summary}
    ]

# ---------------------------------------------------------
# Main layout
# ---------------------------------------------------------

st.title("GitHub PM Copilot (Engineering Health)")

if st.session_state["has_run_analysis"] and st.session_state["last_owner"] and st.session_state["last_repo"]:
    st.caption(
        f"Showing metrics for last analyzed repo: "
        f"`{st.session_state['last_owner']}/{st.session_state['last_repo']}`"
    )
else:
    st.caption(
        f"Configure a repo in the sidebar (currently: `{owner_input}/{repo_input}`) "
        "and click **Run analysis**."
    )

# ----------------- Weekly Metrics & Charts -----------------

st.subheader("Weekly Metrics (last few weeks)")

if st.session_state.get("has_run_analysis") and st.session_state["last_owner"] and st.session_state["last_repo"]:
    hist_owner = st.session_state["last_owner"]
    hist_repo = st.session_state["last_repo"]

    history_df = get_weekly_metrics_history(hist_owner, hist_repo)

    if not history_df.empty:
        history_df["week_start"] = pd.to_datetime(history_df["week_start"])
        history_df = history_df.sort_values("week_start")

        # Common x-axis zoom/scroll selection for all charts (only x-axis)
        x_zoom = alt.selection_interval(bind="scales", encodings=["x"])

        # --- PR throughput chart ---
        st.caption("PR throughput (merged PRs per week)")
        throughput_data = history_df[["week_start", "pr_throughput"]]

        throughput_chart = (
            alt.Chart(throughput_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("pr_throughput:Q", title="Merged PRs"),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(throughput_chart, use_container_width=True)

        # --- Lead time chart (p50 & p90) ---
        st.caption("Lead time (days) – p50 and p90")
        lead_data = history_df[
            ["week_start", "pr_lead_time_p50", "pr_lead_time_p90"]
        ].melt(
            "week_start",
            ["pr_lead_time_p50", "pr_lead_time_p90"],
            var_name="metric",
            value_name="value",
        )

        lead_chart = (
            alt.Chart(lead_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("value:Q", title="Lead time (days)"),
                color=alt.Color(
                    "metric:N",
                    title="Metric",
                    scale=alt.Scale(
                        domain=["pr_lead_time_p50", "pr_lead_time_p90"],
                        range=["#1f77b4", "#ff7f0e"],
                    ),
                ),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(lead_chart, use_container_width=True)

        # --- Open bugs + WIP PRs chart ---
        st.caption("Open bugs and WIP PRs")
        bugs_wip_data = history_df[
            ["week_start", "open_bugs_count", "wip_prs"]
        ].melt(
            "week_start",
            ["open_bugs_count", "wip_prs"],
            var_name="metric",
            value_name="value",
        )

        bugs_wip_chart = (
            alt.Chart(bugs_wip_data)
            .mark_line(point=True)
            .encode(
                x=alt.X("week_start:T", title="Week"),
                y=alt.Y("value:Q", title="Count"),
                color=alt.Color(
                    "metric:N",
                    title="Metric",
                    scale=alt.Scale(
                        domain=["open_bugs_count", "wip_prs"],
                        range=["#d62728", "#2ca02c"],
                    ),
                ),
            )
            .properties(height=200)
            .add_params(x_zoom)
        )

        st.altair_chart(bugs_wip_chart, use_container_width=True)

    else:
        st.info("No weekly metrics found yet for the last analyzed repo. Try running an analysis.")
else:
    st.info("Run an analysis from the sidebar to see weekly metrics and charts.")

# ----------------- Chat Interface -----------------

st.subheader("Ask about engineering health")

# Render chat history
for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
prompt = st.chat_input("Ask about repo health, trends, or metrics...")
if prompt:
    # Show user message
    st.session_state["chat_history"].append(
        {"role": "user", "content": prompt}
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate assistant reply based on last analyzed repo
    if st.session_state["has_run_analysis"] and st.session_state["last_owner"] and st.session_state["last_repo"]:
        qa_owner = st.session_state["last_owner"]
        qa_repo = st.session_state["last_repo"]
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = answer_user_question(qa_owner, qa_repo, prompt)
                st.markdown(answer)
        st.session_state["chat_history"].append(
            {"role": "assistant", "content": answer}
        )
    else:
        # No analysis yet for any repo
        fallback = "I don't have any metrics yet. Run an analysis from the sidebar first."
        with st.chat_message("assistant"):
            st.markdown(fallback)
        st.session_state["chat_history"].append(
            {"role": "assistant", "content": fallback}
        )
