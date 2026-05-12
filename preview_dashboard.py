"""
Generate a dashboard preview image + seed fake trade data.
"""
import asyncio
import json
import random
from datetime import datetime, timedelta

import aiosqlite
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.lines import Line2D

DB_PATH = "data/trades.db"


async def seed_data():
    import os
    os.makedirs("data", exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            package_id TEXT PRIMARY KEY,
            symbol TEXT,
            status TEXT,
            combined_pnl REAL DEFAULT 0.0,
            risk_budget REAL DEFAULT 0.0,
            close_reason TEXT DEFAULT '',
            consensus_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            notes TEXT DEFAULT '[]'
        )
    """)
    await conn.execute("DELETE FROM trades")

    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    statuses = ["closed", "closed", "closed", "closed", "closed", "active", "active"]
    reasons = ["take_profit", "stop_loss", "trailing_stop", "monitor_exit", "defense_circuit_break", "", ""]

    base = datetime.utcnow() - timedelta(days=3)
    records = []
    for i in range(14):
        sym = random.choice(symbols)
        status = statuses[i % len(statuses)] if i < 7 else "closed"
        pnl = round(random.uniform(-120, 280), 4)
        risk = round(random.uniform(800, 1500), 2)
        created = base + timedelta(hours=i * 4 + random.randint(0, 30))
        closed = created + timedelta(hours=random.randint(2, 12)) if status == "closed" else None
        reason = random.choice(reasons) if status == "closed" else ""
        records.append((
            f"pkg-{i:04d}-{random.randint(1000,9999)}",
            sym, status, pnl, risk, reason,
            json.dumps({"bull_score": round(random.uniform(0.4, 0.9), 2)}),
            created.isoformat(), closed.isoformat() if closed else None,
            json.dumps(["Auto-seeded"])
        ))

    await conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?)", records
    )
    await conn.commit()
    await conn.close()
    print(f"Seeded {len(records)} fake trades.")


def generate_preview():
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT package_id, symbol, status, combined_pnl, risk_budget, close_reason, created_at, closed_at FROM trades ORDER BY created_at",
        conn,
        parse_dates=["created_at", "closed_at"]
    )
    conn.close()

    # Compute KPIs
    total_pnl = df["combined_pnl"].sum()
    closed_df = df[df["status"] == "closed"]
    win_rate = (closed_df["combined_pnl"] > 0).sum() / max(len(closed_df), 1) * 100
    total_closed = len(closed_df)
    active_count = len(df[df["status"] == "active"])

    fig = plt.figure(figsize=(14, 16), facecolor="#0e1117")
    fig.patch.set_facecolor("#0e1117")
    gs = GridSpec(5, 6, figure=fig, hspace=0.35, wspace=0.4,
                  height_ratios=[0.08, 0.22, 0.25, 0.22, 0.23])

    def dark_text(ax, text, y=0.5, size=12, color="#fafafa", weight="normal"):
        ax.text(0.5, y, text, ha="center", va="center", fontsize=size,
                color=color, weight=weight, transform=ax.transAxes)
        ax.set_facecolor("#0e1117")
        ax.axis("off")

    # ── Title ──────────────────────────────────────────────────────────
    ax_title = fig.add_subplot(gs[0, :])
    dark_text(ax_title, "Dual-Agent Composite Hedge System", y=0.6, size=18, weight="bold")
    dark_text(ax_title, "Mode: PAPER TRADING  |  Refresh: 10s", y=0.15, size=10, color="#9ca3af")

    # ── KPI Row ────────────────────────────────────────────────────────
    kpi_labels = ["Total Realised PnL", "Win Rate", "Total Closed Trades", "Active Packages", "Paper Mode"]
    kpi_values = [f"${total_pnl:,.2f}", f"{win_rate:.1f}%", str(total_closed), str(active_count), "ON"]
    kpi_colors = ["#00cc88" if total_pnl >= 0 else "#ff4b4b", "#3b82f6", "#f59e0b", "#8b5cf6", "#9ca3af"]
    for i, (label, value, color) in enumerate(zip(kpi_labels, kpi_values, kpi_colors)):
        ax = fig.add_subplot(gs[1, i])
        ax.set_facecolor("#161b22")
        rect = FancyBboxPatch((0.05, 0.1), 0.9, 0.8, boxstyle="round,pad=0.02,rounding_size=0.15",
                              facecolor="#161b22", edgecolor="#30363d", transform=ax.transAxes)
        ax.add_patch(rect)
        ax.text(0.5, 0.65, value, ha="center", va="center", fontsize=16, color=color, weight="bold",
                transform=ax.transAxes)
        ax.text(0.5, 0.25, label, ha="center", va="center", fontsize=9, color="#9ca3af",
                transform=ax.transAxes)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    # ── Cumulative PnL Chart ───────────────────────────────────────────
    ax_cum = fig.add_subplot(gs[2, :4])
    ax_cum.set_facecolor("#0e1117")
    if not closed_df.empty:
        closed_df = closed_df.sort_values("created_at").copy()
        closed_df["cum_pnl"] = closed_df["combined_pnl"].cumsum()
        ax_cum.plot(closed_df["created_at"], closed_df["cum_pnl"], color="#00cc88", lw=2, marker="o", ms=4)
        ax_cum.axhline(0, color="#555", ls="--", lw=1)
        ax_cum.fill_between(closed_df["created_at"], closed_df["cum_pnl"], 0,
                            where=(closed_df["cum_pnl"] >= 0), color="#00cc88", alpha=0.15)
        ax_cum.fill_between(closed_df["created_at"], closed_df["cum_pnl"], 0,
                            where=(closed_df["cum_pnl"] < 0), color="#ff4b4b", alpha=0.15)
    ax_cum.set_title("Cumulative PnL", color="#fafafa", fontsize=12, loc="left", pad=10)
    ax_cum.tick_params(colors="#9ca3af", labelsize=8)
    ax_cum.spines[:].set_color("#30363d")
    ax_cum.xaxis.label.set_color("#9ca3af")
    ax_cum.yaxis.label.set_color("#9ca3af")

    # ── Recent Trades Table ────────────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[2, 4:])
    ax_tbl.set_facecolor("#0e1117")
    display = df[["package_id", "symbol", "status", "combined_pnl", "created_at"]].tail(8).copy()
    display.columns = ["ID", "Symbol", "Status", "PnL", "Time"]
    display["ID"] = display["ID"].str[:8]
    display["PnL"] = display["PnL"].apply(lambda x: f"${x:+.2f}")
    display["Time"] = display["Time"].dt.strftime("%m-%d %H:%M")
    table_data = [display.columns.tolist()] + display.values.tolist()
    table = ax_tbl.table(cellText=table_data, loc="center", cellLoc="center",
                         colWidths=[0.14, 0.30, 0.14, 0.18, 0.24])
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.6)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#30363d")
        if row == 0:
            cell.set_facecolor("#21262d")
            cell.set_text_props(color="#58a6ff", weight="bold")
        else:
            cell.set_facecolor("#161b22" if row % 2 == 0 else "#0e1117")
            cell.set_text_props(color="#c9d1d9")
    ax_tbl.set_title("Recent Trade Packages", color="#fafafa", fontsize=12, loc="left", pad=10)
    ax_tbl.axis("off")

    # ── Radar Chart (Agent Votes) ──────────────────────────────────────
    ax_radar = fig.add_subplot(gs[3, :3], projection="polar")
    ax_radar.set_facecolor("#0e1117")
    labels = ["Sentiment", "Technical", "Volatility", "OnChain", "Funding", "OrderFlow", "Macro", "News", "Reflection"]
    values = [0.62, 0.58, 0.70, 0.55, 0.45, 0.60, 0.52, 0.65, 0.57]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    values += values[:1]
    angles += angles[:1]
    ax_radar.plot(angles, values, color="#3b82f6", lw=2)
    ax_radar.fill(angles, values, color="#3b82f6", alpha=0.2)
    ax_radar.set_xticks(angles[:-1])
    ax_radar.set_xticklabels(labels, color="#9ca3af", size=8)
    ax_radar.set_ylim(0, 1)
    ax_radar.set_yticklabels([])
    ax_radar.set_title("Agent Vote Distribution", color="#fafafa", fontsize=12, pad=20)
    ax_radar.spines["polar"].set_color("#30363d")

    # ── Defense Swarm Panel ────────────────────────────────────────────
    ax_def = fig.add_subplot(gs[3, 3:])
    ax_def.set_facecolor("#161b22")
    rect = FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.02,rounding_size=0.1",
                          facecolor="#161b22", edgecolor="#30363d", transform=ax_def.transAxes)
    ax_def.add_patch(rect)
    ax_def.text(0.5, 0.88, "Defense Swarm Status", ha="center", va="center",
                fontsize=12, color="#fafafa", weight="bold", transform=ax_def.transAxes)

    def_status = {
        "status": "STANDBY",
        "bull_score": 0.00,
        "active_ex": "—",
        "events": 0,
        "rotations": 0,
        "splits": 0,
        "unresolved": 0,
        "last_action": "—",
    }
    rows = [
        ("Status", def_status["status"], "#f59e0b"),
        ("Bull Score", f"{def_status['bull_score']:.2f}", "#9ca3af"),
        ("Active Exchange", def_status["active_ex"], "#9ca3af"),
        ("Interference Events", str(def_status["events"]), "#ef4444"),
        ("Rotations Today", str(def_status["rotations"]), "#8b5cf6"),
    ]
    for idx, (label, val, color) in enumerate(rows):
        y = 0.65 - idx * 0.15
        ax_def.text(0.08, y, label + ":", ha="left", va="center", fontsize=9,
                    color="#9ca3af", transform=ax_def.transAxes)
        ax_def.text(0.92, y, val, ha="right", va="center", fontsize=10,
                    color=color, weight="bold", transform=ax_def.transAxes)
    ax_def.set_xlim(0, 1)
    ax_def.set_ylim(0, 1)
    ax_def.axis("off")

    # ── Watchlist ──────────────────────────────────────────────────────
    ax_wl = fig.add_subplot(gs[4, :])
    ax_wl.set_facecolor("#0e1117")
    watchlist = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
    n = len(watchlist)
    for i, sym in enumerate(watchlist):
        x = (i + 0.5) / n
        rect = FancyBboxPatch((x - 0.12, 0.35), 0.24, 0.35, boxstyle="round,pad=0.02,rounding_size=0.15",
                              facecolor="#161b22", edgecolor="#30363d", transform=ax_wl.transAxes)
        ax_wl.add_patch(rect)
        ax_wl.text(x, 0.68, sym, ha="center", va="center", fontsize=10,
                   color="#58a6ff", weight="bold", transform=ax_wl.transAxes)
        ax_wl.text(x, 0.45, "–", ha="center", va="center", fontsize=14,
                   color="#9ca3af", transform=ax_wl.transAxes)
    ax_wl.set_title("Watchlist", color="#fafafa", fontsize=12, loc="left", pad=10)
    ax_wl.set_xlim(0, 1)
    ax_wl.set_ylim(0, 1)
    ax_wl.axis("off")

    # ── Footer ─────────────────────────────────────────────────────────
    fig.text(0.5, 0.01, f"Last updated: {datetime.utcnow().strftime('%H:%M:%S UTC')}  •  Auto-refresh: 10s",
             ha="center", va="bottom", fontsize=9, color="#6e7681")

    plt.savefig("dashboard_preview.png", dpi=150, bbox_inches="tight",
                facecolor="#0e1117", edgecolor="none")
    plt.close()
    print("Saved dashboard_preview.png")


if __name__ == "__main__":
    asyncio.run(seed_data())
    generate_preview()
