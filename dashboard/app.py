"""
dashboard/app.py — Technical Debt Archaeologist
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from models import AnalysisResult  # noqa: E402

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def _fmt_date(dt) -> str:
    return f"{_MONTHS[dt.month - 1]} {dt.day}"

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Debt Archaeologist",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ── Variables ── */
:root {
    --bg:      #08090a;
    --s1:      #0f1012;
    --s2:      #16181c;
    --s3:      #1e2024;
    --bd:      #1d2026;
    --bd2:     #2a2e38;
    --text:    #e8eaf0;
    --text2:   #6b7385;
    --text3:   #383d4a;
    --accent:  #7c6dfa;
    --green:   #2dd4a0;
    --yellow:  #f5c842;
    --orange:  #f87c3d;
    --red:     #f06060;
    --r:       6px;
    --mono:    'JetBrains Mono', ui-monospace, monospace;
    --sans:    'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMain"], .main {
    background: var(--bg) !important;
    color: var(--text);
    font-family: var(--sans);
    -webkit-font-smoothing: antialiased;
}

/* ── Hide ALL Streamlit chrome ── */
#MainMenu,
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarHeader"],
[data-testid="stStatusWidget"],
[data-testid="stActionButton"],
footer,
.stDeployButton {
    display: none !important;
}

/* ── Main content padding ── */
.block-container {
    padding: 2rem 2.5rem 5rem !important;
    max-width: 1440px !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--s1) !important;
    border-right: 1px solid var(--bd) !important;
    min-width: 240px !important;
    max-width: 260px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 1.8rem 1.1rem 1.5rem !important;
}

/* Sidebar text inputs */
[data-testid="stSidebar"] input {
    background: var(--s2) !important;
    border: 1px solid var(--bd) !important;
    border-radius: var(--r) !important;
    color: var(--text) !important;
    font-family: var(--sans) !important;
    font-size: 12.5px !important;
    padding: 7px 10px !important;
    transition: border-color .15s !important;
}
[data-testid="stSidebar"] input:focus {
    border-color: var(--accent) !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(124,109,250,.15) !important;
}

/* Sidebar labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stTextInput label {
    color: var(--text2) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    letter-spacing: .01em !important;
}

/* Sidebar primary button */
[data-testid="stSidebar"] .stButton > button {
    background: var(--accent) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--r) !important;
    font-family: var(--sans) !important;
    font-size: 12.5px !important;
    font-weight: 600 !important;
    padding: 8px 14px !important;
    width: 100% !important;
    letter-spacing: .01em !important;
    transition: filter .15s, transform .1s !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    filter: brightness(1.12) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stSidebar"] .stButton > button:active {
    transform: translateY(0) !important;
}

/* Sidebar secondary button (Load) */
[data-testid="stSidebar"] .stButton:last-of-type > button {
    background: var(--s2) !important;
    border: 1px solid var(--bd) !important;
    color: var(--text2) !important;
}
[data-testid="stSidebar"] .stButton:last-of-type > button:hover {
    border-color: var(--bd2) !important;
    color: var(--text) !important;
}

/* Sidebar selectbox */
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: var(--s2) !important;
    border: 1px solid var(--bd) !important;
    border-radius: var(--r) !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
    color: var(--text2) !important;
    font-size: 12px !important;
    background: transparent !important;
}

/* Slider */
[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"] {
    background: var(--accent) !important;
    border: 2px solid var(--accent) !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] div[data-testid] {
    color: var(--text2) !important;
    font-size: 12px !important;
}

/* ── Divider ── */
.hr { height: 1px; background: var(--bd); margin: 16px 0; }

/* ── Section label ── */
.sec {
    font-size: 10px; font-weight: 700; color: var(--text3);
    text-transform: uppercase; letter-spacing: .14em;
    padding: 20px 0 10px;
}

/* ── Stat strip ── */
.stat-strip {
    display: grid; grid-template-columns: repeat(5,1fr);
    border: 1px solid var(--bd); border-radius: var(--r);
    overflow: hidden; margin-bottom: 1.4rem;
}
.stat-cell {
    background: var(--s1); padding: 16px 18px;
    border-right: 1px solid var(--bd); position: relative;
}
.stat-cell:last-child { border-right: none; }
.stat-top { height: 2px; position: absolute; top: 0; left: 0; right: 0; }
.stat-n {
    font-family: var(--mono); font-size: 24px; font-weight: 600;
    color: var(--text); letter-spacing: -.03em; line-height: 1; margin-bottom: 5px;
}
.stat-l { font-size: 10.5px; font-weight: 500; color: var(--text2); text-transform: uppercase; letter-spacing: .07em; }
.stat-s { font-size: 10px; color: var(--text3); margin-top: 3px; font-family: var(--mono); }
.c-red    { color: var(--red) !important; }
.c-orange { color: var(--orange) !important; }
.c-yellow { color: var(--yellow) !important; }
.c-green  { color: var(--green) !important; }
.c-accent { color: var(--accent) !important; }
.b-red    { background: var(--red); }
.b-orange { background: var(--orange); }
.b-yellow { background: var(--yellow); }
.b-green  { background: var(--green); }
.b-accent { background: var(--accent); }

/* ── Summary bar ── */
.sum-bar {
    background: var(--s1); border: 1px solid var(--bd);
    border-left: 2px solid var(--accent);
    border-radius: var(--r); padding: 10px 14px;
    font-size: 13px; color: var(--text2); line-height: 1.6;
    margin-bottom: 1.4rem;
}

/* ── Page header ── */
.ph {
    display: flex; align-items: flex-start; justify-content: space-between;
    border-bottom: 1px solid var(--bd); padding-bottom: 1.2rem; margin-bottom: 1.4rem;
}
.ph-brand {
    font-family: var(--mono); font-size: 10px; font-weight: 600;
    color: var(--text3); letter-spacing: .14em; text-transform: uppercase;
    margin-bottom: 4px;
}
.ph-repo {
    font-size: 20px; font-weight: 700; color: var(--text);
    letter-spacing: -.02em; line-height: 1.1; margin-bottom: 4px;
}
.ph-meta { font-size: 11.5px; color: var(--text3); }
.ph-meta b { color: var(--text2); font-weight: 500; }

/* ── Chart card ── */
.cc {
    background: var(--s1); border: 1px solid var(--bd);
    border-radius: var(--r); padding: 14px 14px 6px; overflow: hidden;
}
.cc-t {
    font-size: 10px; font-weight: 700; color: var(--text3);
    text-transform: uppercase; letter-spacing: .11em; margin-bottom: 8px;
}

/* ── Insight rows ── */
.ir {
    display: grid; grid-template-columns: 2px 1fr;
    background: var(--s1); border: 1px solid var(--bd);
    border-radius: var(--r); overflow: hidden; margin-bottom: 6px;
    transition: border-color .12s;
}
.ir:hover { border-color: var(--bd2); }
.ir-bar { }
.ir-body { padding: 10px 12px; }
.ir-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ir-period { font-family: var(--mono); font-size: 10.5px; color: var(--text3); }
.ir-score  { font-family: var(--mono); font-size: 11px; font-weight: 600; color: var(--text2); margin-left: auto; }
.ir-text   { font-size: 12px; color: var(--text2); line-height: 1.55; margin-bottom: 5px; }
.ir-hint   { font-size: 11.5px; color: var(--text); line-height: 1.5; padding: 1px 0; }
.ir-hint::before { content: '› '; color: var(--accent); }
.stag {
    font-size: 9px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; padding: 2px 6px; border-radius: 4px;
}
.st-critical { background: rgba(240,96,96,.12); color: var(--red); }
.st-high     { background: rgba(248,124,61,.12); color: var(--orange); }
.st-medium   { background: rgba(245,200,66,.12); color: var(--yellow); }
.st-low      { background: rgba(45,212,160,.12); color: var(--green); }

/* ── Pipeline progress ── */
.pipe {
    background: var(--s1); border: 1px solid var(--bd);
    border-radius: var(--r); padding: 16px 18px;
    font-family: var(--sans);
}
.pipe-hd {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px;
}
.pipe-title { font-size: 10px; font-weight: 700; color: var(--accent); letter-spacing: .14em; text-transform: uppercase; }
.pipe-repo  { font-family: var(--mono); font-size: 11px; color: var(--text3); }
.ps { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-top: 1px solid var(--s3); }
.ps:first-of-type { border-top: none; }
.ps-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ps-label-done    { font-size: 12px; color: var(--text2); }
.ps-label-run     { font-size: 12px; color: var(--text); font-weight: 500; }
.ps-label-wait    { font-size: 12px; color: var(--text3); }
.ps-tag { font-family: var(--mono); font-size: 10px; margin-left: auto; }
.ps-tag-done { color: var(--green); }
.ps-tag-run  { color: var(--accent); }
.pipe-log {
    margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--s3);
    font-family: var(--mono); font-size: 10.5px; color: var(--text3);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: var(--s1) !important;
    border: 1px solid var(--bd) !important;
    border-radius: var(--r) !important;
}
[data-testid="stExpander"] summary { color: var(--text2) !important; font-size: 12px !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bd2); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
SEV_COLOR = {"critical": "#f06060", "high": "#f87c3d", "medium": "#f5c842", "low": "#2dd4a0"}
SEV_BAR   = {"critical": "b-red",   "high": "b-orange", "medium": "b-yellow", "low": "b-green"}

_PLOT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,16,18,0.8)",
    font=dict(family="Inter, -apple-system, sans-serif", color="#6b7385", size=11),
    margin=dict(l=0, r=0, t=0, b=0),
    showlegend=False,
    height=210,
    xaxis=dict(
        gridcolor="rgba(255,255,255,0.025)", linecolor="#1d2026",
        tickfont=dict(size=10, color="#383d4a"), zeroline=False, title="",
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.025)", linecolor="#1d2026",
        tickfont=dict(size=10, color="#383d4a"), zeroline=False, title="",
    ),
)

# ─── Pipeline steps ───────────────────────────────────────────────────────────
_PIPE_STEPS = [
    {"key": "commits loaded",       "label": "Ingest commit history",     "done": False, "running": True},
    {"key": "[OK]  Commit quality", "label": "Score commit quality",      "done": False, "running": False},
    {"key": "[OK]  File churn",     "label": "Analyse file churn",        "done": False, "running": False},
    {"key": "[OK]  TODO density",   "label": "Track TODO/FIXME density",  "done": False, "running": False},
    {"key": "[OK]  PR patterns",    "label": "Extract PR patterns",       "done": False, "running": False},
    {"key": "[OK]  Velocity delta", "label": "Compute velocity windows",  "done": False, "running": False},
    {"key": "[OK]  Code complexity","label": "AST complexity analysis",   "done": False, "running": False},
    {"key": "[OK]  Bug correlation","label": "GitHub bug correlation",    "done": False, "running": False},
    {"key": "Analysis complete",    "label": "AI synthesis",              "done": False, "running": False},
    {"key": "Report saved",         "label": "Write report",              "done": False, "running": False},
]

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_reports() -> list[Path]:
    return sorted(_ROOT.glob("debt_report_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

def _load_report(path: Path) -> AnalysisResult:
    with open(path, encoding="utf-8") as f:
        return AnalysisResult.model_validate(json.load(f))

def _repo_name(url: str) -> str:
    return url.rstrip("/").split("/")[-1].replace(".git", "")

def _pipe_html(steps: list[dict], repo: str, last_line: str = "") -> str:
    rows = ""
    for s in steps:
        if s["done"]:
            dot   = '<div class="ps-dot" style="background:#2dd4a0"></div>'
            lbl   = f'<span class="ps-label-done">{s["label"]}</span>'
            tag   = '<span class="ps-tag ps-tag-done">done</span>'
        elif s["running"]:
            dot   = '<div class="ps-dot" style="background:#7c6dfa"></div>'
            lbl   = f'<span class="ps-label-run">{s["label"]}</span>'
            tag   = '<span class="ps-tag ps-tag-run">running</span>'
        else:
            dot   = '<div class="ps-dot" style="background:#1d2026;border:1px solid #2a2e38"></div>'
            lbl   = f'<span class="ps-label-wait">{s["label"]}</span>'
            tag   = ''
        rows += f'<div class="ps">{dot}{lbl}{tag}</div>'
    log = f'<div class="pipe-log">{last_line}</div>' if last_line else ""
    return (
        f'<div class="pipe">'
        f'<div class="pipe-hd"><span class="pipe-title">Pipeline</span>'
        f'<span class="pipe-repo">{repo}</span></div>'
        f'{rows}{log}</div>'
    )

def _run_with_progress(repo_url: str, max_commits: int, output_path: Path) -> tuple[bool, str]:
    steps   = deepcopy(_PIPE_STEPS)
    rname   = _repo_name(repo_url)
    slot    = st.empty()
    lines   = []

    proc = subprocess.Popen(
        [sys.executable, str(_ROOT / "main.py"),
         "--repo", repo_url, "--max-commits", str(max_commits), "--output", str(output_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=False,                   # binary — we decode manually below
        cwd=str(_ROOT),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    slot.markdown(_pipe_html(steps, rname), unsafe_allow_html=True)

    for raw_bytes in proc.stdout:
        raw = raw_bytes.decode("utf-8", errors="replace")
        line = raw.strip()
        if not line:
            continue
        lines.append(line)

        # When agents start (parallel), mark all 5 as running together
        if "step 2" in line.lower():
            for i in range(1, 6):
                steps[i]["running"] = True

        for i, s in enumerate(steps):
            if s["key"].lower() in line.lower() and not s["done"]:
                s["done"]    = True
                s["running"] = False
                if i + 1 < len(steps) and not steps[i + 1]["running"]:
                    steps[i + 1]["running"] = True
                break

        # Only show tqdm / progress lines in the log strip
        log_line = line if ("%" in line or "step" in line.lower() or "saved" in line.lower()) else (lines[-1] if lines else "")
        slot.markdown(_pipe_html(steps, rname, log_line), unsafe_allow_html=True)

    proc.wait()
    slot.empty()
    return proc.returncode == 0, "\n".join(lines)

def _stat_cell(num: str, label: str, sub: str = "", nc: str = "", bc: str = "") -> str:
    top = f'<div class="stat-top {bc}"></div>' if bc else ""
    return (
        f'<div class="stat-cell">{top}'
        f'<div class="stat-n {nc}">{num}</div>'
        f'<div class="stat-l">{label}</div>'
        + (f'<div class="stat-s">{sub}</div>' if sub else "")
        + "</div>"
    )

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<p style="font-family:var(--mono,monospace);font-size:10px;font-weight:700;'
        'color:#7c6dfa;letter-spacing:.16em;text-transform:uppercase;margin-bottom:2px">'
        'Debt Archaeologist</p>'
        '<p style="font-size:11px;color:#383d4a;margin-bottom:0">Technical debt intelligence</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    repo_url    = st.text_input("Repository URL", value="https://github.com/pallets/flask", placeholder="https://github.com/org/repo")
    max_commits = st.slider("Commit depth", 50, 2000, 500, step=50)
    st.markdown(f'<p style="font-size:10.5px;color:#383d4a;margin-top:-10px;margin-bottom:10px">{max_commits} commits</p>', unsafe_allow_html=True)
    run_btn = st.button("Run Analysis", use_container_width=True)

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    existing = _find_reports()
    load_btn, sel = False, None
    if existing:
        sel      = st.selectbox("Existing reports", [p.name for p in existing], label_visibility="visible")
        load_btn = st.button("Load report", use_container_width=True)
    else:
        st.markdown('<p style="font-size:11px;color:#383d4a">No reports yet. Run an analysis first.</p>', unsafe_allow_html=True)

# ─── Report resolution ────────────────────────────────────────────────────────
result: AnalysisResult | None = None

if run_btn and repo_url:
    rn       = _repo_name(repo_url)
    out_path = _ROOT / f"debt_report_{rn}.json"
    ok, log  = _run_with_progress(repo_url, max_commits, out_path)
    if ok and out_path.exists():
        result = _load_report(out_path)
        st.toast(f"{rn} analysis complete", icon=None)
    else:
        st.error("Analysis failed — check the log below.")
        with st.expander("Pipeline output"):
            st.code(log)
        st.stop()

elif load_btn and sel:
    result = _load_report(_ROOT / sel)

# ─── Empty state ──────────────────────────────────────────────────────────────
if result is None:
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                min-height:76vh;gap:12px;text-align:center;user-select:none">
        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700;
                    color:#7c6dfa;letter-spacing:.22em;text-transform:uppercase;margin-bottom:4px">
            Debt Archaeologist
        </div>
        <div style="font-size:26px;font-weight:700;color:#e8eaf0;letter-spacing:-.03em;line-height:1.25">
            Technical debt intelligence<br>for engineering teams
        </div>
        <div style="font-size:13px;color:#6b7385;max-width:360px;line-height:1.75;margin-top:2px">
            Analyses your commit history to surface exactly where
            debt accumulated — and what to do about it.
        </div>
        <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;justify-content:center">
            <span style="background:#0f1012;border:1px solid #1d2026;border-radius:5px;
                         padding:4px 11px;font-size:11px;color:#6b7385">Commit quality</span>
            <span style="background:#0f1012;border:1px solid #1d2026;border-radius:5px;
                         padding:4px 11px;font-size:11px;color:#6b7385">Velocity delta</span>
            <span style="background:#0f1012;border:1px solid #1d2026;border-radius:5px;
                         padding:4px 11px;font-size:11px;color:#6b7385">File churn</span>
            <span style="background:#0f1012;border:1px solid #1d2026;border-radius:5px;
                         padding:4px 11px;font-size:11px;color:#6b7385">TODO drift</span>
            <span style="background:#0f1012;border:1px solid #1d2026;border-radius:5px;
                         padding:4px 11px;font-size:11px;color:#6b7385">AI synthesis</span>
        </div>
        <p style="font-size:11px;color:#2a2e38;margin-top:6px">Enter a repo URL in the sidebar to begin</p>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ─── Build DataFrame ──────────────────────────────────────────────────────────
events = result.debt_events
df = pd.DataFrame([{
    "label":   _fmt_date(e.period_start),
    "debt":    e.debt_score,
    "vel":     e.velocity_score or 0.0,
    "qual":    e.commit_quality_avg or 0.0,
    "todos":   e.todo_delta or 0,
    "sev":     e.severity.value,
    "pr":      e.pr_merge_count or 0,
} for e in events])

sev_counts = df["sev"].value_counts().to_dict()
high_crit  = sev_counts.get("critical", 0) + sev_counts.get("high", 0)
net_todos  = int(df["todos"].clip(lower=0).sum())
score      = result.overall_debt_score
sc_nc      = "c-red" if score >= 60 else ("c-orange" if score >= 35 else ("c-yellow" if score >= 15 else "c-green"))
sc_bc      = "b-red" if score >= 60 else ("b-orange" if score >= 35 else ("b-yellow" if score >= 15 else "b-green"))

# ─── Page header ─────────────────────────────────────────────────────────────
ts = result.analysis_timestamp.strftime("%d %b %Y %H:%M UTC")
st.markdown(f"""
<div class="ph">
  <div>
    <div class="ph-brand">Debt Archaeologist</div>
    <div class="ph-repo">{result.repo_name}</div>
    <div class="ph-meta">
      <b>{result.repo_url}</b>
      &nbsp;·&nbsp; {result.total_commits_analyzed:,} commits
      &nbsp;·&nbsp; {len(events)} windows
      &nbsp;·&nbsp; {ts}
    </div>
  </div>
</div>""", unsafe_allow_html=True)

st.markdown(f'<div class="sum-bar">{result.executive_summary}</div>', unsafe_allow_html=True)

# ─── Stat strip ───────────────────────────────────────────────────────────────
st.markdown(
    '<div class="stat-strip">'
    + _stat_cell(f"{score:.1f}", "Debt Score", "/ 100", sc_nc, sc_bc)
    + _stat_cell(f"{result.total_commits_analyzed:,}", "Commits", f"{len(events)} windows")
    + _stat_cell(f"{df['vel'].max():.2f}", "Peak velocity", "0 – 1", "c-accent", "b-accent")
    + _stat_cell(str(net_todos), "Net TODOs", "added", "c-yellow" if net_todos > 0 else "c-green", "b-yellow" if net_todos > 0 else "b-green")
    + _stat_cell(str(high_crit), "High / critical", f"of {len(events)} windows", "c-red" if high_crit else "c-green", "b-red" if high_crit else "b-green")
    + "</div>",
    unsafe_allow_html=True,
)

# ─── Debt timeline ────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Debt score — bi-weekly windows</div>', unsafe_allow_html=True)
st.markdown('<div class="cc">', unsafe_allow_html=True)
fig_tl = go.Figure(go.Bar(
    x=df["label"], y=df["debt"],
    marker=dict(color=[SEV_COLOR.get(s, "#7c6dfa") for s in df["sev"]], line=dict(width=0), opacity=0.88),
    hovertemplate="<b>%{x}</b><br>Score: %{y:.1f}<extra></extra>",
))
fig_tl.update_layout(**{**_PLOT, "height": 185, "bargap": 0.38,
    "yaxis": {**_PLOT["yaxis"], "range": [0, 105]},
})
st.plotly_chart(fig_tl, use_container_width=True, config={"displayModeBar": False})
st.markdown('</div>', unsafe_allow_html=True)

# ─── Signal row ───────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Signals</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3, gap="small")

def _area(y_col, color, alpha=0.08):
    fig = go.Figure(go.Scatter(
        x=df["label"], y=df[y_col], mode="lines+markers",
        line=dict(color=color, width=2, shape="spline"),
        marker=dict(size=3.5, color=color),
        fill="tozeroy", fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},{alpha})",
        hovertemplate="%{x}: <b>%{y:.2f}</b><extra></extra>",
    ))
    fig.update_layout(**{**_PLOT, "yaxis": {**_PLOT["yaxis"], "range": [0, 1.06]}})
    return fig

with c1:
    st.markdown('<div class="cc"><div class="cc-t">Development velocity</div>', unsafe_allow_html=True)
    st.plotly_chart(_area("vel",  "#7c6dfa"), use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="cc"><div class="cc-t">Commit quality</div>', unsafe_allow_html=True)
    st.plotly_chart(_area("qual", "#2dd4a0"), use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c3:
    st.markdown('<div class="cc"><div class="cc-t">TODO / FIXME drift</div>', unsafe_allow_html=True)
    fig_td = go.Figure(go.Bar(
        x=df["label"], y=df["todos"],
        marker=dict(color=["#f06060" if v > 0 else "#2dd4a0" for v in df["todos"]],
                    line=dict(width=0), opacity=0.82),
        hovertemplate="%{x}: <b>%{y:+d}</b><extra></extra>",
    ))
    fig_td.update_layout(**{**_PLOT, "bargap": 0.42})
    st.plotly_chart(fig_td, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# ─── Hotspots ─────────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Hotspots</div>', unsafe_allow_html=True)
c4, c5 = st.columns([3, 2], gap="small")

with c4:
    st.markdown('<div class="cc"><div class="cc-t">Top churned files</div>', unsafe_allow_html=True)
    fc: Counter = Counter()
    for e in events:
        for f in e.top_churned_files:
            fc[f] += 1
    if fc:
        top = fc.most_common(8)
        fdf = pd.DataFrame(top, columns=["file", "n"])
        fdf["short"] = fdf["file"].apply(lambda p: "/".join(p.split("/")[-2:]) if "/" in p else p)
        fig_f = go.Figure(go.Bar(
            x=fdf["n"], y=fdf["short"], orientation="h",
            marker=dict(color="#7c6dfa", opacity=0.55, line=dict(width=0)),
            hovertemplate="<b>%{y}</b><br>%{x} windows<extra></extra>",
        ))
        fig_f.update_layout(**{**_PLOT, "height": 230,
            "yaxis": {**_PLOT["yaxis"], "autorange": "reversed"},
        })
        st.plotly_chart(fig_f, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c5:
    st.markdown('<div class="cc"><div class="cc-t">Severity distribution</div>', unsafe_allow_html=True)
    fig_d = go.Figure(go.Pie(
        labels=["Critical","High","Medium","Low"],
        values=[sev_counts.get(s, 0) for s in ["critical","high","medium","low"]],
        hole=0.65,
        marker=dict(colors=[SEV_COLOR[s] for s in ["critical","high","medium","low"]],
                    line=dict(color="#08090a", width=2)),
        textfont=dict(size=11, color="#e8eaf0"),
        hovertemplate="<b>%{label}</b>: %{value} windows<extra></extra>",
    ))
    fig_d.update_layout(**{**_PLOT, "height": 230, "showlegend": True,
        "legend": dict(orientation="v", x=0.7, y=0.5, xanchor="left",
                       font=dict(color="#6b7385", size=11), bgcolor="rgba(0,0,0,0)"),
    })
    st.plotly_chart(fig_d, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# ─── Remediation ──────────────────────────────────────────────────────────────
st.markdown('<div class="sec">Remediation — top debt windows</div>', unsafe_allow_html=True)
cols = st.columns(2, gap="small")
worst = sorted(events, key=lambda e: e.debt_score, reverse=True)[:6]
for i, e in enumerate(worst):
    sev    = e.severity.value
    bar_c  = SEV_COLOR.get(sev, "#7c6dfa")
    period = f"{_fmt_date(e.period_start)} – {_fmt_date(e.period_end)}, {e.period_end.year}"
    hints  = "".join(f'<div class="ir-hint">{h}</div>' for h in (e.remediation_hints or ["No hints."]))
    cols[i % 2].markdown(
        f'<div class="ir">'
        f'<div class="ir-bar" style="background:{bar_c}"></div>'
        f'<div class="ir-body">'
        f'<div class="ir-head">'
        f'<span class="stag st-{sev}">{sev}</span>'
        f'<span class="ir-period">{period}</span>'
        f'<span class="ir-score">{e.debt_score:.1f}</span>'
        f'</div>'
        f'<div class="ir-text">{e.summary}</div>'
        f'{hints}</div></div>',
        unsafe_allow_html=True,
    )

# ─── Benchmark percentile ─────────────────────────────────────────────────────
if result.benchmark_percentile is not None:
    perc = result.benchmark_percentile
    rank = 100 - perc
    bar_w = max(4, int(rank))
    bar_c = "#f06060" if rank < 30 else ("#f5c842" if rank < 60 else "#2dd4a0")
    st.markdown('<div class="sec">Benchmark — vs reference repos</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="cc" style="padding:16px 18px">
        <div style="display:flex;justify-content:space-between;margin-bottom:10px">
            <span style="font-size:12px;color:#6b7385">
                This repo scores better than
                <span style="color:{bar_c};font-weight:600;font-family:var(--mono)">{rank:.0f}%</span>
                of analysed Python repositories
            </span>
            <span style="font-family:var(--mono);font-size:11px;color:#383d4a">p{perc:.0f} percentile</span>
        </div>
        <div style="height:6px;background:#1d2026;border-radius:3px;overflow:hidden">
            <div style="height:100%;width:{bar_w}%;background:{bar_c};border-radius:3px;transition:width .3s"></div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:6px">
            <span style="font-size:10px;color:#383d4a">p10 (best)</span>
            <span style="font-size:10px;color:#383d4a">p90 (worst)</span>
        </div>
    </div>""", unsafe_allow_html=True)

# ─── Code complexity ──────────────────────────────────────────────────────────
if result.code_complexity:
    st.markdown('<div class="sec">Code complexity — AST analysis (current HEAD)</div>', unsafe_allow_html=True)
    cc_df = pd.DataFrame([{
        "file":     r.filepath.split("/")[-1],
        "path":     "/".join(r.filepath.split("/")[-2:]) if "/" in r.filepath else r.filepath,
        "avg_cc":   r.avg_cyclomatic_complexity,
        "max_cc":   r.max_cyclomatic_complexity,
        "funcs":    r.num_functions,
        "score":    r.complexity_score,
    } for r in result.code_complexity[:12]])

    c_a, c_b = st.columns([3, 2], gap="small")
    with c_a:
        st.markdown('<div class="cc"><div class="cc-t">Most complex files (avg cyclomatic complexity)</div>', unsafe_allow_html=True)
        fig_cc = go.Figure(go.Bar(
            x=cc_df["avg_cc"], y=cc_df["path"], orientation="h",
            marker=dict(
                color=cc_df["score"],
                colorscale=[[0,"#2dd4a0"],[0.5,"#f5c842"],[1,"#f06060"]],
                cmin=0, cmax=1, line=dict(width=0), opacity=0.85,
            ),
            hovertemplate="<b>%{y}</b><br>Avg CC: %{x:.1f}<extra></extra>",
        ))
        fig_cc.update_layout(**{**_PLOT, "height": 260,
            "yaxis": {**_PLOT["yaxis"], "autorange": "reversed"},
            "xaxis": {**_PLOT["xaxis"], "title": "Avg cyclomatic complexity"},
        })
        st.plotly_chart(fig_cc, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with c_b:
        avg_score = sum(r.complexity_score for r in result.code_complexity) / len(result.code_complexity)
        worst = result.code_complexity[0]
        st.markdown(f"""
        <div class="cc" style="height:100%">
            <div class="cc-t">Summary</div>
            <div style="display:flex;flex-direction:column;gap:10px;padding-top:4px">
                <div>
                    <div style="font-family:var(--mono);font-size:22px;font-weight:600;color:#f5c842">{avg_score:.2f}</div>
                    <div style="font-size:11px;color:#6b7385">avg complexity score (0=simple, 1=complex)</div>
                </div>
                <div style="height:1px;background:#1d2026"></div>
                <div>
                    <div style="font-size:11px;color:#383d4a;margin-bottom:4px">Most complex file</div>
                    <div style="font-family:var(--mono);font-size:11px;color:#e8eaf0">{worst.filepath.split("/")[-1]}</div>
                    <div style="font-size:11px;color:#6b7385">max CC: {worst.max_cyclomatic_complexity} &nbsp;·&nbsp; {worst.num_functions} functions</div>
                    {'<div style="margin-top:6px">' + "".join(f'<span style="background:#1d2026;border:1px solid #2a2e38;border-radius:4px;padding:1px 6px;font-size:10px;color:#f06060;margin-right:4px;font-family:var(--mono)">{fn}()</span>' for fn in worst.complex_functions[:3]) + '</div>' if worst.complex_functions else ""}
                </div>
            </div>
        </div>""", unsafe_allow_html=True)

# ─── Author attribution ───────────────────────────────────────────────────────
if result.author_records:
    st.markdown('<div class="sec">Author attribution — debt contribution by engineer</div>', unsafe_allow_html=True)
    auth_df = pd.DataFrame([{
        "Author":        r.author_name,
        "Commits":       r.commit_count,
        "Avg Quality":   round(r.avg_quality_score, 2),
        "High-Churn":    r.high_churn_commits,
        "TODOs Added":   r.todo_introduced,
        "Debt Score":    round(r.debt_contribution_score, 2),
    } for r in result.author_records[:15]])

    def _color_debt(val):
        if val >= 0.6: return "color: #f06060"
        if val >= 0.35: return "color: #f5c842"
        return "color: #2dd4a0"

    with st.expander(f"Show {len(result.author_records)} contributors", expanded=True):
        st.dataframe(
            auth_df.style
                .map(_color_debt, subset=["Debt Score"])
                .format({"Avg Quality": "{:.2f}", "Debt Score": "{:.2f}"}),
            use_container_width=True, hide_index=True,
        )

# ─── Bug correlation ──────────────────────────────────────────────────────────
if result.bug_density and any(r.bugs_opened > 0 for r in result.bug_density):
    st.markdown('<div class="sec">Bug correlation — GitHub issues vs debt windows</div>', unsafe_allow_html=True)
    bug_df = pd.DataFrame([{
        "label":  _fmt_date(r.window_start),
        "opened": r.bugs_opened,
        "closed": r.bugs_closed,
    } for r in result.bug_density])

    st.markdown('<div class="cc"><div class="cc-t">Bug reports opened per window (from GitHub Issues)</div>', unsafe_allow_html=True)
    fig_bug = go.Figure()
    fig_bug.add_trace(go.Bar(
        x=bug_df["label"], y=bug_df["opened"], name="Opened",
        marker=dict(color="#f06060", opacity=0.75, line=dict(width=0)),
        hovertemplate="%{x}: <b>%{y} bugs opened</b><extra></extra>",
    ))
    fig_bug.add_trace(go.Bar(
        x=bug_df["label"], y=bug_df["closed"], name="Closed",
        marker=dict(color="#2dd4a0", opacity=0.75, line=dict(width=0)),
        hovertemplate="%{x}: <b>%{y} bugs closed</b><extra></extra>",
    ))
    fig_bug.update_layout(**{**_PLOT, "height": 200, "bargap": 0.35, "showlegend": True,
        "legend": dict(orientation="h", x=0, y=1.08, font=dict(color="#6b7385", size=11), bgcolor="rgba(0,0,0,0)"),
    })
    st.plotly_chart(fig_bug, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# ─── Raw table ────────────────────────────────────────────────────────────────
st.markdown('<div style="height:1px;background:#1d2026;margin:20px 0 0"></div>', unsafe_allow_html=True)
with st.expander("Raw event data"):
    st.dataframe(
        df.rename(columns={
            "label":"Window","sev":"Severity","debt":"Debt Score",
            "vel":"Velocity","qual":"Quality","todos":"TODOs","pr":"PRs"
        })[["Window","Severity","Debt Score","Velocity","Quality","TODOs","PRs"]]
        .style.format({"Debt Score":"{:.1f}","Velocity":"{:.2f}","Quality":"{:.2f}"}),
        use_container_width=True, hide_index=True,
    )
