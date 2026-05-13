"""
crypto_payments.py
─────────────────────────────────────────────────────────────────────────────
XRP Ledger payment processing for SaaS subscriptions.

Flow:
  1. User gets a payment address (master wallet + unique destination tag)
  2. User sends XRP or RLUSD to that address
  3. We poll the XRP Ledger for incoming payments
  4. When matched → activate subscription
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from loguru import logger
import xrpl
from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.models.requests import AccountTx
from xrpl.utils import xrp_to_drops, drops_to_xrp

from config import settings


# ═══════════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════════

# Your business XRP wallet (the one customers pay TO)
MASTER_XRP_ADDRESS = "rN7n7otQDd6FczFgLdlqtyMVrn3HMfHgFj"  # Replace with yours
# Secret key for reading tx only (never expose in frontend)
# Leave empty if only monitoring (read-only)
MASTER_XRP_SECRET = ""

# XRP Ledger node
XRPL_NODE = "https://s1.ripple.com:51234/"

# Pricing in XRP
SUBSCRIPTION_PRICE_XRP = 25.0   # 25 XRP per month
SUBSCRIPTION_PRICE_RLUSD = 25.0 # 25 RLUSD per month

# RLUSD issuer on XRP Ledger
RLUSD_CURRENCY = "RLUSD"
RLUSD_ISSUER = "rsA2LpGwyNX15r1EfJzrF9nS4z7cMP9bXW"  # Mainnet issuer


# ═══════════════════════════════════════════════════════════════════════════════
# Client
# ═══════════════════════════════════════════════════════════════════════════════

_xrpl_client: Optional[AsyncJsonRpcClient] = None


def get_xrpl_client() -> AsyncJsonRpcClient:
    global _xrpl_client
    if _xrpl_client is None:
        _xrpl_client = AsyncJsonRpcClient(XRPL_NODE)
    return _xrpl_client


# ═══════════════════════════════════════════════════════════════════════════════
# Payment Monitoring
# ═══════════════════════════════════════════════════════════════════════════════

async def check_incoming_payments(last_checked_ledger: int = 0) -> list[Dict[str, Any]]:
    """Poll XRP Ledger for incoming payments to MASTER_XRP_ADDRESS."""
    client = get_xrpl_client()
    try:
        req = AccountTx(
            account=MASTER_XRP_ADDRESS,
            ledger_index_min=-1,
            ledger_index_max=-1,
            forward=True,
        )
        resp = await client.request(req)
        transactions = resp.result.get("transactions", [])

        payments = []
        for tx_wrapper in transactions:
            tx = tx_wrapper.get("tx", {})
            meta = tx_wrapper.get("meta", {})

            if tx.get("TransactionType") != "Payment":
                continue
            if tx.get("Destination") != MASTER_XRP_ADDRESS:
                continue

            amount = tx.get("Amount")
            memos = tx.get("Memos", [])
            memo_data = ""
            for memo in memos:
                memo_hex = memo.get("Memo", {}).get("MemoData", "")
                if memo_hex:
                    try:
                        memo_data = bytes.fromhex(memo_hex).decode("utf-8")
                    except Exception:
                        pass

            delivered = meta.get("delivered_amount") or amount

            # Parse amount
            if isinstance(delivered, str):
                # XRP in drops
                xrp_amount = drops_to_xrp(delivered)
                currency = "XRP"
                issuer = ""
            elif isinstance(delivered, dict):
                # IOU (RLUSD, etc.)
                xrp_amount = float(delivered.get("value", 0))
                currency = delivered.get("currency", "")
                issuer = delivered.get("issuer", "")
            else:
                continue

            payments.append({
                "tx_hash": tx.get("hash"),
                "from": tx.get("Account"),
                "amount": xrp_amount,
                "currency": currency,
                "issuer": issuer,
                "memo": memo_data,
                "ledger_index": tx_wrapper.get("ledger_index"),
                "date": tx.get("date"),
            })

        return payments
    except Exception as e:
        logger.error(f"[CryptoPayments] Error checking payments: {e}")
        return []


async def verify_payment(tx_hash: str) -> Optional[Dict[str, Any]]:
    """Verify a specific transaction exists and is validated."""
    client = get_xrpl_client()
    try:
        from xrpl.models.requests import Tx
        req = Tx(transaction=tx_hash)
        resp = await client.request(req)
        result = resp.result

        if result.get("validated") and result.get("Destination") == MASTER_XRP_ADDRESS:
            return result
        return None
    except Exception as e:
        logger.error(f"[CryptoPayments] Error verifying tx {tx_hash}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Subscription Logic
# ═══════════════════════════════════════════════════════════════════════════════

async def process_pending_payments():
    """Background task: check for new payments and activate subscriptions."""
    from memory_store import memory_store
    await memory_store.initialize()

    payments = await check_incoming_payments()

    for p in payments:
        # Skip if already processed
        existing = await memory_store.get_payment_by_tx(p["tx_hash"])
        if existing:
            continue

        # Determine tier from amount
        tier = "basic"
        months = 1

        if p["currency"] == "XRP":
            if p["amount"] >= SUBSCRIPTION_PRICE_XRP * 12:
                months = 12
                tier = "annual"
            elif p["amount"] >= SUBSCRIPTION_PRICE_XRP * 3:
                months = 3
                tier = "quarterly"
            elif p["amount"] >= SUBSCRIPTION_PRICE_XRP:
                months = 1
                tier = "monthly"
            else:
                continue  # Below minimum

        elif p["currency"] == RLUSD_CURRENCY and p["issuer"] == RLUSD_ISSUER:
            if p["amount"] >= SUBSCRIPTION_PRICE_RLUSD:
                months = 1
                tier = "monthly"
            else:
                continue
        else:
            continue

        # Extract username from memo
        username = p["memo"].strip() if p["memo"] else None
        if not username:
            logger.warning(f"[CryptoPayments] Payment {p['tx_hash']} has no memo/username")
            continue

        # Save payment
        await memory_store.save_payment(
            tx_hash=p["tx_hash"],
            username=username,
            amount=p["amount"],
            currency=p["currency"],
            months=months,
            tier=tier,
        )

        # Activate/extend subscription
        await memory_store.activate_subscription(username, months, tier)
        logger.info(f"[CryptoPayments] Activated {months}mo {tier} subscription for {username} via {p['tx_hash']}")


async def subscription_monitor_loop(interval_seconds: int = 60):
    """Run forever in background to check for new crypto payments."""
    logger.info("[CryptoPayments] Subscription monitor started")
    while True:
        try:
            await process_pending_payments()
        except Exception as e:
            logger.error(f"[CryptoPayments] Monitor error: {e}")
        await asyncio.sleep(interval_seconds)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def format_payment_instructions(username: str) -> Dict[str, str]:
    """Return payment instructions for a user."""
    return {
        "address": MASTER_XRP_ADDRESS,
        "memo": username,
        "xrp_amount": str(SUBSCRIPTION_PRICE_XRP),
        "rlusd_amount": str(SUBSCRIPTION_PRICE_RLUSD),
        "rlusd_issuer": RLUSD_ISSUER,
        "instructions": (
            f"Send exactly {SUBSCRIPTION_PRICE_XRP} XRP or {SUBSCRIPTION_PRICE_RLUSD} RLUSD to:\n"
            f"Address: {MASTER_XRP_ADDRESS}\n"
            f"Memo: {username}\n\n"
            f"Important: Include your username ({username}) in the memo field.\n"
            f"Without the memo, we cannot credit your account."
        ),
    }
