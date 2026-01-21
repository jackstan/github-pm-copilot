from __future__ import annotations

import re
from typing import Callable, Optional

import streamlit as st


# -----------------------------
# Header + Nav
# -----------------------------
def render_header(
    owner_input: str,
    repo_input: str,
    last_owner: Optional[str],
    last_repo: Optional[str],
    last_run_at: Optional[str],
    last_days_back: Optional[int],
) -> None:
    repo_label = f"{last_owner}/{last_repo}" if last_owner and last_repo else f"{owner_input}/{repo_input}"
    run_label = f"Last run: {last_run_at}" if last_run_at else "Last run: not yet"
    window_label = f"Window: last {last_days_back} days" if last_days_back else "Window: not set"

    st.markdown(
        f"""
<div class="hero">
  <div class="hero-title">GitHub PM Copilot</div>
  <div class="hero-subtitle">Weekly engineering health, summarized and searchable.</div>
  <div class="hero-meta">
    <span class="pill pill-strong mono">{repo_label}</span>
    <span class="pill">{window_label}</span>
    <span class="pill">{run_label}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_nav(active_view: str, disabled: bool = False) -> str:
    options = ["Overview", "Trends", "Ask"]
    icon = {"Overview": "📌", "Trends": "📈", "Ask": "💬"}
    selected = active_view if active_view in options else options[0]

    st.markdown('<div class="nav-buttons">', unsafe_allow_html=True)
    cols = st.columns(len(options))
    for i, option in enumerate(options):
        button_type = "primary" if option == selected else "secondary"
        if cols[i].button(
            f"{icon[option]} {option}",
            key=f"nav-btn-{option}",
            use_container_width=True,
            disabled=disabled,
            type=button_type,
        ):
            st.session_state["nav_view"] = option
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    return selected


# -----------------------------
# AI Summary formatting
# -----------------------------
def render_ai_summary(summary: str) -> None:
    if not summary:
        st.markdown("_No summary available._")
        return

    # If orchestrator returns markdown bullets only, we still preserve headings if present.
    html = summary

    # Support both "###" and "**Title:**" style headings
    html = re.sub(r"^####\s+(.*)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^###\s+(.*)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)

    # If summary has lines like "Highlights:" treat as section title
    html = re.sub(
        r"^(Highlights|Risks|Recommendations|Notes|Summary)\s*:\s*$",
        r"<h3>\1</h3>",
        html,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    html = html.replace("\n\n", "<br><br>").replace("\n", "<br>")
    st.markdown(f'<div class="ai-summary">{html}</div>', unsafe_allow_html=True)


# -----------------------------
# KPI cards
# -----------------------------
def _delta_chip(delta: Optional[float], higher_is_good: bool = True) -> tuple[str, str]:
    if delta is None:
        return ("", "neutral")
    try:
        d = float(delta)
    except Exception:
        return (str(delta), "neutral")

    if d > 0:
        cls = "up" if higher_is_good else "down"
        return (f"↑ {abs(d):.1f}%", cls)
    if d < 0:
        cls = "down" if higher_is_good else "up"
        return (f"↓ {abs(d):.1f}%", cls)
    return ("0.0%", "neutral")


def render_kpi_row(
    merged_prs: int,
    merged_delta: Optional[float],
    p50_days: float,
    p50_delta: Optional[float],
    p90_days: float,
    p90_delta: Optional[float],
    open_bugs: int,
    bugs_delta: Optional[float],
) -> None:
    m_label, m_cls = _delta_chip(merged_delta, higher_is_good=True)
    p50_label, p50_cls = _delta_chip(p50_delta, higher_is_good=False)
    p90_label, p90_cls = _delta_chip(p90_delta, higher_is_good=False)
    b_label, b_cls = _delta_chip(bugs_delta, higher_is_good=False)

    html = f"""
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Merged PRs</div>
    <div class="kpi-value-row">
      <div class="kpi-value">{merged_prs}</div>
      <div class="kpi-delta {m_cls}">{m_label if m_label else "&nbsp;"}</div>
    </div>
  </div>

  <div class="kpi-card">
    <div class="kpi-label">Lead time p50</div>
    <div class="kpi-value-row">
      <div class="kpi-value">{p50_days:.2f}</div>
      <div class="kpi-delta {p50_cls}">{p50_label if p50_label else "&nbsp;"}</div>
    </div>
  </div>

  <div class="kpi-card">
    <div class="kpi-label">Lead time p90</div>
    <div class="kpi-value-row">
      <div class="kpi-value">{p90_days:.2f}</div>
      <div class="kpi-delta {p90_cls}">{p90_label if p90_label else "&nbsp;"}</div>
    </div>
  </div>

  <div class="kpi-card">
    <div class="kpi-label">Open bugs</div>
    <div class="kpi-value-row">
      <div class="kpi-value">{open_bugs}</div>
      <div class="kpi-delta {b_cls}">{b_label if b_label else "&nbsp;"}</div>
    </div>
  </div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)
