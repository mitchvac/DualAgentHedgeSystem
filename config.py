"""
config.py
─────────────────────────────────────────────────────────────────────────────
Central configuration for the Dual-Agent Composite Hedge Trading System.
All secrets are loaded from environment variables / .env file.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load .env from the project root
load_dotenv(Path(__file__).parent / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Exchange Credential Blocks
# ─────────────────────────────────────────────────────────────────────────────

class ExchangeConfig(BaseSettings):
    """Credentials for a single exchange."""

    api_key: str = ""
    api_secret: str = ""
    api_passphrase: Optional[str] = None   # OKX, Kucoin, etc.
    testnet: bool = True                   # always paper-trade by default

    model_config = {"env_prefix": "", "extra": "ignore"}


# ─────────────────────────────────────────────────────────────────────────────
# Master System Settings
# ─────────────────────────────────────────────────────────────────────────────

class SystemConfig(BaseSettings):
    """
    Top-level runtime config.
    Every field can be overridden by the matching env-var (see .env.example).
    """

    # ── Mode ────────────────────────────────────────────────────────────────
    paper_trading: bool = Field(True, description="Dry-run mode; no real orders")
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    db_url: str = "sqlite+aiosqlite:///./data/trades.db"
    chroma_persist_dir: str = "./data/chroma"
    default_trading_user: str = Field("admin", description="Default user_id for background engine trades")

    # ── LLM ─────────────────────────────────────────────────────────────────
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", env="ANTHROPIC_API_KEY")
    grok_api_key: str = Field("", env="GROK_API_KEY")
    default_llm_model: str = "gpt-4o"           # swap to claude-3-5-sonnet, etc.
    llm_temperature: float = 0.1

    # ── Social data ─────────────────────────────────────────────────────────
    twitter_bearer_token: str = Field("", env="TWITTER_BEARER_TOKEN")
    lunarcrush_api_key: str = Field("", env="LUNARCRUSH_API_KEY")

    # ── On-chain data ────────────────────────────────────────────────────────
    glassnode_api_key: str = Field("", env="GLASSNODE_API_KEY")
    coinglass_api_key: str = Field("", env="COINGLASS_API_KEY")

    # ── Exchange defaults ─────────────────────────────────────────────────
    long_exchange_id: str = "bybit"             # Exchange for the Up-Agent leg
    short_exchange_id: str = "okx"              # Exchange for the Down-Agent leg
    # When same_exchange=True, both legs trade on long_exchange_id (hedge mode)
    same_exchange_hedge_mode: bool = False

    # Bybit credentials
    bybit_api_key: str = Field("", env="BYBIT_API_KEY")
    bybit_api_secret: str = Field("", env="BYBIT_API_SECRET")
    bybit_testnet: bool = Field(True, env="BYBIT_TESTNET")

    # OKX credentials
    okx_api_key: str = Field("", env="OKX_API_KEY")
    okx_api_secret: str = Field("", env="OKX_API_SECRET")
    okx_api_passphrase: str = Field("", env="OKX_API_PASSPHRASE")
    okx_testnet: bool = Field(True, env="OKX_TESTNET")

    # Binance credentials (optional 3rd exchange)
    binance_api_key: str = Field("", env="BINANCE_API_KEY")
    binance_api_secret: str = Field("", env="BINANCE_API_SECRET")
    binance_testnet: bool = Field(True, env="BINANCE_TESTNET")

    # ── Risk parameters ───────────────────────────────────────────────────
    max_risk_per_package_pct: float = 0.5       # % of account per composite trade
    max_daily_drawdown_pct: float = 3.0          # halt if daily loss > 3%
    default_leverage: int = 5
    max_leverage: int = 20
    stop_loss_pct: float = 2.0                   # per leg
    take_profit_pct: float = 4.0                 # per leg
    trailing_stop_pct: Optional[float] = 1.5

    # ── Position management ───────────────────────────────────────────────
    max_concurrent_packages: int = 6             # max open composite trades
    rebalance_interval_min: int = 15             # swarm re-eval interval (minutes)

    # ── Swarm thresholds ──────────────────────────────────────────────────
    min_consensus_score: float = 0.65           # 0-1; swarm must agree ≥65%
    min_volatility_percentile: float = 60.0     # IV must be in top 40%
    signal_refresh_seconds: int = 30

    # ── Funding / Arbitrage filters ───────────────────────────────────────
    funding_rate_threshold: float = 0.03         # ±% threshold for perp funding filter

    # ── Coins to watch ────────────────────────────────────────────────────
    watchlist: List[str] = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]

    # ── Defense Swarm ─────────────────────────────────────────────────────
    # Activate the 15-agent anti-bot defense layer during bull runs
    defense_enabled: bool = Field(True, description="Enable anti-bot Defense Swarm")
    defense_bull_run_threshold: float = Field(
        0.70,
        description="bull_score above this activates the Defense Swarm (0-1)",
    )
    defense_max_retries: int = Field(
        5,
        description="Max order retry attempts before rotating exchange",
    )
    defense_base_backoff_s: float = Field(
        0.5,
        description="Base seconds for exponential backoff (doubles each attempt)",
    )
    defense_stealth_splits: bool = Field(
        True,
        description="Split orders into randomised micro-lots when interference detected",
    )
    defense_ob_scan_interval_s: float = Field(
        5.0,
        description="Background order-book scan interval in seconds",
    )
    # Circuit-breaker: fire if cumulative severity > this within 120s window
    defense_circuit_severity_threshold: float = Field(
        3.0,
        description="Cumulative interference severity that triggers circuit break",
    )
    # Additional API key sets for rotation (exchange_id:api_key:api_secret[:passphrase])
    # Example: "bybit:KEY2:SECRET2,okx:KEY2:SECRET2:PASS2"
    defense_backup_api_keys: str = Field(
        "",
        env="DEFENSE_BACKUP_API_KEYS",
        description="Comma-separated backup API key triples for exchange rotation",
    )

    # ── Dashboard ────────────────────────────────────────────────────────
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501


    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v.upper()

    def get_exchange_kwargs(self, exchange_id: str) -> Dict:
        """
        Returns the ccxt constructor kwargs for the given exchange_id.
        Supports bybit, okx, binance.
        """
        ex = exchange_id.lower()
        if ex == "bybit":
            return {
                "apiKey": self.bybit_api_key,
                "secret": self.bybit_api_secret,
                "options": {"defaultType": "swap"},
                "sandbox": self.bybit_testnet,
            }
        elif ex == "okx":
            return {
                "apiKey": self.okx_api_key,
                "secret": self.okx_api_secret,
                "password": self.okx_api_passphrase,
                "options": {"defaultType": "swap"},
                "sandbox": self.okx_testnet,
            }
        elif ex == "binance":
            return {
                "apiKey": self.binance_api_key,
                "secret": self.binance_api_secret,
                "options": {"defaultType": "future"},
                "sandbox": self.binance_testnet,
            }
        else:
            raise ValueError(f"Unknown exchange_id: {exchange_id}")


# ── Singleton ─────────────────────────────────────────────────────────────────
settings = SystemConfig()

# Ensure data directory exists
settings.data_dir.mkdir(parents=True, exist_ok=True)
