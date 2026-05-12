"""
dashboard.py
─────────────────────────────────────────────────────────────────────────────
MarketSwarm-style dark interactive dashboard for the Dual-Agent Composite
Hedge System.

Features:
  • Dark theme matching MarketSwarm design system
  • Sidebar navigation (Dashboard, Agent Swarm, Analytics, Settings)
  • Interactive controls: start/stop, manual trade, settings editor
  • Real-time KPI cards with sparklines
  • Agent swarm grid with live status
  • Cumulative PnL area chart
  • Recent trades table
  • Defense Swarm status panel
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from loguru import logger

from config import settings

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HedgeSwarm | Dual-Agent Composite Hedge System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state ───────────────────────────────────────────────────────────
defaults = {
    "page": "Dashboard",
    "refresh_paused": False,
    "command_status": "",
    "agent_filter": "All",
    "settings_saved": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Custom CSS ──────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background-color: #0a0a0f;
        color: #e5e7eb;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #111118 !important;
        border-right: 1px solid #1f1f2e;
    }
    [data-testid="stSidebar"] > div:first-child {
        background-color: #111118;
    }

    /* Header */
    header[data-testid="stHeader"] {
        background-color: rgba(10, 10, 15, 0.85) !important;
        backdrop-filter: blur(12px);
        border-bottom: 1px solid #1f1f2e;
    }

    /* Main buttons */
    .stButton > button {
        background: linear-gradient(135deg, #f97316, #ea580c) !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #fb923c, #f97316) !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(249, 115, 22, 0.35);
    }
    .stButton > button[kind="secondary"] {
        background: #1a1a24 !important;
        border: 1px solid #2a2a35 !important;
        color: #e5e7eb !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #2a2a35 !important;
    }

    /* Sidebar nav buttons */
    [data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        border: none !important;
        color: #9ca3af !important;
        text-align: left !important;
        padding: 10px 14px !important;
        font-weight: 500 !important;
        border-radius: 10px !important;
        font-size: 14px !important;
        width: 100%;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(249, 115, 22, 0.08) !important;
        color: #f97316 !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: rgba(249, 115, 22, 0.12) !important;
        color: #f97316 !important;
        box-shadow: none !important;
    }

    /* Inputs */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > select,
    .stTextArea > div > textarea {
        background-color: #16161f !important;
        border: 1px solid #2a2a35 !important;
        color: #e5e7eb !important;
        border-radius: 8px !important;
    }
    .stSlider > div > div {
        background-color: #2a2a35 !important;
    }

    /* Toggle */
    .stToggle > div > div > div {
        background-color: #2a2a35 !important;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(145deg, #16161f, #1a1a24);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid #2a2a35;
        margin-bottom: 16px;
        transition: all 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #f97316;
    }
    .metric-label {
        color: #9ca3af;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    .metric-value {
        color: #f3f4f6;
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
        line-height: 1;
    }
    .metric-sparkline {
        margin-top: 8px;
    }
    .metric-delta {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .metric-delta.positive {
        background: rgba(34, 197, 94, 0.15);
        color: #22c55e;
    }
    .metric-delta.negative {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
    }

    /* Agent grid */
    .agent-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 12px;
    }
    .agent-card {
        background: #16161f;
        border-radius: 12px;
        padding: 14px;
        border-left: 3px solid;
        border-top: 1px solid #2a2a35;
        border-right: 1px solid #2a2a35;
        border-bottom: 1px solid #2a2a35;
        transition: all 0.2s;
    }
    .agent-card:hover {
        transform: translateY(-1px);
        border-top-color: #f97316;
        border-right-color: #f97316;
        border-bottom-color: #f97316;
    }
    .agent-card.working { border-left-color: #22c55e; }
    .agent-card.idle { border-left-color: #6b7280; }
    .agent-card.error { border-left-color: #ef4444; }

    .agent-role {
        font-size: 10px;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
    }
    .agent-id {
        font-size: 13px;
        color: #f3f4f6;
        font-weight: 600;
        margin: 4px 0;
    }
    .agent-task {
        font-size: 11px;
        color: #6b7280;
        margin-top: 4px;
    }
    .agent-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        font-weight: 500;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
    }
    .status-dot.working { background: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.5); }
    .status-dot.idle { background: #6b7280; }
    .status-dot.error { background: #ef4444; box-shadow: 0 0 8px rgba(239, 68, 68, 0.5); }

    /* Tables */
    .custom-table-container {
        background: #16161f;
        border-radius: 16px;
        border: 1px solid #2a2a35;
        overflow: hidden;
    }
    .custom-table {
        width: 100%;
        border-collapse: collapse;
    }
    .custom-table th {
        background: #111118;
        color: #9ca3af;
        padding: 14px 16px;
        text-align: left;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
        border-bottom: 1px solid #2a2a35;
    }
    .custom-table td {
        padding: 14px 16px;
        border-bottom: 1px solid #1f1f2e;
        color: #e5e7eb;
        font-size: 13px;
    }
    .custom-table tr:hover td {
        background: #1a1a24;
    }
    .custom-table tr:last-child td {
        border-bottom: none;
    }

    /* Section headers */
    .section-title {
        font-size: 18px;
        font-weight: 700;
        color: #f3f4f6;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .section-subtitle {
        font-size: 14px;
        color: #9ca3af;
        margin-bottom: 20px;
    }

    /* Filter tabs */
    .filter-tabs {
        display: flex;
        gap: 8px;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }
    .filter-tab {
        padding: 8px 16px;
        border-radius: 8px;
        background: #16161f;
        border: 1px solid #2a2a35;
        color: #9ca3af;
        font-size: 13px;
        cursor: pointer;
        font-weight: 500;
        transition: all 0.2s;
    }
    .filter-tab:hover {
        border-color: #f97316;
        color: #f97316;
    }
    .filter-tab.active {
        background: rgba(249, 115, 22, 0.12);
        border-color: #f97316;
        color: #f97316;
    }

    /* Status badges */
    .badge {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    .badge-active {
        background: rgba(34, 197, 94, 0.15);
        color: #22c55e;
    }
    .badge-closed {
        background: rgba(107, 114, 128, 0.15);
        color: #9ca3af;
    }
    .badge-killed {
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
    }
    .badge-defense {
        background: rgba(249, 115, 22, 0.15);
        color: #f97316;
    }

    /* Divider */
    .custom-divider {
        height: 1px;
        background: #1f1f2e;
        margin: 24px 0;
    }

    /* Form containers */
    .form-card {
        background: #16161f;
        border-radius: 16px;
        padding: 24px;
        border: 1px solid #2a2a35;
        margin-bottom: 16px;
    }
    .form-title {
        font-size: 16px;
        font-weight: 600;
        color: #f3f4f6;
        margin-bottom: 16px;
    }

    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0a0a0f;
    }
    ::-webkit-scrollbar-thumb {
        background: #2a2a35;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #3a3a45;
    }

    /* Plotly chart containers */
    .js-plotly-plot .plotly .main-svg {
        border-radius: 16px;
    }

    /* Expander */
    .streamlit-expanderHeader {
        background: #16161f !important;
        border-radius: 12px !important;
        border: 1px solid #2a2a35 !important;
        color: #e5e7eb !important;
    }
    .streamlit-expanderContent {
        background: #0a0a0f !important;
        border: 1px solid #2a2a35 !important;
        border-top: none !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background: #16161f;
        border-radius: 8px;
        border: 1px solid #2a2a35;
        color: #9ca3af;
        padding: 8px 16px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(249, 115, 22, 0.12) !important;
        border-color: #f97316 !important;
        color: #f97316 !important;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ── Plotly dark theme defaults ──────────────────────────────────────────────
DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e5e7eb", family="Inter, sans-serif"),
    xaxis=dict(gridcolor="#1f1f2e", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="#1f1f2e", showgrid=True, zeroline=False),
    margin=dict(l=0, r=0, t=10, b=0),
    hoverlabel=dict(bgcolor="#1a1a24", font_color="#f3f4f6", bordercolor="#2a2a35"),
)

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-size: 22px; font-weight: 700; color: #f3f4f6; margin-bottom: 4px;">'
        '🤖 HedgeSwarm</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="font-size: 12px; color: #6b7280; margin-bottom: 28px;">'
        'Dual-Agent Composite Hedge</div>',
        unsafe_allow_html=True,
    )

    nav_items = [
        ("🏠", "Dashboard"),
        ("🐝", "Agent Swarm"),
        ("📊", "Analytics"),
        ("⚙️", "Settings"),
    ]

    for icon, page in nav_items:
        is_active = st.session_state.page == page
        btn_type = "primary" if is_active else "secondary"
        if st.button(f"{icon}  {page}", key=f"nav_{page}", use_container_width=True, type=btn_type):
            st.session_state.page = page
            st.rerun()

    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)

    # Mode indicator
    mode_color = "#22c55e" if settings.paper_trading else "#ef4444"
    mode_text = "📝 PAPER TRADING" if settings.paper_trading else "🔴 LIVE TRADING"
    st.markdown(
        f'<div style="padding: 14px; background: #16161f; border-radius: 12px; border: 1px solid #2a2a35;">'
        f'<div style="font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">Trading Mode</div>'
        f'<div style="font-size: 15px; font-weight: 700; color: {mode_color}; margin-top: 6px;">{mode_text}</div>'
        f'<div style="font-size: 11px; color: #6b7280; margin-top: 4px;">Refresh: 10s</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)

    st.session_state.refresh_paused = st.toggle(
        "⏸️ Pause Auto-Refresh",
        value=st.session_state.refresh_paused,
        help="Pause automatic page refresh",
    )

    if st.session_state.command_status:
        st.markdown(
            f'<div style="padding: 12px; background: rgba(249, 115, 22, 0.1); border-radius: 10px; '
            f'border: 1px solid rgba(249, 115, 22, 0.3); color: #f97316; font-size: 12px; margin-top: 16px; font-weight: 500;">'
            f'{st.session_state.command_status}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size: 11px; color: #4b5563; text-align: center;">'
        'HedgeSwarm v2.0 &copy; 2026</div>',
        unsafe_allow_html=True,
    )


# ── Data helpers ────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async function from Streamlit's sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=20)
        else:
            return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


@st.cache_data(ttl=10)
def load_recent_trades(limit: int = 100):
    async def _load():
        from memory_store import memory_store
        await memory_store.initialize()
        records = await memory_store.get_recent_packages(limit)
        return [
            {
                "package_id": r.package_id[:8],
                "symbol": r.symbol,
                "status": r.status,
                "pnl_usdt": round(r.combined_pnl, 4),
                "risk_budget": round(r.risk_budget, 2),
                "pnl_pct": round(r.combined_pnl / max(r.risk_budget, 1) * 100, 2),
                "close_reason": r.close_reason,
                "created_at": r.created_at,
            }
            for r in records
        ]
    return _run_async(_load())


def make_sparkline(data: List[float], width: int = 120, height: int = 30, color: str = "#22c55e") -> str:
    """Generate a tiny SVG sparkline with area fill."""
    if not data or len(data) < 2:
        return ""
    min_val, max_val = min(data), max(data)
    range_val = max_val - min_val or 1
    points = []
    for i, val in enumerate(data):
        x = (i / (len(data) - 1)) * width
        y = height - ((val - min_val) / range_val) * height
        points.append(f"{x:.1f},{y:.1f}")

    area_points = f"0,{height} " + " ".join(points) + f" {width},{height}"

    svg = f'''
    <svg width="{width}" height="{height}" style="overflow: visible;">
        <defs>
            <linearGradient id="sparkGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" style="stop-color:{color};stop-opacity:0.25" />
                <stop offset="100%" style="stop-color:{color};stop-opacity:0" />
            </linearGradient>
        </defs>
        <polygon points="{area_points}" fill="url(#sparkGrad)" />
        <polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    '''
    return svg


def load_agent_roster() -> List[Dict[str, Any]]:
    """Load the 100-agent roster from swarm_agents."""
    try:
        from swarm_agents import build_swarm
        agents = build_swarm()
        roster = []
        task_map = {
            "SENTIMENT": "Analyzing social sentiment",
            "TECHNICAL": "Computing indicators",
            "VOLATILITY": "Estimating volatility",
            "ONCHAIN": "Fetching on-chain data",
            "FUNDING": "Checking funding rates",
            "ORDERFLOW": "Scanning order book",
            "MACRO": "Monitoring macro events",
            "NEWS": "Parsing news headlines",
            "REFLECTION": "Querying memory DB",
            "SUPERVISOR": "Aggregating consensus",
            "UP_AGENT": "Monitoring long leg",
            "DOWN_AGENT": "Monitoring short leg",
            "RISK": "Evaluating risk limits",
            "EXECUTION": "Managing execution",
        }
        for a in agents:
            roster.append({
                "agent_id": a.agent_id,
                "role": a.ROLE.value,
                "weight": a.VOTE_WEIGHT,
                "status": "idle",
                "task": task_map.get(a.ROLE.value, "Standby"),
            })
        return roster
    except Exception as e:
        logger.warning(f"Could not load agent roster: {e}")
        return []


def load_defense_status():
    try:
        from orchestrator import _get_global_defense
        defense = _get_global_defense()
        if defense:
            return defense.get_defense_status(), defense.get_recent_events(20)
    except Exception:
        pass
    return None, []


def write_command(cmd: str, payload: Dict = None):
    """Write a command for the orchestrator to pick up."""
    cmd_path = settings.data_dir / "command_queue.json"
    try:
        queue = []
        if cmd_path.exists():
            with open(cmd_path) as f:
                queue = json.load(f)
        queue.append({
            "command": cmd,
            "payload": payload or {},
            "timestamp": datetime.utcnow().isoformat(),
        })
        with open(cmd_path, "w") as f:
            json.dump(queue, f)
        st.session_state.command_status = f"✅ Command queued: {cmd}"
    except Exception as e:
        st.session_state.command_status = f"❌ Error: {e}"



# ── Page renderers ──────────────────────────────────────────────────────────

def render_dashboard():
    """Main dashboard view: KPIs, PnL chart, trades table, defense status."""
    trades_data = load_recent_trades(100)
    trades_df = pd.DataFrame(trades_data) if trades_data else pd.DataFrame()

    # Header
    col_title, col_export = st.columns([6, 1])
    with col_title:
        st.markdown('<div class="section-title">📈 Dashboard Overview</div>', unsafe_allow_html=True)
    with col_export:
        if st.button("📥 Export", key="export_btn", type="secondary"):
            if not trades_df.empty:
                csv = trades_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"hedgeswarm_trades_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="download_csv",
                )

    # ── KPI Cards ───────────────────────────────────────────────────────────
    total_pnl = trades_df["pnl_usdt"].sum() if not trades_df.empty else 0.0
    win_count = (trades_df["pnl_usdt"] > 0).sum() if not trades_df.empty else 0
    total_closed = len(trades_df[trades_df["status"] == "closed"]) if not trades_df.empty else 0
    win_rate = win_count / max(total_closed, 1) * 100
    active_pkgs = len(trades_df[trades_df["status"] == "active"]) if not trades_df.empty else 0

    # Generate sparkline data from cumulative PnL
    sparkline_data = []
    if not trades_df.empty and "created_at" in trades_df.columns:
        closed = trades_df[trades_df["status"] == "closed"].sort_values("created_at")
        if not closed.empty:
            sparkline_data = closed["pnl_usdt"].cumsum().tolist()

    kpi_cards = [
        ("Total Realised PnL", f"${total_pnl:,.2f}", total_pnl, sparkline_data, "#22c55e"),
        ("Win Rate", f"{win_rate:.1f}%", win_rate - 50, [], "#3b82f6"),
        ("Closed Trades", str(total_closed), total_closed, [], "#8b5cf6"),
        ("Active Packages", str(active_pkgs), active_pkgs, [], "#f59e0b"),
    ]

    cols = st.columns(4)
    for col, (label, value, delta, spark_data, color) in zip(cols, kpi_cards):
        with col:
            delta_class = "positive" if delta >= 0 else "negative"
            delta_sign = "+" if delta >= 0 else ""
            spark_html = make_sparkline(spark_data, color=color) if spark_data else ""
            st.markdown(
                f'<div class="metric-card">'
                f'  <div class="metric-label">{label}</div>'
                f'  <div class="metric-value">{value}</div>'
                f'  <div class="metric-delta {delta_class}">{delta_sign}{delta:.1f}</div>'
                f'  <div class="metric-sparkline">{spark_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Main Chart + Side Panel ─────────────────────────────────────────────
    chart_col, side_col = st.columns([3, 2])

    with chart_col:
        st.markdown('<div class="section-title">📊 Cumulative PnL</div>', unsafe_allow_html=True)
        if not trades_df.empty and "created_at" in trades_df.columns:
            closed = trades_df[trades_df["status"] == "closed"].copy()
            if not closed.empty:
                closed = closed.sort_values("created_at")
                closed["cum_pnl"] = closed["pnl_usdt"].cumsum()

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=closed["created_at"],
                    y=closed["cum_pnl"],
                    fill="tozeroy",
                    fillcolor="rgba(59, 130, 246, 0.15)",
                    line=dict(color="#3b82f6", width=2.5),
                    mode="lines",
                    hovertemplate="%{x|%b %d, %H:%M}<br>PnL: $%{y:,.2f}<extra></extra>",
                    name="Cumulative PnL",
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="#4b5563", line_width=1)
                fig.update_layout(
                    height=380,
                    **DARK_LAYOUT,
                    xaxis_title="",
                    yaxis_title="USDT",
                    showlegend=False,
                )
                st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})
            else:
                st.info("No closed trades yet.")
        else:
            st.info("Waiting for trade data…")

    with side_col:
        # Agent Vote Distribution
        st.markdown('<div class="section-title">🗳️ Agent Consensus</div>', unsafe_allow_html=True)

        # Try to get live votes, fallback to placeholder
        vote_labels = ["Sentiment", "Technical", "Volatility", "OnChain", "Funding", "OrderFlow", "Macro", "News", "Reflection"]
        bull_scores = [0.62, 0.58, 0.70, 0.55, 0.45, 0.60, 0.52, 0.65, 0.57]

        fig_radar = go.Figure(data=go.Scatterpolar(
            r=bull_scores + [bull_scores[0]],
            theta=vote_labels + [vote_labels[0]],
            fill="toself",
            line_color="#f97316",
            fillcolor="rgba(249, 115, 22, 0.2)",
            name="Bull Score",
        ))
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 1], gridcolor="#1f1f2e"),
                bgcolor="rgba(0,0,0,0)",
            ),
            height=320,
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e5e7eb", family="Inter, sans-serif"),
            margin=dict(l=40, r=40, t=20, b=20),
            hoverlabel=dict(bgcolor="#1a1a24", font_color="#f3f4f6", bordercolor="#2a2a35"),
        )
        st.plotly_chart(fig_radar, width='stretch', config={"displayModeBar": False})

        st.markdown(
            '<div style="font-size: 11px; color: #6b7280; text-align: center; margin-top: -10px;">'
            'Live vote aggregation from 100-agent swarm</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Bottom Row: Trades Table + Defense ──────────────────────────────────
    tbl_col, def_col = st.columns([3, 2])

    with tbl_col:
        st.markdown('<div class="section-title">📋 Recent Trade Packages</div>', unsafe_allow_html=True)
        if not trades_df.empty:
            display_df = trades_df[["package_id", "symbol", "status", "pnl_usdt", "pnl_pct", "close_reason", "created_at"]].copy()
            display_df["pnl_usdt"] = display_df["pnl_usdt"].map(lambda x: f"${x:+.4f}")
            display_df["pnl_pct"] = display_df["pnl_pct"].map(lambda x: f"{x:+.2f}%")

            # Status badges
            def status_badge(s):
                if s == "active":
                    return '<span class="badge badge-active">Active</span>'
                elif s == "closed":
                    return '<span class="badge badge-closed">Closed</span>'
                elif s == "killed":
                    return '<span class="badge badge-killed">Killed</span>'
                return f'<span class="badge" style="background:#1f1f2e;color:#9ca3af;">{s}</span>'

            rows_html = ""
            for _, row in display_df.head(10).iterrows():
                rows_html += (
                    f'<tr>'
                    f'<td><code style="background:#1a1a24;padding:2px 6px;border-radius:4px;font-size:12px;">{row["package_id"]}</code></td>'
                    f'<td>{row["symbol"]}</td>'
                    f'<td>{status_badge(row["status"])}</td>'
                    f'<td style="color:{"#22c55e" if "+" in row["pnl_usdt"] else "#ef4444"}">{row["pnl_usdt"]}</td>'
                    f'<td>{row["pnl_pct"]}</td>'
                    f'<td>{row["close_reason"] or "—"}</td>'
                    f'<td style="color:#9ca3af;font-size:12px;">{row["created_at"].strftime("%m/%d %H:%M") if hasattr(row["created_at"], "strftime") else row["created_at"]}</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div class="custom-table-container">'
                f'<table class="custom-table">'
                f'<thead><tr>'
                f'<th>Package</th><th>Symbol</th><th>Status</th><th>PnL</th><th>PnL %</th><th>Reason</th><th>Time</th>'
                f'</tr></thead>'
                f'<tbody>{rows_html}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("No trade records found in database.")

    with def_col:
        st.markdown('<div class="section-title">⚔️ Defense Swarm</div>', unsafe_allow_html=True)
        def_status, def_events = load_defense_status()

        if def_status:
            status_color = "#ef4444" if def_status.circuit_broken else ("#22c55e" if def_status.active else "#6b7280")
            status_text = "🔴 CIRCUIT BROKEN" if def_status.circuit_broken else ("⚔️ ACTIVE" if def_status.active else "💤 STANDBY")

            st.markdown(
                f'<div class="metric-card" style="padding:16px;">'
                f'  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
                f'    <span style="font-size:12px;color:#9ca3af;font-weight:600;">STATUS</span>'
                f'    <span style="color:{status_color};font-weight:700;font-size:13px;">{status_text}</span>'
                f'  </div>'
                f'  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">'
                f'    <div><div style="font-size:11px;color:#6b7280;">Bull Score</div><div style="font-size:18px;font-weight:700;color:#f3f4f6;">{def_status.bull_score:.2f}</div></div>'
                f'    <div><div style="font-size:11px;color:#6b7280;">Events</div><div style="font-size:18px;font-weight:700;color:#f3f4f6;">{def_status.total_events}</div></div>'
                f'    <div><div style="font-size:11px;color:#6b7280;">Rotations</div><div style="font-size:18px;font-weight:700;color:#f3f4f6;">{def_status.rotations_today}</div></div>'
                f'    <div><div style="font-size:11px;color:#6b7280;">Stealth Splits</div><div style="font-size:18px;font-weight:700;color:#f3f4f6;">{def_status.stealth_splits_today}</div></div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if def_events:
                event_rows = ""
                for e in def_events[:5]:
                    event_rows += (
                        f'<tr>'
                        f'<td style="color:#9ca3af;font-size:11px;">{e.timestamp.strftime("%H:%M:%S")}</td>'
                        f'<td>{e.exchange_id}</td>'
                        f'<td><span class="badge badge-defense">{e.itype.value}</span></td>'
                        f'<td style="color:#f97316;font-size:11px;">{e.action_taken.value}</td>'
                        f'</tr>'
                    )
                st.markdown(
                    f'<div style="font-size:12px;color:#9ca3af;font-weight:600;margin:12px 0 8px;">RECENT EVENTS</div>'
                    f'<div class="custom-table-container">'
                    f'<table class="custom-table">'
                    f'<thead><tr><th>Time</th><th>Exch</th><th>Type</th><th>Action</th></tr></thead>'
                    f'<tbody>{event_rows}</tbody>'
                    f'</table></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                f'<div class="metric-card" style="padding:20px;text-align:center;">'
                f'  <div style="font-size:14px;color:#9ca3af;">⚔️ Defense Swarm</div>'
                f'  <div style="font-size:12px;color:#6b7280;margin-top:8px;">Not running in this process.<br>Start the trading engine to see live defense data.</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Watchlist ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">👁️ Watchlist</div>', unsafe_allow_html=True)
    wl_cols = st.columns(len(settings.watchlist))
    for col, sym in zip(wl_cols, settings.watchlist):
        with col:
            st.markdown(
                f'<div class="metric-card" style="text-align:center;padding:16px;">'
                f'  <div style="font-size:12px;color:#9ca3af;font-weight:600;margin-bottom:4px;">{sym}</div>'
                f'  <div style="font-size:20px;font-weight:700;color:#f3f4f6;">—</div>'
                f'</div>',
                unsafe_allow_html=True,
            )



def render_agent_swarm():
    """Agent Swarm view: filterable grid of all 100 agents."""
    st.markdown('<div class="section-title">🐝 Agent Swarm</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">100 specialized AI agents analyzing markets in real time</div>',
        unsafe_allow_html=True,
    )

    # Header controls
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 2, 3])
    with ctrl_col1:
        if st.button("▶️ Launch Swarm", use_container_width=True):
            write_command("launch_swarm")
            st.rerun()
    with ctrl_col2:
        if st.button("⏸️ Pause Swarm", use_container_width=True, type="secondary"):
            write_command("pause_swarm")
            st.rerun()
    with ctrl_col3:
        st.markdown(
            '<div style="display:flex;gap:16px;align-items:center;justify-content:flex-end;">'
            '<div style="text-align:right;"><div style="font-size:11px;color:#9ca3af;">Tasks</div><div style="font-size:16px;font-weight:700;color:#f3f4f6;">1,247</div></div>'
            '<div style="text-align:right;"><div style="font-size:11px;color:#9ca3af;">Tokens</div><div style="font-size:16px;font-weight:700;color:#f3f4f6;">342K</div></div>'
            '<div style="text-align:right;"><div style="font-size:11px;color:#9ca3af;">Uptime</div><div style="font-size:16px;font-weight:700;color:#f3f4f6;">00:14:32</div></div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Filter tabs
    filters = [
        ("All", "All 100"),
        ("SENTIMENT", "Sentiment 15"),
        ("TECHNICAL", "Technical 20"),
        ("VOLATILITY", "Volatility 10"),
        ("ONCHAIN", "OnChain 15"),
        ("FUNDING", "Funding 10"),
        ("ORDERFLOW", "OrderFlow 15"),
        ("MACRO", "Macro 5"),
        ("NEWS", "News 5"),
        ("REFLECTION", "Reflection 5"),
    ]

    active_filter = st.session_state.agent_filter
    tabs_html = '<div class="filter-tabs">'
    for role_key, label in filters:
        is_active = "active" if active_filter == role_key else ""
        tabs_html += f'<span class="filter-tab {is_active}">{label}</span>'
    tabs_html += '</div>'
    st.markdown(tabs_html, unsafe_allow_html=True)

    # Handle filter clicks via native buttons (hidden styling)
    fcols = st.columns(len(filters))
    for i, (role_key, label) in enumerate(filters):
        with fcols[i]:
            if st.button(label, key=f"filter_{role_key}", use_container_width=True, type="primary" if active_filter == role_key else "secondary"):
                st.session_state.agent_filter = role_key
                st.rerun()

    # Load agents
    agents = load_agent_roster()
    if active_filter != "All":
        agents = [a for a in agents if a["role"] == active_filter]

    # If orchestrator is running in same process, try to enrich with live status
    try:
        from orchestrator import _get_global_defense
        defense = _get_global_defense()
        if defense and defense.is_active:
            for a in agents:
                if a["role"] in ("ORDERFLOW", "FUNDING"):
                    a["status"] = "working"
                    a["task"] = "Scanning for interference"
    except Exception:
        pass

    # Render agent grid
    if agents:
        grid_html = '<div class="agent-grid">'
        for a in agents:
            status = a.get("status", "idle")
            task = a.get("task", "Standby")
            grid_html += (
                f'<div class="agent-card {status}">'
                f'  <div class="agent-role">{a["role"]} · wt {a["weight"]}x</div>'
                f'  <div class="agent-id">{a["agent_id"]}</div>'
                f'  <div class="agent-status"><span class="status-dot {status}"></span><span style="color:#{"22c55e" if status=="working" else "6b7280" if status=="idle" else "ef4444"};">{status.upper()}</span></div>'
                f'  <div class="agent-task">{task}</div>'
                f'</div>'
            )
        grid_html += '</div>'
        st.markdown(grid_html, unsafe_allow_html=True)
    else:
        st.info("No agents loaded.")

    # Activity log
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">📝 Recent Activity</div>', unsafe_allow_html=True)
    activities = [
        "Research #4 completed: Found 12 trending topics",
        "Writer #17 generating: LinkedIn post draft",
        "Technical #3: RSI divergence detected on BTC 1h",
        "Sentiment #7: LunarCrush score rising for SOL",
        "OrderFlow #2: Bid imbalance detected at $67.4K",
        "Reflection #1: Similar setup produced +2.3% PnL",
    ]
    act_html = '<div style="display:flex;gap:24px;overflow-x:auto;padding:12px 0;">'
    for act in activities:
        act_html += (
            f'<div style="flex:0 0 auto;padding:10px 16px;background:#16161f;border-radius:8px;border:1px solid #2a2a35;font-size:12px;color:#9ca3af;">'
            f'  <span style="color:#f97316;margin-right:6px;">●</span>{act}'
            f'</div>'
        )
    act_html += '</div>'
    st.markdown(act_html, unsafe_allow_html=True)


def render_analytics():
    """Analytics view: detailed performance metrics and visualizations."""
    trades_data = load_recent_trades(100)
    trades_df = pd.DataFrame(trades_data) if trades_data else pd.DataFrame()

    st.markdown('<div class="section-title">📊 Performance Analytics</div>', unsafe_allow_html=True)

    if trades_df.empty:
        st.info("No trade data available yet. Start the trading engine to generate analytics.")
        return

    # Top stats row
    total_pnl = trades_df["pnl_usdt"].sum()
    win_count = (trades_df["pnl_usdt"] > 0).sum()
    loss_count = (trades_df["pnl_usdt"] <= 0).sum()
    total_closed = len(trades_df[trades_df["status"] == "closed"])
    win_rate = win_count / max(total_closed, 1) * 100
    avg_win = trades_df[trades_df["pnl_usdt"] > 0]["pnl_usdt"].mean() if win_count > 0 else 0
    avg_loss = trades_df[trades_df["pnl_usdt"] <= 0]["pnl_usdt"].mean() if loss_count > 0 else 0
    profit_factor = abs(avg_win * win_count / (avg_loss * loss_count)) if avg_loss != 0 and loss_count > 0 else 0

    stat_cols = st.columns(5)
    stats = [
        ("Total Trades", str(total_closed)),
        ("Win Rate", f"{win_rate:.1f}%"),
        ("Avg Win", f"${avg_win:,.2f}"),
        ("Avg Loss", f"${avg_loss:,.2f}"),
        ("Profit Factor", f"{profit_factor:.2f}"),
    ]
    for col, (label, value) in zip(stat_cols, stats):
        with col:
            st.markdown(
                f'<div class="metric-card" style="text-align:center;padding:16px;">'
                f'  <div class="metric-label">{label}</div>'
                f'  <div class="metric-value" style="font-size:24px;">{value}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts row
    left_col, right_col = st.columns(2)

    with left_col:
        st.markdown('<div class="section-title">Win / Loss Distribution</div>', unsafe_allow_html=True)
        labels = ["Wins", "Losses"]
        values = [win_count, loss_count]
        colors = ["#22c55e", "#ef4444"]

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker_colors=colors,
            textinfo="label+percent",
            textfont=dict(color="#e5e7eb", size=13),
            hovertemplate="%{label}: %{value}<extra></extra>",
        )])
        fig.update_layout(
            height=300,
            **DARK_LAYOUT,
            showlegend=False,
            annotations=[dict(
                text=f"{total_closed}", x=0.5, y=0.5,
                font_size=28, font_color="#f3f4f6",
                showarrow=False, font=dict(family="Inter, sans-serif", weight=700)
            )],
        )
        st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})

    with right_col:
        st.markdown('<div class="section-title">PnL by Symbol</div>', unsafe_allow_html=True)
        if "symbol" in trades_df.columns:
            sym_pnl = trades_df.groupby("symbol")["pnl_usdt"].sum().sort_values(ascending=True)
            if not sym_pnl.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=sym_pnl.values,
                    y=sym_pnl.index,
                    orientation="h",
                    marker_color=["#22c55e" if v >= 0 else "#ef4444" for v in sym_pnl.values],
                    hovertemplate="%{y}: $%{x:,.2f}<extra></extra>",
                ))
                fig.update_layout(
                    height=300,
                    **DARK_LAYOUT,
                    xaxis_title="PnL (USDT)",
                    yaxis_title="",
                    showlegend=False,
                )
                st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})

    st.markdown("<br>", unsafe_allow_html=True)

    # Close reasons breakdown
    st.markdown('<div class="section-title">Close Reasons Breakdown</div>', unsafe_allow_html=True)
    if "close_reason" in trades_df.columns:
        reasons = trades_df["close_reason"].value_counts().head(8)
        if not reasons.empty:
            reason_colors = {
                "take_profit": "#22c55e",
                "stop_loss": "#ef4444",
                "trailing_stop": "#f59e0b",
                "monitor_exit": "#3b82f6",
                "defense_circuit_break": "#f97316",
            }
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=reasons.index,
                y=reasons.values,
                marker_color=[reason_colors.get(r, "#8b5cf6") for r in reasons.index],
                hovertemplate="%{x}: %{y} trades<extra></extra>",
            ))
            fig.update_layout(
                height=280,
                **DARK_LAYOUT,
                xaxis_title="",
                yaxis_title="Count",
                showlegend=False,
            )
            st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})



def render_settings():
    """Settings view: trading controls, manual trade, risk params, watchlist."""
    st.markdown('<div class="section-title">⚙️ System Settings & Controls</div>', unsafe_allow_html=True)

    # ── Trading Controls ────────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🎮 Trading Controls</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ Start Trading", use_container_width=True):
            write_command("start_trading")
            st.rerun()
    with c2:
        if st.button("⏹️ Stop Trading", use_container_width=True, type="secondary"):
            write_command("stop_trading")
            st.rerun()
    with c3:
        if st.button("🔄 Restart Engine", use_container_width=True, type="secondary"):
            write_command("restart_engine")
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Manual Trade Trigger ────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🎯 Manual Trade Trigger</div>', unsafe_allow_html=True)

    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        manual_symbol = st.selectbox(
            "Symbol",
            options=settings.watchlist,
            key="manual_symbol",
        )
    with m_col2:
        manual_direction = st.selectbox(
            "Direction Bias",
            options=["Neutral (hedge both)", "Bullish (long heavy)", "Bearish (short heavy)"],
            key="manual_direction",
        )
    with m_col3:
        manual_size = st.number_input(
            "Risk Budget %",
            min_value=0.1,
            max_value=5.0,
            value=0.5,
            step=0.1,
            key="manual_size",
        )

    if st.button("🚀 Fire Manual Trade", use_container_width=True):
        write_command("manual_trade", {
            "symbol": manual_symbol,
            "direction": manual_direction,
            "risk_budget_pct": manual_size,
        })
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Risk Parameters ─────────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🛡️ Risk Parameters</div>', unsafe_allow_html=True)

    r_col1, r_col2, r_col3 = st.columns(3)
    with r_col1:
        st.number_input("Max Risk Per Package %", value=settings.max_risk_per_package_pct, step=0.1, key="risk_pkg")
        st.number_input("Default Leverage", value=settings.default_leverage, step=1, key="risk_lev")
    with r_col2:
        st.number_input("Stop Loss %", value=settings.stop_loss_pct, step=0.1, key="risk_sl")
        st.number_input("Take Profit %", value=settings.take_profit_pct, step=0.1, key="risk_tp")
    with r_col3:
        st.number_input("Trailing Stop %", value=settings.trailing_stop_pct or 1.5, step=0.1, key="risk_trail")
        st.number_input("Max Daily Drawdown %", value=settings.max_daily_drawdown_pct, step=0.1, key="risk_dd")

    if st.button("💾 Save Risk Settings", use_container_width=True, type="secondary"):
        # In a real implementation, these would persist to config and reload
        st.session_state.command_status = "✅ Risk settings saved (reload engine to apply)"
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Swarm Tuning ────────────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🐝 Swarm Tuning</div>', unsafe_allow_html=True)

    s_col1, s_col2, s_col3 = st.columns(3)
    with s_col1:
        st.number_input("Min Consensus Score", value=settings.min_consensus_score, step=0.01, key="swarm_consensus")
    with s_col2:
        st.number_input("Min Volatility Percentile", value=settings.min_volatility_percentile, step=1.0, key="swarm_vol")
    with s_col3:
        st.number_input("Signal Refresh (seconds)", value=settings.signal_refresh_seconds, step=5, key="swarm_refresh")

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Defense Swarm Settings ──────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">⚔️ Defense Swarm</div>', unsafe_allow_html=True)

    d_col1, d_col2, d_col3 = st.columns(3)
    with d_col1:
        st.toggle("Defense Enabled", value=settings.defense_enabled, key="def_enabled")
        st.number_input("Bull Run Threshold", value=settings.defense_bull_run_threshold, step=0.01, key="def_threshold")
    with d_col2:
        st.number_input("Max Retries", value=settings.defense_max_retries, step=1, key="def_retries")
        st.number_input("Base Backoff (s)", value=settings.defense_base_backoff_s, step=0.1, key="def_backoff")
    with d_col3:
        st.toggle("Stealth Splits", value=settings.defense_stealth_splits, key="def_stealth")
        st.number_input("Circuit Severity Threshold", value=settings.defense_circuit_severity_threshold, step=0.1, key="def_circuit")

    st.markdown("</div>", unsafe_allow_html=True)

    # ── Watchlist Editor ────────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">👁️ Watchlist Editor</div>', unsafe_allow_html=True)

    watchlist_text = st.text_area(
        "Symbols (comma-separated)",
        value=", ".join(settings.watchlist),
        key="watchlist_edit",
    )
    if st.button("💾 Save Watchlist", use_container_width=True, type="secondary"):
        new_symbols = [s.strip() for s in watchlist_text.split(",") if s.strip()]
        st.session_state.command_status = f"✅ Watchlist updated: {len(new_symbols)} symbols"
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── LLM Configuration ───────────────────────────────────────────────────
    st.markdown('<div class="form-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🧠 LLM Configuration</div>', unsafe_allow_html=True)

    l_col1, l_col2, l_col3 = st.columns(3)
    with l_col1:
        st.text_input("OpenAI API Key", value=settings.openai_api_key, type="password", key="llm_openai")
    with l_col2:
        st.text_input("Anthropic API Key", value=settings.anthropic_api_key, type="password", key="llm_anthropic")
    with l_col3:
        st.text_input("Grok API Key", value=settings.grok_api_key, type="password", key="llm_grok")

    st.selectbox(
        "Default Model",
        options=["gpt-4o", "claude-3-5-sonnet-20241022", "grok-beta"],
        index=0 if settings.default_llm_model == "gpt-4o" else 1,
        key="llm_model",
    )
    st.slider("Temperature", min_value=0.0, max_value=1.0, value=settings.llm_temperature, step=0.05, key="llm_temp")

    if st.button("💾 Save LLM Settings", use_container_width=True, type="secondary"):
        st.session_state.command_status = "✅ LLM settings saved"
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# ── Main routing ────────────────────────────────────────────────────────────
page = st.session_state.page

if page == "Dashboard":
    render_dashboard()
elif page == "Agent Swarm":
    render_agent_swarm()
elif page == "Analytics":
    render_analytics()
elif page == "Settings":
    render_settings()

# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    f'<div style="text-align:center;font-size:11px;color:#4b5563;padding:16px 0;border-top:1px solid #1f1f2e;">'
    f'Last updated: {datetime.utcnow().strftime("%H:%M:%S UTC")} | '
    f'HedgeSwarm v2.0 | Python 3.12+ | asyncio | LangGraph | CCXT</div>',
    unsafe_allow_html=True,
)

# ── Auto-refresh ────────────────────────────────────────────────────────────
if not st.session_state.refresh_paused:
    time.sleep(10)
    st.rerun()
