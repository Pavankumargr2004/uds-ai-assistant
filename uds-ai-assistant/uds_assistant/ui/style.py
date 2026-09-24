"""Shared styling, session-state helpers and small render helpers for the Streamlit UI."""
from __future__ import annotations

import streamlit as st

from uds_assistant.config import Settings
from uds_assistant.knowledge.service import KnowledgeService
from uds_assistant.llm.base import get_llm
from uds_assistant.store import ProjectStore

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&family=Space+Mono:ital,wght@0,400;0,700;1,400&display=swap');

:root {
  --bg: #F8FAFC;
  --panel: #FFFFFF;
  --panel-2: #F1F5F9;
  --border: #E2E8F0;
  --text: #0F172A;
  --text-dim: #64748B;
  --amber: #E9874F;
  --pos: #059669;
  --neg: #DC2626;
  --sec: #4F46E5;
  --timing: #2563EB;
  --radius: 6px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
}

html, body, [class*="css"] { font-family: 'Manrope', system-ui, sans-serif; }
code, pre, .mono { font-family: 'Space Mono', monospace !important; font-size: 0.84em; }

/* Hide Streamlit chrome */
header[data-testid="stHeader"] { display: none !important; }
.stAppDeployButton { display: none !important; }
#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; }

.stApp { background: var(--bg); }

h1 { font-size: 1.7rem; font-weight: 700; color: var(--text); }
h2 { font-size: 1.25rem; font-weight: 600; color: var(--text); margin-top: 0.25rem; }
h3 { font-size: 0.85rem; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; }

/* Sidebar */
[data-testid="stSidebarContent"] { padding-top: 1rem; }

/* Banner */
.uds-banner {
  border-bottom: 2px solid var(--border);
  padding: 0.75rem 0 0.75rem;
  margin-bottom: 1.25rem;
  display: flex; align-items: baseline; gap: 0.75rem;
}
.uds-banner .mark {
  color: var(--amber);
  font-family: 'Space Mono', monospace;
  font-size: 1rem; font-weight: 700;
}
.uds-banner .sub { color: var(--text-dim); font-size: 0.88rem; }

/* Cards */
.uds-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow);
}

/* Steps */
.uds-step {
  display: flex; gap: 0.75rem; align-items: center;
  padding: 0.4rem 0.6rem; border-radius: 6px; margin-bottom: 0.2rem;
  color: var(--text-dim); font-size: 0.88rem;
}
.uds-step.done { color: var(--pos); }
.uds-step .n {
  font-family: 'Space Mono', monospace;
  color: inherit; width: 1.2rem;
  display: inline-block; font-weight: 700;
}

/* Pills */
.uds-pill {
  display: inline-block; padding: 0.15rem 0.65rem; border-radius: 9999px;
  font-family: 'Space Mono', monospace; font-size: 0.72rem; font-weight: 700;
  text-transform: uppercase; background: var(--panel-2); border: 1px solid var(--border);
}
.pill-pos { color: var(--pos); border-color: var(--pos); background: rgba(5,150,105,0.08); }
.pill-neg { color: var(--neg); border-color: var(--neg); background: rgba(220,38,38,0.08); }
.pill-sec { color: var(--sec); border-color: var(--sec); background: rgba(79,70,229,0.08); }
.pill-timing { color: var(--timing); border-color: var(--timing); background: rgba(37,99,235,0.08); }
.pill-amber { color: var(--amber); border-color: var(--amber); background: rgba(233,135,79,0.08); }
.pill-dim { color: var(--text-dim); }

/* Hex frames */
.uds-frame {
  font-family: 'Space Mono', monospace; font-size: 0.82rem;
  background: #F1F5F9; border: 1px solid var(--border); border-radius: 4px;
  padding: 0.45rem 0.75rem; color: var(--text);
  overflow-x: auto; display: inline-block;
}

/* Metrics */
div[data-testid="stMetricValue"] {
  font-family: 'Space Mono', monospace; color: var(--amber); font-weight: 700;
}

/* Buttons */
.stButton > button, .stDownloadButton > button {
  border-radius: var(--radius); border: 1px solid var(--border);
  background: var(--panel); color: var(--text);
  font-family: 'Manrope', sans-serif; font-weight: 600;
  box-shadow: var(--shadow); transition: all 0.15s;
}
.stButton > button:hover {
  border-color: var(--amber); color: var(--amber);
  transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
button[kind="primary"] {
  background: var(--amber) !important;
  border-color: var(--amber) !important;
  color: white !important;
}
button[kind="primary"]:hover {
  background: #d97220 !important; color: white !important;
}
</style>
"""

CATEGORY_PILL = {
    "positive": "pill-pos", "negative": "pill-neg", "session": "pill-timing",
    "security": "pill-sec", "timing": "pill-timing", "boundary": "pill-amber",
}
STATUS_PILL = {"approved": "pill-pos", "rejected": "pill-neg", "draft": "pill-dim"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def banner(subtitle: str) -> None:
    st.markdown(
        f'<div class="uds-banner"><span class="mark">UDS // ASSISTANT</span>'
        f'<span class="sub">{subtitle}</span></div>', unsafe_allow_html=True)


def pill(text: str, cls: str) -> str:
    return f'<span class="uds-pill {cls}">{text}</span>'


@st.cache_resource
def _settings() -> Settings:
    return Settings()


@st.cache_resource
def get_store() -> ProjectStore:
    return ProjectStore(_settings())


@st.cache_resource
def get_knowledge() -> KnowledgeService:
    s = _settings()
    return KnowledgeService(s, get_llm(s))


def init_identity() -> tuple[str, str]:
    st.session_state.setdefault("user", "engineer1")
    st.session_state.setdefault("role", "engineer")
    return st.session_state["user"], st.session_state["role"]
