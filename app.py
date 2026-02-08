import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Make `src` importable
ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from eng_health_copilot.orchestrator import run_full_analysis, answer_user_question
from eng_health_copilot.query import get_weekly_metrics_history
from eng_health_copilot import ui

# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------
st.set_page_config(page_title="GitHub PM Copilot", layout="wide")

# ---------------------------------------------------------
# Debug theme indicator (dev-only)
# ---------------------------------------------------------
if os.getenv("DEBUG_THEME") == "1":
    st.caption("Theme policy: light")
    components.html(
        """
<div id="theme-indicator" style="font: 13px/1.4 system-ui; color: #0f172a;">
  prefers-color-scheme: …
</div>
<script>
  const el = document.getElementById("theme-indicator");
  const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  el.textContent = "prefers-color-scheme: " + (isDark ? "dark" : "light");
</script>
""",
        height=24,
    )

# ---------------------------------------------------------
# Session state init
# ---------------------------------------------------------
DEFAULT_OWNER = "rustfs"
DEFAULT_REPO = "rustfs"
DEFAULT_DAYS = 90

if "has_run_analysis" not in st.session_state:
    st.session_state["has_run_analysis"] = False
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "last_owner" not in st.session_state:
    st.session_state["last_owner"] = None
if "last_repo" not in st.session_state:
    st.session_state["last_repo"] = None
if "last_days_back" not in st.session_state:
    st.session_state["last_days_back"] = DEFAULT_DAYS
if "last_run_at" not in st.session_state:
    st.session_state["last_run_at"] = None

if "weekly_summary" not in st.session_state:
    st.session_state["weekly_summary"] = ""
if "weekly_history_df" not in st.session_state:
    st.session_state["weekly_history_df"] = pd.DataFrame()

# UI state
if "nav_view" not in st.session_state:
    st.session_state["nav_view"] = "Overview"
if "is_running" not in st.session_state:
    st.session_state["is_running"] = False
if "run_requested" not in st.session_state:
    st.session_state["run_requested"] = False

# ---------------------------------------------------------
# CSS
# ---------------------------------------------------------
ui.inject_css()

# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------
st.sidebar.title("Repo Settings")

sidebar_disabled = st.session_state["is_running"] or st.session_state["run_requested"]

owner_input = st.sidebar.text_input(
    "Owner",
    value=st.session_state["last_owner"] or DEFAULT_OWNER,
    disabled=sidebar_disabled,
)
repo_input = st.sidebar.text_input(
    "Repo",
    value=st.session_state["last_repo"] or DEFAULT_REPO,
    disabled=sidebar_disabled,
)
days_back = st.sidebar.number_input(
    "Days back",
    min_value=7,
    max_value=365,
    value=int(st.session_state["last_days_back"] or DEFAULT_DAYS),
    step=7,
    disabled=sidebar_disabled,
)
force_refresh = st.sidebar.checkbox(
    "Force refresh from GitHub",
    value=False,
    disabled=sidebar_disabled,
)

st.sidebar.caption("Tip: Click **Run analysis** to generate the AI report + charts. Initial load may be slow for large repos.")

run_clicked = st.sidebar.button(
    "Run analysis",
    type="primary",
    disabled=sidebar_disabled,
)

# If clicked: set flags BEFORE nav widget exists (safe)
if run_clicked and not st.session_state["is_running"]:
    st.session_state["run_requested"] = True
    st.session_state["nav_view"] = "Overview"
    st.rerun()

# ---------------------------------------------------------
# Header
# ---------------------------------------------------------
ui.render_header(
    owner_input=owner_input,
    repo_input=repo_input,
    last_owner=st.session_state["last_owner"],
    last_repo=st.session_state["last_repo"],
    last_run_at=st.session_state["last_run_at"],
    last_days_back=st.session_state["last_days_back"],
)

# ---------------------------------------------------------
# NAV
# Key trick:
# - While running: do NOT instantiate the radio widget at all.
#   (Otherwise any later attempt to change nav_view is illegal.)
# ---------------------------------------------------------
if st.session_state["is_running"] or st.session_state["run_requested"]:
    # Render a "locked" nav that looks like tabs but isn't interactive.
    # (Simple markdown; styling already comes from your global CSS background.)
    st.markdown(
        f"""
<div style="display:flex; gap:12px; width:100%; margin-top:6px;">
  <div style="flex:1; padding:12px 14px; border-radius:16px;
              border:1px solid rgba(14,165,164,0.35);
              background:rgba(14,165,164,0.12);
              text-align:center; font-weight:600; color:{ui.ACCENT};">
    📌 Overview
  </div>
  <div style="flex:1; padding:12px 14px; border-radius:16px;
              border:1px solid rgba(15,23,42,0.10);
              background:rgba(255,255,255,0.7);
              text-align:center; font-weight:600; color:rgba(71,85,105,0.8);">
    📈 Trends
  </div>
  <div style="flex:1; padding:12px 14px; border-radius:16px;
              border:1px solid rgba(15,23,42,0.10);
              background:rgba(255,255,255,0.7);
              text-align:center; font-weight:600; color:rgba(71,85,105,0.8);">
    💬 Ask
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    view = "Overview"
else:
    ui.render_nav(
        active_view=st.session_state["nav_view"],
        disabled=False,
    )
    view = st.session_state["nav_view"]

# ---------------------------------------------------------
# Analysis runner (NO nav_view writes inside)
# ---------------------------------------------------------
def _perform_analysis() -> None:
    st.session_state["is_running"] = True
    st.session_state["run_requested"] = False
    analysis_succeeded = False

    try:
        with st.status("Running analysis…", expanded=True) as status:
            progress_slot = st.empty()

            def _render_progress(pct: int) -> None:
                pct = max(0, min(100, pct))
                progress_slot.markdown(
                    f"""
<div class="progress-track">
  <div class="progress-fill" style="width: {pct}%"></div>
</div>
""",
                    unsafe_allow_html=True,
                )

            def _on_status(label: str, pct: float) -> None:
                status.update(label=label, state="running")
                _render_progress(int(pct * 100))

            summary = run_full_analysis(
                owner_input,
                repo_input,
                days_back=int(days_back),
                force_refresh=bool(force_refresh),
                on_status=_on_status,
            )

            status.update(label="Loading weekly history…", state="running")
            _render_progress(95)
            history_df = get_weekly_metrics_history(owner_input, repo_input)

            st.session_state["has_run_analysis"] = True
            st.session_state["last_owner"] = owner_input
            st.session_state["last_repo"] = repo_input
            st.session_state["last_days_back"] = int(days_back)
            st.session_state["last_run_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            st.session_state["weekly_summary"] = summary
            st.session_state["weekly_history_df"] = history_df

            st.session_state["chat_history"] = []

            _render_progress(100)
            status.update(label="Done.", state="complete")
            analysis_succeeded = True

    except Exception as e:
        st.error(f"Analysis failed: {e}")

    finally:
        st.session_state["is_running"] = False

    if analysis_succeeded:
        st.rerun()

# Kick off analysis
if st.session_state["run_requested"] and not st.session_state["is_running"]:
    _perform_analysis()

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
has_run = st.session_state["has_run_analysis"]
last_owner = st.session_state["last_owner"]
last_repo = st.session_state["last_repo"]
summary = st.session_state["weekly_summary"]
history_df = st.session_state["weekly_history_df"]

def go_to_ask() -> None:
    # Safe because it triggers a new rerun and is set BEFORE next nav widget instantiation
    if st.session_state["is_running"]:
        return
    st.session_state["nav_view"] = "Ask"
    st.rerun()

def answer_fn(question: str) -> str:
    if not (last_owner and last_repo):
        return "I don't have metrics yet. Run an analysis first."
    return answer_user_question(last_owner, last_repo, question)

# ---------------------------------------------------------
# Routing
# ---------------------------------------------------------
if view == "Overview":
    ui.render_overview(
        has_run=has_run,
        owner=last_owner,
        repo=last_repo,
        history_df=history_df,
        summary=summary,
        on_go_to_ask=go_to_ask,
    )
elif view == "Trends":
    ui.render_trends(history_df=history_df)
else:
    ui.render_ask(
        has_run=has_run,
        owner=last_owner,
        repo=last_repo,
        summary=summary,
        chat_history=st.session_state["chat_history"],
        answer_fn=answer_fn,
        disabled=st.session_state["is_running"],
    )
