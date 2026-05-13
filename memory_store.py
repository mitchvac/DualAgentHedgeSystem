"""
memory_store.py
─────────────────────────────────────────────────────────────────────────────
Persistent memory for the trading system.
Uses:
  • SQLite (via SQLAlchemy async) — structured trade log
  • ChromaDB (local vector store) — semantic memory for reflection agents
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, select, Boolean, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings
from models import TradeMemory, TradePackage


# ─────────────────────────────────────────────────────────────────────────────
# SQLAlchemy ORM
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trades"

    package_id   = Column(String, primary_key=True)
    user_id      = Column(String, index=True, default="system")
    symbol       = Column(String, index=True)
    status       = Column(String)
    combined_pnl = Column(Float, default=0.0)
    risk_budget  = Column(Float, default=0.0)
    close_reason = Column(String, default="")
    consensus_json = Column(Text, default="{}")
    created_at   = Column(DateTime, default=datetime.utcnow)
    closed_at    = Column(DateTime, nullable=True)
    notes        = Column(Text, default="[]")
    # Leg detail columns (added v2.2)
    long_exchange  = Column(String, nullable=True)
    short_exchange = Column(String, nullable=True)
    long_pnl       = Column(Float, default=0.0)
    short_pnl      = Column(Float, default=0.0)
    # Leg size & entry columns (added v2.3)
    long_qty       = Column(Float, nullable=True)
    short_qty      = Column(Float, nullable=True)
    long_notional  = Column(Float, nullable=True)
    short_notional = Column(Float, nullable=True)
    long_entry     = Column(Float, nullable=True)
    short_entry    = Column(Float, nullable=True)
    long_leverage  = Column(Integer, nullable=True)
    short_leverage = Column(Integer, nullable=True)
    funding_paid   = Column(Float, default=0.0)


class EquitySnapshotRecord(Base):
    __tablename__ = "equity_history"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    user_id   = Column(String, index=True, default="system")
    equity    = Column(Float, default=0.0)
    pnl_today = Column(Float, default=0.0)
    drawdown_pct = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)


class AgentVoteRecord(Base):
    __tablename__ = "agent_votes"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    user_id   = Column(String, index=True, default="system")
    agent_id  = Column(String, index=True)
    role      = Column(String)
    symbol    = Column(String, index=True)
    direction = Column(String)   # bull / bear / neutral
    confidence = Column(Float, default=0.0)
    was_correct = Column(Boolean, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class ArbOpportunityRecord(Base):
    __tablename__ = "arb_opportunities"

    id           = Column(String, primary_key=True)
    user_id      = Column(String, index=True, default="system")
    strategy     = Column(String)
    symbol       = Column(String, index=True)
    buy_exchange = Column(String)
    sell_exchange = Column(String)
    buy_price    = Column(Float, default=0.0)
    sell_price   = Column(Float, default=0.0)
    spread_pct   = Column(Float, default=0.0)
    fees_pct     = Column(Float, default=0.0)
    net_profit_pct = Column(Float, default=0.0)
    size_usdt    = Column(Float, default=0.0)
    net_profit_usdt = Column(Float, default=0.0)
    funding_rate = Column(Float, nullable=True)
    withdrawal_fee = Column(Float, nullable=True)
    network_fee_usdt = Column(Float, nullable=True)
    deposit_fee = Column(Float, nullable=True)
    withdrawal_time_min = Column(Integer, nullable=True)
    deposit_time_min = Column(Integer, nullable=True)
    min_withdraw_amount = Column(Float, nullable=True)
    withdraw_enabled = Column(Boolean, default=True)
    deposit_enabled = Column(Boolean, default=True)
    net_gain_coins = Column(Float, nullable=True)
    net_gain_usdt = Column(Float, nullable=True)
    executed     = Column(Boolean, default=False)
    timestamp    = Column(DateTime, default=datetime.utcnow)


class UserRecord(Base):
    __tablename__ = "users"

    username     = Column(String, primary_key=True)
    password_hash = Column(String, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class OAuthAccountRecord(Base):
    __tablename__ = "oauth_accounts"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    provider        = Column(String, nullable=False)
    provider_user_id = Column(String, nullable=False)
    username        = Column(String, nullable=False)
    email           = Column(String, nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Unique constraint on provider + provider_user_id
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class PaymentRecord(Base):
    __tablename__ = "payments"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash      = Column(String, unique=True, nullable=False)
    username     = Column(String, nullable=False, index=True)
    amount       = Column(Float, nullable=False)
    currency     = Column(String, nullable=False)
    months       = Column(Integer, default=1)
    tier         = Column(String, default="monthly")
    status       = Column(String, default="confirmed")
    created_at   = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ({'sqlite_autoincrement': True},)


class SubscriptionRecord(Base):
    __tablename__ = "subscriptions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    username     = Column(String, unique=True, nullable=False)
    tier         = Column(String, default="free")
    active       = Column(Boolean, default=True)
    started_at   = Column(DateTime, default=datetime.utcnow)
    expires_at   = Column(DateTime, nullable=True)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'sqlite_autoincrement': True},)


class SystemSettingRecord(Base):
    __tablename__ = "system_settings"

    key          = Column(String, primary_key=True)
    user_id      = Column(String, index=True, default="system")
    value        = Column(Text, nullable=False)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomExchangeRecord(Base):
    __tablename__ = "custom_exchanges"

    exchange_id  = Column(String, primary_key=True)
    user_id      = Column(String, index=True, default="system")
    api_key      = Column(String, default="")
    api_secret   = Column(String, default="")
    api_passphrase = Column(String, default="")
    testnet      = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Memory Store class
# ─────────────────────────────────────────────────────────────────────────────

class MemoryStore:
    """
    Dual-layer persistence:
    • SQLite  → structured trade records (queryable)
    • ChromaDB → semantic embeddings for the Reflection agents
    """

    def __init__(self) -> None:
        # SQL layer
        self.engine = create_async_engine(settings.db_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        # Vector layer
        self._chroma_client: Optional[chromadb.Client] = None
        self._collection = None

    async def _migrate_trades_table(self) -> None:
        """Add missing columns to trades table (SQLite ALTER TABLE)."""
        def _add_columns(sync_conn):
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(sync_conn)
            cols = {c["name"] for c in inspector.get_columns("trades")}
            new_cols = [
                ("long_exchange", "VARCHAR"),
                ("short_exchange", "VARCHAR"),
                ("long_pnl", "FLOAT"),
                ("short_pnl", "FLOAT"),
                ("long_qty", "FLOAT"),
                ("short_qty", "FLOAT"),
                ("long_notional", "FLOAT"),
                ("short_notional", "FLOAT"),
                ("long_entry", "FLOAT"),
                ("short_entry", "FLOAT"),
                ("long_leverage", "INTEGER"),
                ("short_leverage", "INTEGER"),
                ("funding_paid", "FLOAT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in cols:
                    sync_conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"[Memory] Migrated trades table: added {col_name}")
        async with self.engine.begin() as conn:
            await conn.run_sync(_add_columns)

    async def _migrate_arb_opportunities_table(self) -> None:
        """Add missing columns to arb_opportunities table."""
        def _add_columns(sync_conn):
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(sync_conn)
            cols = {c["name"] for c in inspector.get_columns("arb_opportunities")}
            new_cols = [
                ("withdrawal_fee", "FLOAT"),
                ("network_fee_usdt", "FLOAT"),
                ("deposit_fee", "FLOAT"),
                ("withdrawal_time_min", "INTEGER"),
                ("deposit_time_min", "INTEGER"),
                ("min_withdraw_amount", "FLOAT"),
                ("withdraw_enabled", "BOOLEAN"),
                ("deposit_enabled", "BOOLEAN"),
                ("net_gain_coins", "FLOAT"),
                ("net_gain_usdt", "FLOAT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in cols:
                    sync_conn.execute(text(f"ALTER TABLE arb_opportunities ADD COLUMN {col_name} {col_type}"))
                    logger.info(f"[Memory] Migrated arb_opportunities table: added {col_name}")
        async with self.engine.begin() as conn:
            await conn.run_sync(_add_columns)

    async def _migrate_user_id_columns(self) -> None:
        """Add user_id columns to all tables for multi-tenant RLS."""
        def _add_columns(sync_conn):
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(sync_conn)
            tables = [
                "trades", "equity_history", "agent_votes",
                "arb_opportunities", "system_settings", "custom_exchanges"
            ]
            for table in tables:
                cols = {c["name"] for c in inspector.get_columns(table)}
                if "user_id" not in cols:
                    sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR DEFAULT 'system'"))
                    logger.info(f"[Memory] Migrated {table}: added user_id")
                # Also create index for performance
                idx_name = f"idx_{table}_user_id"
                existing_idx = {i['name'] for i in inspector.get_indexes(table)}
                if idx_name not in existing_idx:
                    try:
                        sync_conn.execute(text(f"CREATE INDEX {idx_name} ON {table}(user_id)"))
                        logger.info(f"[Memory] Created index {idx_name}")
                    except Exception:
                        pass  # Index may already exist with different name
        async with self.engine.begin() as conn:
            await conn.run_sync(_add_columns)

    async def initialize(self) -> None:
        """Create tables and connect to ChromaDB."""
        async with self.engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))
        # Migrate existing tables: add new columns if missing
        await self._migrate_trades_table()
        await self._migrate_arb_opportunities_table()
        await self._migrate_user_id_columns()
        logger.info("[Memory] SQLite tables ready")

        self._chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._chroma_client.get_or_create_collection(
            name="trade_memory",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"[Memory] ChromaDB collection ready ({self._collection.count()} records)")

    # ── SQL helpers ──────────────────────────────────────────────────────────

    async def save_package(self, pkg: TradePackage, user_id: str = "system") -> None:
        """Upsert a TradePackage into the SQLite trades table."""
        async with self.async_session() as session:
            existing = await session.get(TradeRecord, pkg.package_id)
            if existing:
                existing.status = pkg.status.value
                existing.combined_pnl = pkg.combined_pnl
                existing.close_reason = pkg.close_reason
                existing.closed_at = pkg.closed_at
                existing.notes = json.dumps(pkg.notes)
                existing.user_id = user_id
                if pkg.long_leg:
                    existing.long_exchange = pkg.long_leg.exchange_id
                    existing.long_pnl = pkg.long_leg.unrealized_pnl + pkg.long_leg.realized_pnl
                    existing.long_qty = pkg.long_leg.quantity
                    existing.long_notional = pkg.long_leg.notional_usdt
                    existing.long_entry = pkg.long_leg.entry_price
                    existing.long_leverage = pkg.long_leg.leverage
                if pkg.short_leg:
                    existing.short_exchange = pkg.short_leg.exchange_id
                    existing.short_pnl = pkg.short_leg.unrealized_pnl + pkg.short_leg.realized_pnl
                    existing.short_qty = pkg.short_leg.quantity
                    existing.short_notional = pkg.short_leg.notional_usdt
                    existing.short_entry = pkg.short_leg.entry_price
                    existing.short_leverage = pkg.short_leg.leverage
                existing.funding_paid = (
                    (pkg.long_leg.funding_paid if pkg.long_leg else 0.0)
                    + (pkg.short_leg.funding_paid if pkg.short_leg else 0.0)
                )
            else:
                record = TradeRecord(
                    package_id=pkg.package_id,
                    user_id=user_id,
                    symbol=pkg.symbol,
                    status=pkg.status.value,
                    combined_pnl=pkg.combined_pnl,
                    risk_budget=pkg.risk_budget_usdt,
                    close_reason=pkg.close_reason,
                    consensus_json=pkg.consensus.model_dump_json() if pkg.consensus else "{}",
                    created_at=pkg.created_at,
                    closed_at=pkg.closed_at,
                    notes=json.dumps(pkg.notes),
                    long_exchange=pkg.long_leg.exchange_id if pkg.long_leg else None,
                    short_exchange=pkg.short_leg.exchange_id if pkg.short_leg else None,
                    long_pnl=(pkg.long_leg.unrealized_pnl + pkg.long_leg.realized_pnl) if pkg.long_leg else 0.0,
                    short_pnl=(pkg.short_leg.unrealized_pnl + pkg.short_leg.realized_pnl) if pkg.short_leg else 0.0,
                    long_qty=pkg.long_leg.quantity if pkg.long_leg else None,
                    short_qty=pkg.short_leg.quantity if pkg.short_leg else None,
                    long_notional=pkg.long_leg.notional_usdt if pkg.long_leg else None,
                    short_notional=pkg.short_leg.notional_usdt if pkg.short_leg else None,
                    long_entry=pkg.long_leg.entry_price if pkg.long_leg else None,
                    short_entry=pkg.short_leg.entry_price if pkg.short_leg else None,
                    long_leverage=pkg.long_leg.leverage if pkg.long_leg else None,
                    short_leverage=pkg.short_leg.leverage if pkg.short_leg else None,
                    funding_paid=(pkg.long_leg.funding_paid if pkg.long_leg else 0.0) + (pkg.short_leg.funding_paid if pkg.short_leg else 0.0),
                )
                session.add(record)
            await session.commit()

    async def get_recent_packages(self, user_id: str = "system", limit: int = 50) -> List[TradeRecord]:
        """Return the most recent trade records for a specific user."""
        async with self.async_session() as session:
            result = await session.execute(
                select(TradeRecord)
                .where(TradeRecord.user_id == user_id)
                .order_by(TradeRecord.created_at.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def get_daily_pnl(self, user_id: str = "system") -> float:
        """Sum of combined_pnl for today's closed trades for a specific user."""
        from sqlalchemy import func, cast, Date
        today = datetime.utcnow().date()
        async with self.async_session() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(TradeRecord.combined_pnl), 0.0))
                .where(TradeRecord.user_id == user_id)
                .where(TradeRecord.closed_at >= datetime(today.year, today.month, today.day))
            )
            return float(result.scalar() or 0.0)

    # ── ChromaDB helpers ─────────────────────────────────────────────────────

    async def store_trade_memory(self, pkg: TradePackage, lessons: str = "") -> None:
        """
        Store a closed trade as a semantic memory in ChromaDB.
        Document = human-readable summary; embedding captures the market state.
        """
        if not self._collection:
            return

        consensus = pkg.consensus
        doc = (
            f"Symbol: {pkg.symbol}. "
            f"Bull score: {consensus.bull_score:.2f}. "
            f"Bear score: {consensus.bear_score:.2f}. "
            f"Volatility percentile: {consensus.volatility_percentile:.1f}. "
            f"Outcome PnL: {pkg.combined_pnl:.2f} USDT. "
            f"Close reason: {pkg.close_reason}. "
            f"Lessons: {lessons}"
        )

        self._collection.add(
            documents=[doc],
            ids=[pkg.package_id],
            metadatas=[{
                "symbol": pkg.symbol,
                "pnl": pkg.combined_pnl,
                "close_reason": pkg.close_reason,
                "timestamp": datetime.utcnow().isoformat(),
            }],
        )
        logger.info(f"[Memory] Stored trade memory for package {pkg.package_id}")

    async def query_similar_outcome(
        self,
        symbol: str,
        n_results: int = 5,
    ) -> float:
        """
        Query ChromaDB for similar past trades and return
        a 0-1 bullish outlook score based on historical outcomes.
        """
        if not self._collection or self._collection.count() == 0:
            return 0.5   # no data → neutral

        # Build a query string representing the current market context
        try:
            snap = None
            try:
                from exchange_client import fetch_market_snapshot
                snap = await fetch_market_snapshot(settings.long_exchange_id, symbol)
            except Exception:
                pass

            query = f"Symbol: {symbol}."
            if snap:
                query += (
                    f" Price change 24h: {snap.change_24h_pct:.2f}%. "
                    f" Funding: {snap.funding_rate:.5f}."
                )

            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count()),
            )
            pnls = [m["pnl"] for m in results["metadatas"][0]]
            if not pnls:
                return 0.5
            positive = sum(1 for p in pnls if p > 0)
            return positive / len(pnls)
        except Exception as e:
            logger.debug(f"[Memory] query_similar_outcome error: {e}")
            return 0.5

    async def save_arb_opportunity(self, opp, user_id: str = "system") -> None:
        """Persist an arbitrage opportunity to SQLite."""
        from arbitrage_module import ArbOpportunity
        if not isinstance(opp, ArbOpportunity):
            return
        async with self.async_session() as session:
            record = ArbOpportunityRecord(
                id=f"{opp.symbol}-{opp.strategy}-{opp.timestamp.timestamp()}",
                user_id=user_id,
                strategy=opp.strategy,
                symbol=opp.symbol,
                buy_exchange=opp.buy_exchange,
                sell_exchange=opp.sell_exchange,
                buy_price=opp.buy_price,
                sell_price=opp.sell_price,
                spread_pct=opp.spread_pct,
                fees_pct=opp.fees_pct,
                net_profit_pct=opp.net_profit_pct,
                size_usdt=opp.size_usdt,
                net_profit_usdt=opp.net_profit_usdt,
                funding_rate=opp.funding_rate,
                withdrawal_fee=opp.withdrawal_fee,
                network_fee_usdt=opp.network_fee_usdt,
                deposit_fee=opp.deposit_fee,
                withdrawal_time_min=opp.withdrawal_time_min,
                deposit_time_min=opp.deposit_time_min,
                min_withdraw_amount=opp.min_withdraw_amount,
                withdraw_enabled=opp.withdraw_enabled,
                deposit_enabled=opp.deposit_enabled,
                net_gain_coins=opp.net_gain_coins,
                net_gain_usdt=opp.net_gain_usdt,
                executed=opp.executed,
                timestamp=opp.timestamp,
            )
            session.merge(record)
            await session.commit()

    async def get_recent_arb_opportunities(self, user_id: str = "system", limit: int = 100, since: Optional[datetime] = None) -> List[ArbOpportunityRecord]:
        """Return recent arbitrage opportunities for a specific user, optionally filtered by date."""
        async with self.async_session() as session:
            query = select(ArbOpportunityRecord).where(ArbOpportunityRecord.user_id == user_id).order_by(ArbOpportunityRecord.timestamp.desc())
            if since is not None:
                query = query.where(ArbOpportunityRecord.timestamp >= since)
            query = query.limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    # ── User management ───────────────────────────────────────────────────────

    async def create_user(self, username: str, password_hash: str) -> bool:
        """Create a new user. Returns False if username already exists."""
        async with self.async_session() as session:
            existing = await session.get(UserRecord, username)
            if existing:
                return False
            session.add(UserRecord(username=username, password_hash=password_hash))
            await session.commit()
            return True

    async def get_user(self, username: str) -> Optional[UserRecord]:
        """Fetch a user by username."""
        async with self.async_session() as session:
            return await session.get(UserRecord, username)

    async def create_oauth_user(self, provider: str, provider_user_id: str, username: str, email: Optional[str] = None) -> str:
        """Create or link an OAuth user. Returns username."""
        async with self.async_session() as session:
            # Check if this OAuth account already exists
            result = await session.execute(
                select(OAuthAccountRecord)
                .where(OAuthAccountRecord.provider == provider)
                .where(OAuthAccountRecord.provider_user_id == provider_user_id)
            )
            existing_oauth = result.scalar_one_or_none()
            if existing_oauth:
                return existing_oauth.username

            # Check if username is taken
            existing_user = await session.get(UserRecord, username)
            if existing_user:
                # Generate a unique username
                base = username
                counter = 1
                while existing_user:
                    username = f"{base}_{counter}"
                    existing_user = await session.get(UserRecord, username)
                    counter += 1

            # Create user without password
            session.add(UserRecord(username=username, password_hash=None))
            session.add(OAuthAccountRecord(
                provider=provider,
                provider_user_id=provider_user_id,
                username=username,
                email=email,
            ))
            await session.commit()
            return username

    # ── Payments & Subscriptions ──────────────────────────────────────────────

    async def get_payment_by_tx(self, tx_hash: str) -> Optional[PaymentRecord]:
        async with self.async_session() as session:
            result = await session.execute(
                select(PaymentRecord).where(PaymentRecord.tx_hash == tx_hash)
            )
            return result.scalar_one_or_none()

    async def save_payment(self, tx_hash: str, username: str, amount: float, currency: str, months: int = 1, tier: str = "monthly") -> None:
        async with self.async_session() as session:
            session.add(PaymentRecord(
                tx_hash=tx_hash,
                username=username,
                amount=amount,
                currency=currency,
                months=months,
                tier=tier,
            ))
            await session.commit()

    async def get_subscription(self, username: str) -> Optional[SubscriptionRecord]:
        async with self.async_session() as session:
            result = await session.execute(
                select(SubscriptionRecord).where(SubscriptionRecord.username == username)
            )
            return result.scalar_one_or_none()

    async def activate_subscription(self, username: str, months: int = 1, tier: str = "monthly") -> None:
        async with self.async_session() as session:
            sub = await session.get(SubscriptionRecord, username)
            now = datetime.utcnow()
            if sub:
                if sub.expires_at and sub.expires_at > now:
                    sub.expires_at = sub.expires_at + timedelta(days=30 * months)
                else:
                    sub.expires_at = now + timedelta(days=30 * months)
                    sub.started_at = now
                sub.tier = tier
                sub.active = True
            else:
                session.add(SubscriptionRecord(
                    username=username,
                    tier=tier,
                    active=True,
                    started_at=now,
                    expires_at=now + timedelta(days=30 * months),
                ))
            await session.commit()

    async def check_subscription_active(self, username: str) -> bool:
        sub = await self.get_subscription(username)
        if not sub:
            return False
        if not sub.active:
            return False
        if sub.expires_at and sub.expires_at < datetime.utcnow():
            return False
        return True

    async def get_all_subscriptions(self) -> list[SubscriptionRecord]:
        async with self.async_session() as session:
            result = await session.execute(select(SubscriptionRecord))
            return result.scalars().all()

    async def get_all_payments(self) -> list[PaymentRecord]:
        async with self.async_session() as session:
            result = await session.execute(
                select(PaymentRecord).order_by(PaymentRecord.created_at.desc())
            )
            return result.scalars().all()

    def _setting_key(self, user_id: str, key: str) -> str:
        """Namespace a setting key with user_id to enforce isolation."""
        return f"{user_id}:{key}"

    async def set_system_setting(self, key: str, value: str, user_id: str = "system") -> None:
        """Upsert a system setting scoped to a user."""
        namespaced_key = self._setting_key(user_id, key)
        async with self.async_session() as session:
            record = await session.get(SystemSettingRecord, namespaced_key)
            if record:
                record.value = value
                record.updated_at = datetime.utcnow()
                record.user_id = user_id
            else:
                session.add(SystemSettingRecord(key=namespaced_key, user_id=user_id, value=value))
            await session.commit()

    async def get_system_setting(self, key: str, user_id: str = "system") -> Optional[str]:
        """Fetch a single system setting value scoped to a user."""
        namespaced_key = self._setting_key(user_id, key)
        async with self.async_session() as session:
            record = await session.get(SystemSettingRecord, namespaced_key)
            return record.value if record else None

    async def get_all_system_settings(self, user_id: str = "system") -> dict:
        """Fetch all system settings as a dict scoped to a user."""
        async with self.async_session() as session:
            result = await session.execute(
                select(SystemSettingRecord).where(SystemSettingRecord.user_id == user_id)
            )
            records = result.scalars().all()
            # Strip user_id prefix from keys for API response
            return {r.key.split(":", 1)[1] if ":" in r.key else r.key: r.value for r in records}

    # ── Custom exchanges ─────────────────────────────────────────────────────

    def _exchange_id(self, user_id: str, exchange_id: str) -> str:
        """Namespace an exchange_id with user_id to enforce isolation."""
        return f"{user_id}:{exchange_id}"

    async def add_custom_exchange(self, exchange_id: str, api_key: str = "", api_secret: str = "", api_passphrase: str = "", testnet: bool = True, user_id: str = "system") -> bool:
        """Add a new custom exchange scoped to a user. Returns False if already exists."""
        namespaced_id = self._exchange_id(user_id, exchange_id)
        async with self.async_session() as session:
            existing = await session.get(CustomExchangeRecord, namespaced_id)
            if existing:
                return False
            session.add(CustomExchangeRecord(
                exchange_id=namespaced_id,
                user_id=user_id,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
                testnet=testnet,
            ))
            await session.commit()
            return True

    async def get_custom_exchanges(self, user_id: str = "system") -> List[CustomExchangeRecord]:
        """Fetch all custom exchanges scoped to a user."""
        async with self.async_session() as session:
            result = await session.execute(
                select(CustomExchangeRecord).where(CustomExchangeRecord.user_id == user_id)
            )
            return result.scalars().all()

    async def delete_custom_exchange(self, exchange_id: str, user_id: str = "system") -> bool:
        """Delete a custom exchange scoped to a user."""
        namespaced_id = self._exchange_id(user_id, exchange_id)
        async with self.async_session() as session:
            record = await session.get(CustomExchangeRecord, namespaced_id)
            if not record:
                return False
            await session.delete(record)
            await session.commit()
            return True

    # ── Equity history ───────────────────────────────────────────────────────

    async def save_equity_snapshot(self, equity: float, pnl_today: float = 0.0, drawdown_pct: float = 0.0, user_id: str = "system") -> None:
        """Store an equity snapshot scoped to a user. Keeps last 90 days only."""
        async with self.async_session() as session:
            session.add(EquitySnapshotRecord(
                user_id=user_id,
                equity=equity,
                pnl_today=pnl_today,
                drawdown_pct=drawdown_pct,
            ))
            # Prune old records (> 90 days) for this user
            cutoff = datetime.utcnow() - timedelta(days=90)
            await session.execute(
                EquitySnapshotRecord.__table__.delete().where(
                    EquitySnapshotRecord.user_id == user_id,
                    EquitySnapshotRecord.timestamp < cutoff
                )
            )
            await session.commit()

    async def get_equity_history(self, days: int = 30, user_id: str = "system") -> List[EquitySnapshotRecord]:
        """Return equity snapshots for the last N days scoped to a user."""
        async with self.async_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            result = await session.execute(
                select(EquitySnapshotRecord)
                .where(EquitySnapshotRecord.user_id == user_id)
                .where(EquitySnapshotRecord.timestamp >= since)
                .order_by(EquitySnapshotRecord.timestamp.asc())
            )
            return result.scalars().all()

    # ── Agent vote accuracy ─────────────────────────────────────────────────

    async def save_agent_vote(self, agent_id: str, role: str, symbol: str, direction: str, confidence: float, user_id: str = "system") -> None:
        async with self.async_session() as session:
            session.add(AgentVoteRecord(
                user_id=user_id,
                agent_id=agent_id,
                role=role,
                symbol=symbol,
                direction=direction,
                confidence=confidence,
            ))
            await session.commit()

    async def get_agent_accuracy(self, days: int = 30, user_id: str = "system") -> List[dict]:
        """Return accuracy stats per agent role scoped to a user."""
        from sqlalchemy import func
        async with self.async_session() as session:
            since = datetime.utcnow() - timedelta(days=days)
            result = await session.execute(
                select(
                    AgentVoteRecord.role,
                    func.count(AgentVoteRecord.id).label("total_votes"),
                    func.sum(func.cast(AgentVoteRecord.was_correct, Integer)).label("correct_votes"),
                    func.avg(AgentVoteRecord.confidence).label("avg_confidence"),
                )
                .where(AgentVoteRecord.user_id == user_id)
                .where(AgentVoteRecord.timestamp >= since)
                .where(AgentVoteRecord.was_correct.isnot(None))
                .group_by(AgentVoteRecord.role)
                .order_by(func.sum(func.cast(AgentVoteRecord.was_correct, Integer)).desc())
            )
            rows = result.all()
            return [
                {
                    "role": row.role,
                    "total_votes": row.total_votes,
                    "correct_votes": row.correct_votes or 0,
                    "accuracy_pct": round((row.correct_votes or 0) / max(row.total_votes, 1) * 100, 1),
                    "avg_confidence": round(row.avg_confidence or 0, 2),
                }
                for row in rows
            ]

    async def close(self) -> None:
        await self.engine.dispose()
        logger.info("[Memory] Database connections closed")


# Singleton
memory_store = MemoryStore()
