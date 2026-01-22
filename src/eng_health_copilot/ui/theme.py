from __future__ import annotations

import streamlit as st

ACCENT = "#0EA5A4"
ACCENT_2 = "#F97316"


# -----------------------------
# Global CSS / Theme
# -----------------------------
def inject_css() -> None:
    # NOTE: This entire style block must remain inside ONE f-string.
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,400,0,0');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,400,0,0');

:root {{
  --ink: #0f172a;
  --muted: #475569;
  --accent: {ACCENT};
  --accent-strong: #0f766e;
  --accent-2: {ACCENT_2};
  --surface: rgba(255,255,255,0.9);
  --surface-strong: #ffffff;
  --surface-muted: #f7f2ec;
  --border: rgba(15,23,42,0.10);
  --border-light: rgba(15,23,42,0.06);
  --shadow: 0 14px 34px rgba(15,23,42,0.10);
}}

.stApp, html, body {{
  color-scheme: light;
}}

.stApp {{
  background:
    radial-gradient(900px 520px at 8% 6%, rgba(14,165,164,0.15), transparent 60%),
    radial-gradient(760px 520px at 92% 0%, rgba(249,115,22,0.14), transparent 62%),
    linear-gradient(180deg, #f7f2ec 0%, #f6f4f1 45%, #f4f1ec 100%);
  color: var(--ink);
}}

.stApp, .stApp * {{
  font-family: "Space Grotesk", sans-serif;
}}

.stApp {{
  color: var(--ink);
}}

header[data-testid="stHeader"] {{
  background: transparent;
}}

section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div {{
  color: var(--ink);
}}

input, textarea, select {{
  color: var(--ink) !important;
}}

::placeholder {{
  color: rgba(71,85,105,0.7) !important;
}}

.material-icons,
.material-icons-outlined,
.material-icons-round,
.material-icons-sharp,
.material-icons-two-tone {{
  font-family: "Material Icons" !important;
  font-weight: normal !important;
  font-style: normal !important;
  letter-spacing: normal !important;
  text-transform: none !important;
  display: inline-block !important;
  white-space: nowrap !important;
  word-wrap: normal !important;
  direction: ltr !important;
}}

.material-symbols-outlined {{
  font-family: "Material Symbols Outlined" !important;
  font-variation-settings: "opsz" 24, "wght" 400, "FILL" 0, "GRAD" 0;
}}

.material-symbols-rounded {{
  font-family: "Material Symbols Rounded" !important;
  font-variation-settings: "opsz" 24, "wght" 400, "FILL" 0, "GRAD" 0;
}}

.material-symbols-sharp {{
  font-family: "Material Symbols Outlined" !important;
  font-weight: 400 !important;
  font-style: normal !important;
  letter-spacing: normal !important;
  text-transform: none !important;
  display: inline-block !important;
  white-space: nowrap !important;
  word-wrap: normal !important;
  direction: ltr !important;
}}

/* Force Streamlit material icon spans to render as glyphs */
span[data-testid="stIconMaterial"] {{
  font-family: "Material Symbols Outlined", "Material Icons" !important;
  font-weight: 400 !important;
  font-style: normal !important;
  letter-spacing: normal !important;
  text-transform: none !important;
  display: inline-block !important;
  white-space: nowrap !important;
  word-wrap: normal !important;
  direction: ltr !important;
  font-variation-settings: "opsz" 20, "wght" 400, "FILL" 0, "GRAD" 0;
}}

section[data-testid="stSidebar"] {{
  background: rgba(255,255,255,0.65);
  border-right: 1px solid var(--border);
  backdrop-filter: blur(14px);
}}

section[data-testid="stSidebar"] [data-baseweb="base-input"],
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="select"],
section[data-testid="stSidebar"] [data-baseweb="button"] {{
  background: var(--surface-strong) !important;
  color: var(--ink) !important;
}}

.block-container {{
  padding-top: 1.4rem;
  padding-bottom: 2.5rem;
}}

/* Typography polish */
h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{
  color: var(--ink);
  letter-spacing: -0.3px;
}}

.hero {{
  background: linear-gradient(120deg, rgba(255,255,255,0.92), rgba(255,255,255,0.75));
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: var(--shadow);
}}

.hero-title {{
  font-size: 36px;
  font-weight: 700;
}}

.hero-subtitle {{
  color: var(--muted);
  font-size: 16px;
}}

.hero-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}}

.pill {{
  background: var(--surface-strong);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 13px;
  color: var(--muted);
}}

.pill-strong {{
  color: var(--ink);
  font-weight: 600;
}}

.mono {{
  font-family: "IBM Plex Mono", monospace !important;
}}

@keyframes rise {{
  from {{
    opacity: 0;
    transform: translateY(8px);
  }}
  to {{
    opacity: 1;
    transform: translateY(0);
  }}
}}

.hero,
.empty-state,
.ai-summary,
div[data-testid="stVegaLiteChart"] {{
  animation: rise 420ms ease both;
}}

.kpi-card {{
  animation: rise 420ms ease both;
}}

.kpi-card:nth-child(2) {{
  animation-delay: 60ms;
}}

.kpi-card:nth-child(3) {{
  animation-delay: 120ms;
}}

.kpi-card:nth-child(4) {{
  animation-delay: 180ms;
}}

/* Buttons + inputs */
.stButton > button[kind="primary"], .stDownloadButton > button {{
  background: var(--accent);
  color: #ffffff;
  border: 1px solid transparent;
  border-radius: 14px;
  padding: 0.6rem 1.1rem;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(14,165,164,0.25);
}}

.stButton > button[kind="primary"]:hover {{
  background: var(--accent-strong);
}}

.stButton > button[kind="secondary"] {{
  background: var(--surface-strong);
  color: var(--ink);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 0.6rem 1.1rem;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(15,23,42,0.06);
}}

.stButton > button:disabled {{
  background: #cbd5e1;
  color: #64748b;
  box-shadow: none;
}}

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div {{
  border-radius: 12px !important;
  border: 1px solid var(--border) !important;
  background: var(--surface-strong) !important;
  box-shadow: none !important;
}}

div[data-baseweb="input"] > div:has(button) {{
  background: var(--surface-strong) !important;
}}

div[data-baseweb="input"] button,
div[data-baseweb="input"] svg {{
  color: var(--ink) !important;
}}

div[data-baseweb="input"] button {{
  background: var(--surface-muted) !important;
  border: 1px solid var(--border-light) !important;
}}

div[data-testid="stChatInput"] {{
  background: linear-gradient(120deg, rgba(14,165,164,0.12), rgba(255,255,255,0.9));
  border: 2px solid rgba(14,165,164,0.45);
  border-radius: 18px;
  padding: 12px 14px;
  box-shadow: 0 12px 26px rgba(14,165,164,0.12);
}}

div[data-testid="stChatInput"] input,
div[data-testid="stChatInput"] textarea {{
  background: var(--surface-strong) !important;
  color: var(--ink) !important;
}}

div[data-testid="stChatInput"] div[data-baseweb="input"] > div {{
  border: 0 !important;
  box-shadow: none !important;
}}

div[data-testid="stChatInput"] div[data-baseweb="input"] > div:focus-within {{
  border-color: transparent !important;
  box-shadow: none !important;
}}

.ask-input-header {{
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--accent-strong);
  margin-top: 6px;
}}

.ask-input-sub {{
  color: var(--muted);
  margin-bottom: 8px;
}}

.ask-input-sub .pill {{
  margin-left: 6px;
}}

div[data-testid="stTextInput"] [class*="material"],
div[data-testid="stChatInput"] [class*="material"],
div[data-testid="stChatInput"] [data-testid="stIcon"],
div[data-testid="stTextInput"] [data-testid="stIcon"] {{
  font-family: "Material Symbols Outlined" !important;
}}

/* ---------- NAV (tabs) ---------- */
.nav-buttons .stButton > button {{
  width: 100%;
  min-height: 58px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-radius: 16px;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.2px;
  box-shadow: 0 10px 22px rgba(15,23,42,0.06);
}}

.nav-buttons .stButton > button[kind="secondary"] {{
  background: var(--surface-strong);
  color: var(--ink);
  border: 1px solid var(--border);
  box-shadow: 0 10px 22px rgba(15,23,42,0.06);
}}

.nav-buttons .stButton > button[kind="primary"] {{
  background: rgba(14,165,164,0.12);
  color: var(--accent-strong);
  border: 1px solid rgba(14,165,164,0.35);
  box-shadow: none;
}}

/* ---------- KPI cards ---------- */
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}}

.kpi-card {{
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: 18px;
  height: 132px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  overflow: hidden;
  box-sizing: border-box;
  box-shadow: 0 10px 22px rgba(15,23,42,0.06);
}}

.kpi-label {{
  font-size: 15px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

.kpi-value-row {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
}}

.kpi-value {{
  font-size: 44px;
  line-height: 1.0;
  font-family: "IBM Plex Mono", monospace;
}}

.kpi-delta {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  padding: 6px 10px;
  border-radius: 999px;
  white-space: nowrap;
  min-width: 64px;
}}

.kpi-delta.up {{
  background: rgba(34,197,94,0.16);
  border: 1px solid rgba(34,197,94,0.25);
  color: #15803d;
}}

.kpi-delta.down {{
  background: rgba(239,68,68,0.16);
  border: 1px solid rgba(239,68,68,0.25);
  color: #b91c1c;
}}

.kpi-delta.neutral {{
  background: var(--surface-muted);
  border: 1px solid var(--border-light);
  color: var(--muted);
}}

.kpi-delta.placeholder {{
  background: transparent !important;
  border: 1px solid transparent !important;
  color: transparent !important;
  opacity: 0 !important;
}}

/* ---------- Empty state ---------- */
.empty-state {{
  background: var(--surface-strong);
  border: 1px dashed rgba(15,23,42,0.18);
  border-radius: 20px;
  padding: 22px 24px;
  box-shadow: 0 12px 26px rgba(15,23,42,0.08);
}}

.empty-title {{
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 6px;
}}

.empty-subtitle {{
  color: var(--muted);
  margin-bottom: 16px;
}}

.empty-steps {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}}

.empty-step {{
  background: var(--surface-muted);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}}

.empty-step span {{
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}}

.empty-step strong {{
  font-size: 15px;
  color: var(--ink);
}}

/* ---------- Charts container ---------- */
div[data-testid="stVegaLiteChart"] {{
  background: var(--surface-strong) !important;
  border: 1px solid var(--border) !important;
  border-radius: 18px !important;
  padding: 14px 14px 32px 14px !important;
  box-sizing: border-box !important;
  overflow: hidden !important;
  margin-top: 8px !important;
  box-shadow: 0 12px 26px rgba(15,23,42,0.06);
}}

div[data-testid="stVegaLiteChart"] .vega-embed,
div[data-testid="stVegaLiteChart"] .vega-embed > div {{
  background: var(--surface-strong) !important;
}}

div[data-testid="stVegaLiteChart"] .vega-embed .background {{
  fill: #ffffff !important;
}}

div[data-testid="stVegaLiteChart"] .vega-embed text {{
  fill: var(--ink) !important;
}}

div[data-testid="stVegaLiteChart"] .vega-embed .axis line,
div[data-testid="stVegaLiteChart"] .vega-embed .axis path,
div[data-testid="stVegaLiteChart"] .vega-embed .grid line {{
  stroke: rgba(15,23,42,0.16) !important;
}}

/* Progress bar */
div[data-testid="stProgress"] > div > div {{
  background: rgba(15,23,42,0.12) !important;
}}

div[data-testid="stProgress"] > div > div > div {{
  background: var(--accent) !important;
}}

div[data-testid="stVegaLiteChart"] > div,
div[data-testid="stVegaLiteChart"] .vega-embed,
div[data-testid="stVegaLiteChart"] .vega-embed > div {{
  width: 100% !important;
  max-width: 100% !important;
  overflow: hidden !important;
}}

div[data-testid="stVegaLiteChart"] svg {{
  max-width: 100% !important;
  height: auto;
}}

/* Section titles */
.section-title {{
  font-size: 20px;
  font-weight: 600;
  margin: 10px 0 0 0;
}}

.section-title.accent {{
  color: var(--accent-strong);
}}

/* Expanders */
div[data-testid="stExpander"] {{
  margin-bottom: 12px;
}}

div[data-testid="stExpander"] > details {{
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
  position: relative;
}}

div[data-testid="stExpander"] > details > summary {{
  padding: 10px 14px;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  z-index: 1;
  background: var(--surface-strong);
  justify-content: space-between;
}}

div[data-testid="stExpander"] > details > summary::marker,
div[data-testid="stExpander"] > details > summary::-webkit-details-marker {{
  display: none;
  content: "";
}}

div[data-testid="stExpander"] > details > summary span[aria-hidden="true"],
div[data-testid="stExpander"] > details > summary svg,
div[data-testid="stExpander"] > details > summary [data-baseweb="icon"],
div[data-testid="stExpander"] > details > summary [data-testid="stIconMaterial"] {{
  display: none !important;
}}

div[data-testid="stExpander"] [class*="material"],
div[data-testid="stExpander"] [data-testid="stIcon"] {{
  display: none !important;
}}

div[data-testid="stExpander"] > details > summary::after {{
  content: "";
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  transform: rotate(-45deg);
  margin-left: auto;
}}

div[data-testid="stExpander"] > details[open] > summary::after {{
  transform: rotate(45deg);
}}

div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {{
  padding: 4px 14px 14px 14px;
}}

/* Sidebar collapse icon: replace text with CSS chevron */
div[data-testid="stSidebarCollapseButton"] [class*="material"],
div[data-testid="stSidebarCollapseButton"] [data-testid="stIcon"],
div[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
div[data-testid="stSidebarCollapseButton"] svg {{
  display: none !important;
}}

div[data-testid="stSidebarCollapseButton"] button {{
  position: relative;
}}

div[data-testid="stSidebarCollapseButton"] button::after {{
  content: "";
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(135deg);
}}

div[data-testid="stSidebarCollapseButton"] button::before {{
  content: "";
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  position: absolute;
  top: 50%;
  left: calc(50% - 8px);
  transform: translate(-50%, -50%) rotate(135deg);
}}

/* Sidebar collapsed control (when sidebar is hidden) */
div[data-testid="stSidebarCollapsedControl"] [class*="material"],
div[data-testid="stSidebarCollapsedControl"] [data-testid="stIcon"],
div[data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
div[data-testid="stSidebarCollapsedControl"] svg {{
  display: none !important;
}}

div[data-testid="stSidebarCollapsedControl"] button {{
  position: relative;
}}

div[data-testid="stSidebarCollapsedControl"] button::after {{
  content: "";
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-45deg);
}}

div[data-testid="stSidebarCollapsedControl"] button::before {{
  content: "";
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--muted);
  border-bottom: 2px solid var(--muted);
  position: absolute;
  top: 50%;
  left: calc(50% + 8px);
  transform: translate(-50%, -50%) rotate(-45deg);
}}

/* AI summary formatting */
.ai-summary {{
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: 0 8px 18px rgba(15,23,42,0.04);
}}

.ai-summary h3 {{
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(14,165,164,0.25);
  background: rgba(14,165,164,0.08);
}}

.ai-summary h4 {{
  margin-top: 12px;
  padding: 8px 12px;
  border-left: 3px solid {ACCENT_2};
  border-radius: 10px;
  background: rgba(249,115,22,0.08);
}}

.ai-summary p, .ai-summary li {{
  line-height: 1.55;
}}

/* Ask suggestion pills */
.ask-wrap button {{
  min-height: 70px !important;
  padding: 12px 14px !important;
  background: var(--surface-strong) !important;
  border: 1px solid var(--border) !important;
  color: var(--ink) !important;
  box-shadow: none !important;
}}

.ask-wrap button:hover {{
  border-color: rgba(14,165,164,0.4) !important;
  color: var(--accent-strong) !important;
}}

/* Chat */
div[data-testid="stChatMessage"] {{
  background: var(--surface-strong);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 10px 12px;
}}

/* Alerts */
div[data-testid="stAlert"] {{
  border-radius: 16px;
  border: 1px solid rgba(14,165,164,0.25);
  background: rgba(14,165,164,0.08);
  color: var(--ink);
}}

div[data-testid="stAlert"] a {{
  color: var(--accent-strong);
}}

/* Responsive tweaks */
@media (max-width: 1100px) {{
  .kpi-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}
  .empty-steps {{
    grid-template-columns: 1fr;
  }}
}}

@media (max-width: 700px) {{
  .hero-title {{
    font-size: 28px;
  }}
  .nav-buttons .stButton > button {{
    min-height: 54px;
  }}
  .kpi-grid {{
    grid-template-columns: 1fr;
  }}
}}
</style>
""",
        unsafe_allow_html=True,
    )
