"""
POLYBOT — Polymarket CLOB API Client
Uses py-clob-client for authenticated order placement (proper EIP-712 signing).
Uses aiohttp for public read endpoints (markets, order book, prices).
"""
import asyncio
from functools import partial
from typing import Optional, Dict, List

import aiohttp

from core.config import config


# ── py-clob-client singleton (sync; lazy-init after config is ready) ─────

_clob_client = None


def _get_clob():
    """Return (or create) the py-clob-client singleton."""
    global _clob_client
    if _clob_client is None:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        from py_clob_client.constants import POLYGON

        creds = ApiCreds(
            api_key=config.API_KEY,
            api_secret=config.API_SECRET,
            api_passphrase=config.API_PASSPHRASE,
        )
        _clob_client = ClobClient(
            host=config.CLOB_API_URL.rstrip("/"),
            chain_id=POLYGON,
            key=config.PRIVATE_KEY,
            funder=config.WALLET_ADDRESS,
            signature_type=0,   # EOA (externally owned account)
            creds=creds,
        )
    return _clob_client


class PolymarketClient:
    """Async client for Polymarket CLOB API."""

    # Gamma API gives richer market metadata than CLOB /markets
    GAMMA_URL = "https://gamma-api.polymarket.com"

    def __init__(self):
        self.base_url = config.CLOB_API_URL.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None

    async def connect(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession()

    async def disconnect(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    # ── Public / read endpoints (no auth required) ────────────────────────

    async def get_markets(self, limit: int = 100, active_only: bool = True) -> List[Dict]:
        """Fetch active markets. Tries Gamma API first (richer data), falls back to CLOB."""
        params = {
            "limit": limit,
            "active": "true" if active_only else "false",
            "closed": "false",
        }
        try:
            async with self.session.get(
                f"{self.GAMMA_URL}/markets",
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("data", data)
        except Exception:
            pass
        # Fallback: CLOB public markets endpoint
        try:
            async with self.session.get(
                f"{self.base_url}/markets",
                params={"limit": limit},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return []

    async def get_market(self, condition_id: str) -> Optional[Dict]:
        """Fetch a single market by condition ID."""
        try:
            async with self.session.get(
                f"{self.base_url}/markets/{condition_id}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return None

    async def get_order_book(self, token_id: str) -> Dict:
        """
        Fetch order book for a specific token.
        Returns bids descending (best bid first), asks ascending (best ask first).
        """
        try:
            async with self.session.get(
                f"{self.base_url}/book",
                params={"token_id": token_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {"bids": [], "asks": []}

    async def get_price(self, token_id: str) -> Optional[float]:
        """Get current mid-price for a token from the order book."""
        book = await self.get_order_book(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        try:
            if bids and asks:
                bid0 = bids[0]
                ask0 = asks[0]
                best_bid = float(bid0["price"] if isinstance(bid0, dict) else bid0)
                best_ask = float(ask0["price"] if isinstance(ask0, dict) else ask0)
                return (best_bid + best_ask) / 2
            if bids:
                b = bids[0]
                return float(b["price"] if isinstance(b, dict) else b)
            if asks:
                a = asks[0]
                return float(a["price"] if isinstance(a, dict) else a)
        except (KeyError, TypeError, ValueError):
            pass
        return None

    async def get_wallet_activity(
        self, wallet: str, since_timestamp: int = 0
    ) -> List[Dict]:
        """Fetch recent trade activity for a target wallet (for copy-trading)."""
        params = {"maker": wallet, "after": since_timestamp, "limit": 50}
        try:
            async with self.session.get(
                f"{self.base_url}/trades",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return data.get("data", [])
        except Exception:
            pass
        return []

    # ── Authenticated order operations (EIP-712 via py-clob-client) ───────

    async def place_order(
        self,
        token_id: str,
        side: str,          # "BUY" or "SELL"
        price: float,
        size: float,
        order_type: str = "FOK",
    ) -> Optional[Dict]:
        """
        Place a signed order on the Polymarket CLOB.

        Uses py-clob-client for proper EIP-712 typed-data signing —
        the previous HMAC / personal_sign approach was rejected by the exchange.
        The sync client methods run in a thread-pool executor.
        """
        from py_clob_client.clob_types import OrderArgs, OrderType

        ot = OrderType.FOK if order_type.upper() == "FOK" else OrderType.GTC

        order_args = OrderArgs(
            price=float(round(price, 4)),
            size=float(round(size, 4)),
            side=side.upper(),
            token_id=token_id,
        )

        loop = asyncio.get_event_loop()
        clob = _get_clob()

        try:
            signed_order = await loop.run_in_executor(
                None, partial(clob.create_order, order_args)
            )
            result = await loop.run_in_executor(
                None, partial(clob.post_order, signed_order, ot)
            )
        except Exception as exc:
            raise RuntimeError(
                f"place_order failed ({side} {size} @ {price}): {exc}"
            ) from exc

        if isinstance(result, dict):
            return result
        if result:
            return {"id": str(result)}
        return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        loop = asyncio.get_event_loop()
        clob = _get_clob()
        try:
            result = await loop.run_in_executor(
                None, partial(clob.cancel, order_id)
            )
            return bool(result)
        except Exception:
            return False
