"""UDS Diagnostics and Automated Test Generation Assistant - Streamlit UI.

Run with: uds-ai ui   (or: streamlit run uds_assistant/ui/app.py)
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="UDS Diagnostics Assistant",
    page_icon="◈",
    layout="wide",
)

from uds_assistant.coverage import compute_coverage
from uds_assistant.generator.builder import build_request
from uds_assistant.generator.exporters import export_all
from uds_assistant.generator.intent import parse_requirement, select_tests
from uds_assistant.generator.suites import build_suite
from uds_assistant.protocol.profile import parse_profile
from uds_assistant.protocol.validator import validate_request
from uds_assistant.runner.runner import Runner
from uds_assistant.runner.transport import SimTransport
from uds_assistant.simulator.mock_ecu import FAULTS
from uds_assistant.ui.style import (
    CATEGORY_PILL, STATUS_PILL, banner,
    get_knowledge, get_store, init_identity, inject_css, pill
)

inject_css()
store = get_store()
knowledge = get_knowledge()

STEPS = ["Profile & knowledge", "Sandbox", "Generate tests", "Review", "Run", "Export", "Audit"]


# ================================================================================================
# HOME PAGE — Marketing landing page
# ================================================================================================
def page_home():
    st.markdown("""
<style>
/* Remove all Streamlit chrome on home page */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.stApp { background: #050A14 !important; }
header { display: none !important; }
footer { display: none !important; }
.stMainBlockContainer, .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ---- NAVBAR ---- */
.nav {
    position: fixed; top: 0; left: 0; right: 0; z-index: 999;
    display: flex; align-items: center; justify-content: space-between;
    padding: 1.2rem 6%;
    background: rgba(5, 10, 20, 0.85);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255,255,255,0.07);
}
.nav-logo {
    font-family: 'Manrope', sans-serif;
    font-weight: 800; font-size: 1.1rem;
    letter-spacing: 0.1em; color: #ffffff;
    text-decoration: none;
}
.nav-logo span { color: #E9874F; }
.nav-links { display: flex; gap: 2rem; }
.nav-links a {
    font-family: 'Manrope', sans-serif;
    color: rgba(255,255,255,0.65); font-size: 0.9rem;
    text-decoration: none; font-weight: 500;
    transition: color 0.2s;
}
.nav-links a:hover { color: #E9874F; }

/* ---- HERO ---- */
.hero {
    min-height: 100vh;
    background: linear-gradient(135deg, rgba(5,10,20,0.97) 0%, rgba(11,20,38,0.92) 100%),
                url('https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?q=80&w=2560') center/cover no-repeat;
    display: flex; align-items: center;
    padding: 8rem 6% 6rem;
    position: relative; overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at 70% 50%, rgba(233,135,79,0.08) 0%, transparent 60%);
}
.hero-grid {
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 4rem; align-items: center;
    max-width: 1400px; margin: 0 auto; width: 100%;
}
.hero-eyebrow {
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem; font-weight: 400;
    color: #E9874F; letter-spacing: 0.15em;
    text-transform: uppercase; margin-bottom: 1.2rem;
    display: flex; align-items: center; gap: 0.5rem;
}
.hero-eyebrow::before {
    content: ''; width: 24px; height: 1px; background: #E9874F;
}
.hero h1 {
    font-family: 'Manrope', sans-serif !important;
    font-size: clamp(2.2rem, 4vw, 3.8rem) !important;
    font-weight: 800 !important;
    line-height: 1.08 !important;
    color: #fff !important;
    -webkit-text-fill-color: unset !important;
    background: none !important;
    -webkit-background-clip: unset !important;
    margin-bottom: 1.5rem !important;
}
.hero h1 em {
    font-style: normal;
    background: linear-gradient(90deg, #E9874F, #f5b07a);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.hero-subtitle {
    font-family: 'Manrope', sans-serif;
    font-size: 1.15rem; color: rgba(255,255,255,0.6);
    line-height: 1.65; margin-bottom: 2.5rem;
}
.hero-cta {
    display: flex; gap: 1rem; flex-wrap: wrap;
}
.cta-primary {
    background: #E9874F; color: #fff !important;
    padding: 0.85rem 2rem; border-radius: 6px;
    text-decoration: none; font-weight: 700;
    font-family: 'Manrope', sans-serif; font-size: 0.95rem;
    border: 2px solid #E9874F;
    transition: all 0.2s; cursor: pointer;
    display: inline-block;
}
.cta-primary:hover { background: #d97220; border-color: #d97220; transform: translateY(-2px); }
.cta-secondary {
    background: transparent; color: rgba(255,255,255,0.8) !important;
    padding: 0.85rem 2rem; border-radius: 6px;
    text-decoration: none; font-weight: 600;
    font-family: 'Manrope', sans-serif; font-size: 0.95rem;
    border: 2px solid rgba(255,255,255,0.2);
    transition: all 0.2s;
    display: inline-block;
}
.cta-secondary:hover { border-color: rgba(255,255,255,0.5); color: #fff !important; }

/* Hero right side - ECU card */
.hero-visual {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 16px;
    padding: 2rem;
    backdrop-filter: blur(8px);
    position: relative;
}
.hero-visual-header {
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 1.5rem;
}
.dot { width: 10px; height: 10px; border-radius: 50%; }
.dot-r { background: #ff5f57; }
.dot-y { background: #febc2e; }
.dot-g { background: #28c840; }
.hero-terminal {
    font-family: 'Space Mono', monospace;
    font-size: 0.8rem; color: rgba(255,255,255,0.7);
    line-height: 1.8;
}
.t-dim { color: rgba(255,255,255,0.3); }
.t-grn { color: #5FBE84; }
.t-amb { color: #E9874F; }
.t-blu { color: #62AACF; }

/* ---- TRUST STRIP ---- */
.trust-strip {
    background: #0A0F1E;
    border-top: 1px solid rgba(255,255,255,0.07);
    border-bottom: 1px solid rgba(255,255,255,0.07);
    padding: 2rem 6%;
    display: flex; align-items: center;
    gap: 3rem; overflow-x: auto;
}
.trust-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem; color: rgba(255,255,255,0.3);
    text-transform: uppercase; letter-spacing: 0.1em;
    white-space: nowrap;
}
.trust-tag {
    font-family: 'Manrope', sans-serif;
    font-size: 0.85rem; font-weight: 600;
    color: rgba(255,255,255,0.6);
    padding: 0.4rem 1rem;
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 999px; white-space: nowrap;
}
.trust-tag:hover { border-color: #E9874F; color: #E9874F; }

/* ---- FEATURES ---- */
.features-section {
    padding: 6rem 6%;
    background: #070C1A;
}
.section-eyebrow {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem; color: #E9874F;
    letter-spacing: 0.15em; text-transform: uppercase;
    text-align: center; margin-bottom: 0.75rem;
}
.section-title {
    font-family: 'Manrope', sans-serif;
    font-size: clamp(1.8rem, 3vw, 2.8rem); font-weight: 800;
    color: #fff; text-align: center; margin-bottom: 1rem;
}
.section-sub {
    font-family: 'Manrope', sans-serif;
    font-size: 1.05rem; color: rgba(255,255,255,0.5);
    text-align: center; max-width: 600px;
    margin: 0 auto 3.5rem;
}
.features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1.5rem; max-width: 1200px; margin: 0 auto;
}
.feature-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 2rem;
    transition: all 0.3s;
}
.feature-card:hover {
    border-color: rgba(233,135,79,0.4);
    background: rgba(233,135,79,0.05);
    transform: translateY(-4px);
}
.feature-icon {
    font-size: 2rem; margin-bottom: 1rem;
}
.feature-title {
    font-family: 'Manrope', sans-serif;
    font-size: 1.05rem; font-weight: 700;
    color: #fff; margin-bottom: 0.5rem;
}
.feature-desc {
    font-family: 'Manrope', sans-serif;
    font-size: 0.9rem; color: rgba(255,255,255,0.5);
    line-height: 1.6;
}

/* ---- ABOUT ---- */
.about-section {
    padding: 6rem 6%;
    background: #050A14;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 5rem; align-items: center;
    max-width: 1400px; margin: 0 auto;
}
.about-img-wrapper {
    position: relative;
}
.about-img-wrapper img {
    width: 100%; border-radius: 16px;
    object-fit: cover; height: 480px;
    box-shadow: 0 30px 60px rgba(0,0,0,0.5);
}
.about-img-badge {
    position: absolute; bottom: -20px; right: -20px;
    background: #E9874F; color: white;
    padding: 1.2rem 1.8rem; border-radius: 12px;
    font-family: 'Space Mono', monospace;
    font-size: 0.75rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.05em;
}
.about-text { }
.about-eyebrow {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem; color: #E9874F;
    letter-spacing: 0.15em; text-transform: uppercase;
    margin-bottom: 1rem;
}
.about-text h2 {
    font-family: 'Manrope', sans-serif !important;
    font-size: clamp(1.8rem, 2.5vw, 2.5rem) !important;
    font-weight: 800 !important;
    color: #fff !important;
    line-height: 1.15 !important;
    margin-bottom: 1.5rem !important;
    -webkit-text-fill-color: unset !important;
    background: none !important;
}
.about-text p {
    font-family: 'Manrope', sans-serif;
    font-size: 1rem; color: rgba(255,255,255,0.55);
    line-height: 1.7; margin-bottom: 1.2rem;
}
.tech-stack {
    display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 2rem;
}
.tech-pill {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem; color: #E9874F;
    border: 1px solid rgba(233,135,79,0.4);
    padding: 0.3rem 0.8rem; border-radius: 999px;
}

/* ---- CTA BANNER ---- */
.cta-banner {
    padding: 5rem 6%;
    background: linear-gradient(135deg, #0A1428 0%, #0F1E3E 100%);
    text-align: center;
    border-top: 1px solid rgba(255,255,255,0.07);
}
.cta-banner h2 {
    font-family: 'Manrope', sans-serif !important;
    font-size: clamp(1.8rem, 3vw, 2.8rem) !important;
    font-weight: 800 !important; color: #fff !important;
    margin-bottom: 1rem !important;
    -webkit-text-fill-color: unset !important;
    background: none !important;
}
.cta-banner p {
    font-family: 'Manrope', sans-serif;
    font-size: 1.05rem; color: rgba(255,255,255,0.55);
    margin-bottom: 2.5rem;
}
.cta-center { display: flex; gap: 1rem; justify-content: center; }

/* ---- FOOTER ---- */
.site-footer {
    background: #030710;
    padding: 2rem 6%;
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid rgba(255,255,255,0.06);
}
.footer-logo {
    font-family: 'Manrope', sans-serif;
    font-weight: 800; font-size: 1rem; color: #fff;
}
.footer-logo span { color: #E9874F; }
.footer-copy {
    font-family: 'Space Mono', monospace;
    font-size: 0.72rem; color: rgba(255,255,255,0.25);
}
</style>

<!-- NAVBAR -->
<div class="nav">
  <a class="nav-logo">UDS<span>//</span>AI</a>
  <div class="nav-links">
    <a href="#">Features</a>
    <a href="#">About</a>
    <a href="#">Documentation</a>
  </div>
  <a href="#" class="cta-primary" style="padding: 0.6rem 1.4rem; font-size:0.85rem;"
     onclick="(function(){var links=window.parent.document.querySelectorAll('a'); for(var i=0;i<links.length;i++){if(links[i].textContent.trim()==='Knowledge Base'){links[i].click();return;}}})(); return false;">
    Launch Platform →
  </a>
</div>

<!-- HERO SECTION -->
<div class="hero">
  <div class="hero-grid">
    <div>
      <div class="hero-eyebrow">Automotive AI Platform</div>
      <h1>AI-Powered UDS Diagnostics &amp; <em>Automated Test Generation</em></h1>
      <p class="hero-subtitle">Transforming Diagnostic Validation with AI-Powered Knowledge Retrieval, Request Verification and Test Automation.</p>
      <div class="hero-cta">
        <a href="#" class="cta-primary"
           onclick="(function(){var links=window.parent.document.querySelectorAll('a'); for(var i=0;i<links.length;i++){if(links[i].textContent.trim()==='Knowledge Base'){links[i].click();return;}}})(); return false;">
          Explore Platform
        </a>
        <a href="#" class="cta-secondary">Watch Demo ▶</a>
      </div>
    </div>
    <div class="hero-visual">
      <div class="hero-visual-header">
        <div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div>
        <span style="font-family:'Space Mono',monospace;font-size:0.72rem;color:rgba(255,255,255,0.3);margin-left:0.5rem;">uds_assistant ─ simulator</span>
      </div>
      <div class="hero-terminal">
        <div><span class="t-dim">$</span> <span class="t-grn">uds-ai</span> serve --project demo_ecu</div>
        <div><span class="t-dim">→</span> Loading ECU profile <span class="t-amb">DEMO_ECU_v1.2</span></div>
        <div><span class="t-dim">→</span> <span class="t-blu">87 services</span> · <span class="t-blu">34 DIDs</span> · <span class="t-blu">12 routines</span></div>
        <div><span class="t-dim">→</span> Knowledge base indexed <span class="t-grn">✓</span></div>
        <div style="margin-top:0.5rem"><span class="t-dim">$</span> <span class="t-grn">uds-ai</span> generate --suite full</div>
        <div><span class="t-dim">→</span> Generated <span class="t-amb">248 test cases</span></div>
        <div><span class="t-dim">→</span> Coverage <span class="t-grn">94.3%</span> · Gaps: <span class="t-amb">3</span></div>
        <div style="margin-top:0.5rem"><span class="t-dim">$</span> <span class="t-grn">uds-ai</span> run --approved-only</div>
        <div><span class="t-dim">→</span> <span class="t-grn">231 passed</span> · <span style="color:#DD6A5E;">1 failed</span> · pass rate <span class="t-grn">99.6%</span></div>
      </div>
    </div>
  </div>
</div>

<!-- TRUST STRIP -->
<div class="trust-strip">
  <span class="trust-label">Built for</span>
  <span class="trust-tag">UDS Diagnostics</span>
  <span class="trust-tag">ECU Validation</span>
  <span class="trust-tag">Test Automation</span>
  <span class="trust-tag">Coverage Analysis</span>
  <span class="trust-tag">OEM Spec Processing</span>
  <span class="trust-tag">ISO 14229 Compliance</span>
  <span class="trust-tag">RAG-Powered Retrieval</span>
</div>

<!-- FEATURES -->
<div class="features-section">
  <div class="section-eyebrow">Platform Capabilities</div>
  <div class="section-title">Everything you need for diagnostic validation</div>
  <p class="section-sub">A complete AI-powered workflow from specification ingestion to test execution and export.</p>
  <div class="features-grid">
    <div class="feature-card">
      <div class="feature-icon">📚</div>
      <div class="feature-title">Knowledge Base & RAG</div>
      <div class="feature-desc">Upload UDS specs, OEM documents and ECU profiles. Ask grounded questions with cited answers from the knowledge base.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">🧪</div>
      <div class="feature-title">Request Sandbox</div>
      <div class="feature-desc">Build and validate UDS requests in plain English or raw hex. Expected responses computed from the ECU profile — never guessed.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">⚡</div>
      <div class="feature-title">Automated Test Generation</div>
      <div class="feature-desc">Generate full systematic test suites — positive, negative, boundary and error paths — directly from the ECU profile.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">👀</div>
      <div class="feature-title">Four-Eyes Review</div>
      <div class="feature-desc">Structured review workflow with role-based approval, comments and audit trail. Four-eyes policy enforcement built in.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">▶️</div>
      <div class="feature-title">Simulation & Execution</div>
      <div class="feature-desc">Run tests against a built-in ECU simulator with real-time progress and fault injection for defect detection validation.</div>
    </div>
    <div class="feature-card">
      <div class="feature-icon">💾</div>
      <div class="feature-title">Multi-Format Export</div>
      <div class="feature-desc">Export test cases as Python/pytest, CAPL for CANoe, JSON, CSV or Markdown specifications ready for any toolchain.</div>
    </div>
  </div>
</div>

<!-- ABOUT SECTION -->
<div style="padding: 6rem 6%; background: #050A14;">
  <div class="about-section" style="padding: 0; margin: 0; max-width: 100%;">
    <div class="about-img-wrapper">
      <img src="https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=1200" />
      <div class="about-img-badge">ISO 14229 Compliant</div>
    </div>
    <div class="about-text">
      <div class="about-eyebrow">About the Platform</div>
      <h2>Accelerate Diagnostic Validation by 10×</h2>
      <p>The platform helps engineers interpret UDS specifications, validate requests, generate positive and negative test cases, and export automation scripts — all in one unified workflow.</p>
      <p>Built using Agentic AI, Retrieval-Augmented Generation (RAG), Graph Traceability via Neo4j, and a production-grade SQLAlchemy backend. Matches the functional objectives and technology recommendations described in the Case Study 5 of the Automotive Engineering AI Standard Project.</p>
      <div class="tech-stack">
        <span class="tech-pill">Python 3.12</span>
        <span class="tech-pill">Streamlit</span>
        <span class="tech-pill">FastAPI</span>
        <span class="tech-pill">RAG / Vector Search</span>
        <span class="tech-pill">Neo4j Graph DB</span>
        <span class="tech-pill">SQLAlchemy</span>
        <span class="tech-pill">LLM Integration</span>
      </div>
    </div>
  </div>
</div>

<!-- CTA BANNER -->
<div class="cta-banner">
  <h2>Ready to transform your diagnostic workflow?</h2>
  <p>Launch the platform and start with your first ECU profile in minutes.</p>
  <div class="cta-center">
    <a href="#" class="cta-primary"
       onclick="(function(){var links=window.parent.document.querySelectorAll('a'); for(var i=0;i<links.length;i++){if(links[i].textContent.trim()==='Knowledge Base'){links[i].click();return;}}})(); return false;">
      Launch Platform →
    </a>
    <a href="#" class="cta-secondary">View Documentation</a>
  </div>
</div>

<!-- FOOTER -->
<div class="site-footer">
  <div class="footer-logo">UDS<span>//</span>AI ASSISTANT</div>
  <div class="footer-copy">Final Year Project · Automotive Engineering AI Standard · Case Study 5</div>
</div>
""", unsafe_allow_html=True)


# ================================================================================================
# SIDEBAR SETUP — runs on all platform pages
# ================================================================================================
def setup_sidebar():
    global user, role, proj, profile

    with st.sidebar:
        banner("bench")
        user, role = init_identity()
        with st.expander("Identity", expanded=False):
            st.session_state["user"] = st.text_input("Name", value=user)
            st.session_state["role"] = st.selectbox(
                "Role", ["viewer", "engineer", "lead", "admin"],
                index=["viewer", "engineer", "lead", "admin"].index(role)
            )
        user, role = st.session_state["user"], st.session_state["role"]

        st.markdown("#### Project")
        projects = store.list_projects()
        proj = (
            st.selectbox("Active project", projects, index=0 if projects else None,
                         placeholder="No projects yet")
            if projects else None
        )
        with st.expander("New project"):
            new_name = st.text_input("Project name", key="new_proj_name")
            if st.button("Create project", use_container_width=True) and new_name:
                if store.exists(new_name):
                    st.error(f"Project '{new_name}' already exists.")
                else:
                    store.create(new_name)
                    store.audit(new_name, user, role, "create_project")
                    st.success(f"Created '{new_name}'.")
                    st.rerun()

        if proj:
            state = store.load(proj)
            has_profile = state.profile is not None
            n_tests = len(state.tests)
            n_approved = sum(1 for t in state.tests.values() if t.get("status") == "approved")
            n_runs = len(state.runs)
            st.markdown("#### Workflow")
            steps_done = [has_profile, has_profile, n_tests > 0, n_tests > 0, n_runs > 0, n_approved > 0, True]
            for i, (label, done) in enumerate(zip(STEPS, steps_done), start=1):
                cls = "done" if done and i < 7 else ""
                mark = "✓" if done and i < 7 else str(i)
                st.markdown(
                    f'<div class="uds-step {cls}"><span class="n">{mark}</span>{label}</div>',
                    unsafe_allow_html=True
                )
            st.caption(f"{n_tests} test(s) · {n_approved} approved · {n_runs} run(s)")

    if not proj:
        banner("no active project")
        st.info("Create a project in the sidebar to begin.")
        st.stop()

    profile = store.get_profile(proj)
    banner(f"project · {proj}")


# ================================================================================================
# PLATFORM PAGES
# ================================================================================================
def page_knowledge():
    global user, role, proj, profile
    setup_sidebar()
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("### ECU profile")
        if profile:
            st.markdown(
                f'<div class="uds-card"><b>{profile.name}</b> — {profile.oem}, v{profile.version}<br>'
                f'<span style="color:var(--text-dim)">{len(profile.services)} services · {len(profile.dids)} DIDs · '
                f'{len(profile.routines)} routines · {len(profile.security_levels)} security level(s)</span></div>',
                unsafe_allow_html=True)
            with st.expander("Services"):
                for sid, svc in profile.services.items():
                    st.markdown(f'`0x{sid:02X}` **{svc.name}** — sessions: '
                               f'{", ".join(profile.session_name(s) for s in svc.sessions)}')
            with st.expander("Data identifiers (DIDs)"):
                for d in profile.dids:
                    acc = []
                    if d.read:
                        acc.append("read" + (f" (L{d.read.security})" if d.read.security else ""))
                    if d.write:
                        acc.append("write" + (f" (L{d.write.security})" if d.write.security else ""))
                    st.markdown(f'`0x{d.id:04X}` **{d.name}** — {d.length}B {d.data_type} · {" / ".join(acc)}')
            with st.expander("Routines"):
                for r in profile.routines:
                    st.markdown(f'`0x{r.id:04X}` **{r.name}**' + (f" — security L{r.security}" if r.security else ""))
        else:
            st.warning("No ECU profile uploaded yet.")
        up = st.file_uploader("Upload ECU profile (YAML)", type=["yaml", "yml"], key="profile_up")
        if up is not None and st.button("Load profile"):
            try:
                p = parse_profile(up.getvalue().decode("utf-8"))
            except Exception as e:
                st.error(f"Invalid profile: {e}")
            else:
                store.set_profile(proj, p, f"upload:{up.name}", user, role)
                n = knowledge.ingest_profile(proj, p, source=f"ECU profile {p.name} v{p.version}")
                st.success(f"Loaded {p.name} v{p.version}; indexed {n} knowledge chunk(s).")
                st.rerun()

    with right:
        st.markdown("### Knowledge base")
        st.caption("Standard / OEM specs, ECU-specific notes and project notes. Every chunk is citeable.")
        docup = st.file_uploader("Upload a document (.md, .txt, .pdf)", type=["md", "txt", "pdf"], key="doc_up")
        layer = st.selectbox("Layer", ["project", "ecu", "oem", "standard"], index=0)
        version = st.text_input("Document version (optional)", value="")
        if docup is not None and st.button("Ingest document"):
            import tempfile
            from pathlib import Path
            tmp = Path(tempfile.mkdtemp()) / docup.name
            tmp.write_bytes(docup.getvalue())
            try:
                n = knowledge.ingest_file(proj, tmp, layer, version, source_name=docup.name)
            except ValueError as e:
                st.error(str(e))
            else:
                st.success(f"Indexed {n} chunk(s) from {docup.name} ({layer}).")
                st.rerun()
        sources = knowledge.sources(proj)
        if sources:
            for s in sources:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f'{pill(s["layer"], "pill-amber")} **{s["source"]}** '
                           f'<span style="color:var(--text-dim)">· {s["chunks"]} chunk(s)'
                           f'{" · v" + s["version"] if s["version"] else ""}</span>', unsafe_allow_html=True)
                if c2.button("Remove", key=f"rm_{s['source']}"):
                    knowledge.delete_source(proj, s["source"])
                    st.rerun()
        else:
            st.caption("No documents ingested yet.")

        st.markdown("#### Ask")
        q = st.text_input("Ask a grounded question about this ECU", key="ask_q",
                          placeholder="e.g. what security level is needed to write the VIN?")
        if q:
            ans = knowledge.ask(proj, q)
            conf_cls = {"high": "pill-pos", "medium": "pill-amber", "low": "pill-neg",
                       "insufficient": "pill-dim"}[ans.confidence_label]
            st.markdown(pill(f"{ans.mode} · {ans.confidence_label} ({ans.confidence})", conf_cls),
                       unsafe_allow_html=True)
            st.write(ans.answer)
            for w in ans.warnings:
                st.caption(f"⚠ {w}")
            if ans.citations:
                with st.expander(f"{len(ans.citations)} citation(s)"):
                    for c in ans.citations:
                        st.markdown(f"**[{c.n}]** {c.source}" + (f" > {c.section}" if c.section else ""))
                        st.markdown(f'<div class="uds-frame" style="white-space:pre-wrap">{c.snippet}</div>',
                                   unsafe_allow_html=True)


def page_sandbox():
    global user, role, proj, profile
    setup_sidebar()
    if not profile:
        st.info("Upload an ECU profile first.")
        return
    st.markdown("### Request sandbox")
    st.caption("Describe a request in plain language or paste raw hex; the expected response is "
              "computed from the ECU profile, never guessed.")
    c1, c2 = st.columns([2, 1])
    with c1:
        text = st.text_input("Instruction or hex", placeholder='e.g. "read the VIN" or "22 F1 90"')
    with c2:
        session = st.selectbox("Session", list(profile.sessions.items()),
                               format_func=lambda kv: f"0x{kv[0]:02X} {kv[1]}")[0]
    unlocked = st.multiselect("Unlocked security levels", [s.level for s in profile.security_levels])
    if text:
        built = build_request(profile, text)
        if built.ok:
            st.markdown(f'<div class="uds-frame">{built.request}</div>', unsafe_allow_html=True)
            st.caption(built.description)
            for n in built.notes:
                st.caption(f"ℹ {n}")
            req_text = built.request
        else:
            st.warning(built.description)
            req_text = text
        report = validate_request(profile, req_text, session=session, unlocked=unlocked)
        if report.valid_hex:
            kind_pill = {"positive": "pill-pos", "negative": "pill-neg", "none": "pill-dim"}[report.expectation]
            st.markdown(pill(report.expectation, kind_pill) + "  " +
                       f'<span class="uds-frame">{report.expected_pattern or "no response"}</span>',
                       unsafe_allow_html=True)
            st.caption(report.rule)
            for f in report.findings:
                icon = {"info": "ℹ", "warning": "⚠", "error": "✗"}[f.level]
                st.caption(f"{icon} {f.message}")


def page_generate():
    global user, role, proj, profile
    setup_sidebar()
    if not profile:
        st.info("Upload an ECU profile first.")
        return
    st.markdown("### Generate tests")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Full systematic suite**")
        st.caption("Every service, sub-function, boundary and error path implied by the profile.")
        if st.button("Generate full suite", type="primary"):
            with st.spinner("Generating..."):
                tests = build_suite(profile)
                for t in tests:
                    t.created_by = user
                store.save_tests(proj, tests, user, role, origin="full systematic suite")
                cov = compute_coverage(profile, tests)
            st.success(f"Generated {len(tests)} test(s). Coverage {cov['percent']}%.")
            st.rerun()
    with c2:
        st.markdown("**From a requirement**")
        req = st.text_area("Requirement text", height=90,
                           placeholder="e.g. The ECU shall reject writing the VIN without security access")
        use_llm = st.checkbox("Also ask the LLM for additional targets (profile-validated)", value=False)
        if st.button("Generate from requirement") and req:
            with st.spinner("Analysing requirement..."):
                full = build_suite(profile)
                llm = knowledge.llm if use_llm else None
                intent = parse_requirement(profile, req, llm)
                selected = select_tests(profile, full, intent)
            if not selected:
                st.warning("No matching systematic tests found. Try naming a DID, routine, service or session.")
            else:
                for t in selected:
                    t.requirement_id, t.origin, t.created_by = req[:120], "requirement", user
                store.save_tests(proj, selected, user, role, origin=f"requirement: {req[:60]!r}")
                st.success(f"Linked {len(selected)} test(s) to this requirement.")
                st.rerun()

    tests = store.list_tests(proj)
    if tests:
        st.markdown("#### Coverage")
        cov = compute_coverage(profile, tests)
        m1, m2, m3 = st.columns(3)
        m1.metric("Coverage", f"{cov['percent']}%")
        m2.metric("Test cases", len(tests))
        m3.metric("Gaps", len(cov["gaps"]))
        with st.expander("By category"):
            for cat, d in cov["by_category"].items():
                st.progress(d["percent"] / 100, text=f"{cat}: {d['covered']}/{d['total']} ({d['percent']}%)")
        if cov["gaps"]:
            with st.expander(f"Uncovered items ({len(cov['gaps'])})"):
                st.code("\n".join(cov["gaps"]))


def page_review():
    global user, role, proj, profile
    setup_sidebar()
    tests = store.list_tests(proj)
    if not tests:
        st.info("No tests generated yet.")
        return
    st.markdown("### Review queue")
    settings = knowledge.s
    if settings.four_eyes:
        st.caption("Four-eyes review is enabled: approvers must differ from the test author.")
    c1, c2, c3 = st.columns(3)
    status_f = c1.selectbox("Status", ["all", "draft", "approved", "rejected"])
    cat_f = c2.selectbox("Category", ["all"] + sorted({t.category for t in tests}))
    svc_f = c3.selectbox("Service", ["all"] + sorted({f"0x{t.service:02X}" for t in tests}))
    filtered = tests
    if status_f != "all":
        filtered = [t for t in filtered if t.status == status_f]
    if cat_f != "all":
        filtered = [t for t in filtered if t.category == cat_f]
    if svc_f != "all":
        filtered = [t for t in filtered if f"0x{t.service:02X}" == svc_f]
    st.caption(f"{len(filtered)} of {len(tests)} test(s)")

    for t in sorted(filtered, key=lambda t: t.id)[:150]:
        with st.expander(f"{t.id} — {t.title}"):
            st.markdown(pill(t.category, CATEGORY_PILL.get(t.category, "pill-dim")) + " " +
                       pill(t.status, STATUS_PILL.get(t.status, "pill-dim")) +
                       (f" {pill('req: ' + t.requirement_id[:40], 'pill-amber')}" if t.requirement_id else ""),
                       unsafe_allow_html=True)
            st.write(t.objective)
            for s in t.steps:
                if s.action == "wait":
                    st.caption(f"{s.n}. wait {s.wait_ms} ms — {s.description}")
                else:
                    exp_pill = {"positive": "pill-pos", "negative": "pill-neg", "none": "pill-dim"}[s.expect]
                    st.markdown(f'{s.n}. [{s.role}] <span class="uds-frame">{s.request}</span> → '
                               f'{pill(s.expected_pattern or "no response", exp_pill)} '
                               f'<span style="color:var(--text-dim)">{s.description}</span>',
                               unsafe_allow_html=True)
            if role in ("lead", "admin"):
                rc1, rc2, rc3 = st.columns([1, 1, 3])
                comment = rc3.text_input("Comment", key=f"cm_{t.id}", label_visibility="collapsed",
                                        placeholder="Review comment (optional)")
                if rc1.button("Approve", key=f"ap_{t.id}"):
                    try:
                        store.review_test(proj, t.id, user, role, "approved", comment, settings.four_eyes)
                    except PermissionError as e:
                        st.error(str(e))
                    else:
                        st.rerun()
                if rc2.button("Reject", key=f"rj_{t.id}"):
                    store.review_test(proj, t.id, user, role, "rejected", comment, settings.four_eyes)
                    st.rerun()


def page_execute():
    global user, role, proj, profile
    setup_sidebar()
    tests = store.list_tests(proj)
    if not tests or not profile:
        st.info("Generate tests first.")
        return
    st.markdown("### Execute")
    st.caption("Simulator runs are always available. Hardware execution needs explicit environment flags.")
    include_draft = st.checkbox("Include draft (unapproved) tests", value=False)
    pool = tests if include_draft else [t for t in tests if t.status == "approved"]
    st.caption(f"{len(pool)} test(s) selected for this run.")
    faults = st.multiselect("Inject simulator fault(s)",
                            FAULTS.keys(), format_func=lambda f: f"{f} — {FAULTS[f]}")
    if st.button("▶ Run tests", type="primary", disabled=not pool):
        transport = SimTransport(profile, faults=faults)
        runner = Runner(profile, transport)
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()
        total_tests = len(pool)
        completed = 0
        summary = None
        for event in runner.run_stream(pool, faults=faults):
            if hasattr(event, "verdict"):
                completed += 1
                progress_bar.progress(completed / total_tests)
                status_text.text(f"Running... {completed}/{total_tests}")
                icon = "✅" if event.verdict == "pass" else "❌" if event.verdict == "fail" else "⚠️"
                log_container.markdown(f"{icon} **{event.test_id}**: {event.title} — {event.message}")
            else:
                summary = event
        status_text.text(f"Completed {total_tests} tests.")
        if summary:
            entry = store.record_run(proj, summary, user, role, [t.id for t in pool])
            st.session_state["last_run"] = entry["run_id"]
        st.rerun()

    runs = store.list_runs(proj)
    if runs:
        latest = runs[-1]
        s = latest["summary"]
        st.markdown("#### Last run")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Passed", f"{s['passed']}/{s['total']}")
        m2.metric("Failed", s["failed"])
        m3.metric("Errors", s["errors"])
        m4.metric("Pass rate", f"{s['pass_rate']}%")
        if s["faults"]:
            st.caption("Injected faults: " + ", ".join(s["faults"]))
        fails = [r for r in s["results"] if r["verdict"] != "pass"]
        if fails:
            st.markdown("**Failures**")
            for r in fails:
                st.markdown(f'`{r["test_id"]}` **{r["title"]}** — {r["message"]}')
        else:
            st.success("All executed tests passed.")
        with st.expander(f"Run history ({len(runs)})"):
            for r in reversed(runs):
                s2 = r["summary"]
                st.caption(f"{r['run_id']} · {s2['target']} · {s2['passed']}/{s2['total']} passed"
                          + (f" · faults: {', '.join(s2['faults'])}" if s2['faults'] else ""))


def page_export():
    global user, role, proj, profile
    setup_sidebar()
    tests = store.list_tests(proj)
    approved = [t for t in tests if t.status == "approved"]
    st.markdown("### Export")
    st.caption(f"{len(approved)} approved test(s) available to export.")
    fmt = st.selectbox("Format", ["python", "capl", "json", "csv", "markdown"],
                       format_func=lambda f: {
                           "python": "Python (pytest)", "capl": "CAPL (CANoe template)",
                           "json": "JSON", "csv": "CSV", "markdown": "Markdown spec"
                       }[f])
    approved_only = st.checkbox("Approved tests only", value=True)
    pool = approved if approved_only else tests
    if pool and profile:
        files = export_all(fmt, profile, pool)
        for name, content in files.items():
            st.download_button(f"⬇ Download {name}", content, file_name=name, use_container_width=False)
        if fmt == "capl":
            st.caption("uds_helpers.cin is a binding stub — wire it to your CANoe diagnostic layer before use.")
    else:
        st.info("No tests available with the current filter.")


def page_audit():
    global user, role, proj, profile
    setup_sidebar()
    if role not in ("lead", "admin"):
        st.info("Audit log requires the lead or admin role.")
        return
    st.markdown("### Audit log")
    log = store.audit_log(proj)
    for e in reversed(log[-300:]):
        st.caption(f"`{e['user']}` ({e['role']}) — **{e['action']}** {e['detail']}")


# ================================================================================================
# NAVIGATION
# ================================================================================================
# Declare globals used inside page functions
user: str = "engineer1"
role: str = "engineer"
proj: str | None = None
profile = None

pg = st.navigation({
    "Product": [
        st.Page(page_home, title="Home", icon="🏠", default=True),
    ],
    "Platform": [
        st.Page(page_knowledge, title="Knowledge Base", icon="📚"),
        st.Page(page_sandbox, title="Sandbox", icon="🧪"),
        st.Page(page_generate, title="Generate Tests", icon="⚡"),
        st.Page(page_review, title="Review", icon="👀"),
        st.Page(page_execute, title="Execute", icon="▶️"),
        st.Page(page_export, title="Export", icon="💾"),
        st.Page(page_audit, title="Audit", icon="📋"),
    ]
})

pg.run()
