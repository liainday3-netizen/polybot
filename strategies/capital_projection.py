"""
POLYBOT — Capital Projection Engine (v2)
Live financial market data via CoinGecko.

Projects portfolio growth under Conservative / Base / Optimistic scenarios
with ROI rates dynamically calibrated against real-time market regime
(BTC + ETH 24h trend). Also exposes score threshold and sizing adjustments
consumed by AutoTrader at scan time.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ── CoinGecko free API (no key required) ─────────────────────────────────────
COINGECKO_URL = "https://api.coingecko.com/api/v3"

# ── Regime detection (BTC + ETH weighted 24h change) ─────────────────────────
BULL_THRESHOLD = 2.0    # > +2%  → bull
BEAR_THRESHOLD = -2.0   # < -2%  → bear

# ── Base ROI scenarios (annually compounded) ─────────────────────────────────
BASE_SCENARIOS = {
    "conservative": {"label": "Conservative", "color": "#42a5f5", "annual_roi": 0.20},
    "base":         {"label": "Base",          "color": "#7c5cfc", "annual_roi": 0.40},
    "optimistic":   {"label": "Optimistic",    "color": "#00d68f", "annual_roi": 0.70},
}

# ROI multipliers per regime
REGIME_ROI_MULT = {
    "bull":     {"conservative": 1.20, "base": 1.25, "optimistic": 1.30},
    "sideways": {"conservative": 1.00, "base": 1.00, "optimistic": 1.00},
    "bear":     {"conservative": 0.70, "base": 0.75, "optimistic": 0.80},
}

# AutoTrader: delta applied to AUTO_TRADE_MIN_SCORE
REGIME_SCORE_DELTA: Dict[str, float] = {
    "bull":     -5.0,   # easier to fire in bull market
    "sideways":  0.0,
    "bear":    +10.0,   # much more selective in bear market
}

# AutoTrader: position sizing multiplier
REGIME_SIZE_MULT: Dict[str, float] = {
    "bull":     1.15,
    "sideways": 1.00,
    "bear":     0.80,
}


# ── Market context ─────────────────────────────────────────────────────────────

class MarketContext:
    """Live market snapshot returned by CapitalProjectionEngine."""

    def __init__(
        self,
        btc_price: float,
        eth_price: float,
        matic_price: float,
        btc_24h_change: float,
        eth_24h_change: float,
        regime: str,
        fetched_at: float,
    ):
        self.btc_price = btc_price
        self.eth_price = eth_price
        self.matic_price = matic_price
        self.btc_24h_change = btc_24h_change
        self.eth_24h_change = eth_24h_change
        self.regime = regime          # "bull" | "sideways" | "bear"
        self.fetched_at = fetched_at

    @property
    def age_seconds(self) -> float:
        return time.time() - self.fetched_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "btc_price": self.btc_price,
            "eth_price": self.eth_price,
            "matic_price": self.matic_price,
            "btc_24h_change_pct": round(self.btc_24h_change, 2),
            "eth_24h_change_pct": round(self.eth_24h_change, 2),
            "regime": self.regime,
            "age_seconds": round(self.age_seconds),
        }

    def __repr__(self) -> str:
        return (
            f"<MarketContext BTC=${self.btc_price:,.0f} "
            f"({self.btc_24h_change:+.1f}%) regime={self.regime}>"
        )


# ── Engine ─────────────────────────────────────────────────────────────────────

class CapitalProjectionEngine:
    """
    Live capital projection engine consumed by AutoTrader.

    Usage:
        ctx = await projection_engine.get_market_context()
        score_adj = projection_engine.get_score_adjustment(ctx)    # e.g. -5
        size_mult = projection_engine.get_size_multiplier(ctx)     # e.g. 1.15
        data      = projection_engine.project(balance, months=12, market_context=ctx)
    """

    CACHE_TTL_S = 300   # refresh every 5 minutes

    def __init__(self):
        self._market_context: Optional[MarketContext] = None
        # FIX: lock prevents concurrent duplicate fetches (race condition)
        self._fetch_lock = asyncio.Lock()

    # ── Live data fetch ────────────────────────────────────────────────────────

    async def _fetch(self) -> Optional[MarketContext]:
        params = {
            "ids": "bitcoin,ethereum,matic-network",
            "vs_currencies": "usd",
            "include_24hr_change": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{COINGECKO_URL}/simple/price", params=params)
                resp.raise_for_status()
                data = resp.json()

            # FIX: use `or 0` to guard against API returning explicit null values
            # (float(None) raises TypeError)
            btc_price  = float(data.get("bitcoin", {}).get("usd") or 0)
            btc_change = float(data.get("bitcoin", {}).get("usd_24h_change") or 0)
            eth_price  = float(data.get("ethereum", {}).get("usd") or 0)
            eth_change = float(data.get("ethereum", {}).get("usd_24h_change") or 0)
            matic_price = float(data.get("matic-network", {}).get("usd") or 0)

            # FIX: only classify regime if we actually have BTC price data
            # (avoids sideways misclassification when API key is missing)
            if btc_price == 0:
                logger.warning("[CapProjection] BTC price missing — skipping regime update")
                return None

            # Regime: BTC dominates (70%), ETH secondary (30%)
            combined = 0.70 * btc_change + 0.30 * eth_change
            if combined >= BULL_THRESHOLD:
                regime = "bull"
            elif combined <= BEAR_THRESHOLD:
                regime = "bear"
            else:
                regime = "sideways"

            ctx = MarketContext(
                btc_price=btc_price,
                eth_price=eth_price,
                matic_price=matic_price,
                btc_24h_change=btc_change,
                eth_24h_change=eth_change,
                regime=regime,
                fetched_at=time.time(),
            )
            logger.info(
                f"[CapProjection] {ctx}  score_delta={REGIME_SCORE_DELTA[regime]:+.0f}  "
                f"size_mult={REGIME_SIZE_MULT[regime]}"
            )
            return ctx

        except Exception as exc:
            logger.warning(f"[CapProjection] CoinGecko fetch failed: {exc}")
            return None     # caller falls back to stale cache

    async def get_market_context(self, force: bool = False) -> Optional[MarketContext]:
        """Return cached context, refreshing automatically when stale.
        FIX: uses asyncio.Lock to prevent concurrent duplicate API calls.
        """
        stale = (
            self._market_context is None
            or self._market_context.age_seconds > self.CACHE_TTL_S
        )
        if force or stale:
            async with self._fetch_lock:
                # Re-check inside lock in case another coroutine already refreshed
                stale_inner = (
                    self._market_context is None
                    or self._market_context.age_seconds > self.CACHE_TTL_S
                )
                if force or stale_inner:
                    fresh = await self._fetch()
                    if fresh is not None:
                        self._market_context = fresh
        return self._market_context

    # ── AutoTrader helpers ─────────────────────────────────────────────────────

    def get_score_adjustment(self, ctx: Optional[MarketContext]) -> float:
        """Delta (positive = raise threshold, negative = lower) for AUTO_TRADE_MIN_SCORE."""
        if ctx is None:
            return 0.0
        return REGIME_SCORE_DELTA.get(ctx.regime, 0.0)

    def get_size_multiplier(self, ctx: Optional[MarketContext]) -> float:
        """Multiplier applied to calculated position size before order placement."""
        if ctx is None:
            return 1.0
        return REGIME_SIZE_MULT.get(ctx.regime, 1.0)

    # ── Projection ─────────────────────────────────────────────────────────────

    def project(
        self,
        start_capital: float,
        months: int = 12,
        market_context: Optional[MarketContext] = None,
    ) -> Dict[str, Any]:
        """
        Return compounded growth curves for all three scenarios.
        ROI rates are scaled by the current market regime when context is available.
        """
        regime = market_context.regime if market_context else "sideways"
        roi_mults = REGIME_ROI_MULT.get(regime, REGIME_ROI_MULT["sideways"])

        labels = ["Now"] + [f"M{i}" for i in range(1, months + 1)]
        result: Dict[str, Any] = {
            "start_capital": round(start_capital, 2),
            "months": months,
            "labels": labels,
            "regime": regime,
            "market_context": market_context.to_dict() if market_context else None,
            "scenarios": {},
            "milestones": {"double": {}, "triple": {}, "ten_x": {}},
        }

        for key, meta in BASE_SCENARIOS.items():
            adj_roi = meta["annual_roi"] * roi_mults[key]
            rate = (1 + adj_roi) ** (1 / 12) - 1
            values = [round(start_capital * (1 + rate) ** m, 2) for m in range(months + 1)]
            result["scenarios"][key] = {
                "label": meta["label"],
                "color": meta["color"],
                "annual_roi": round(adj_roi, 4),
                "values": values,
            }
            for ms_key, mult in [("double", 2), ("triple", 3), ("ten_x", 10)]:
                target = start_capital * mult
                hit = next((m for m, v in enumerate(values) if v >= target), None)
                result["milestones"][ms_key][key] = hit

        return result


# ── Singleton used across the bot ─────────────────────────────────────────────
projection_engine = CapitalProjectionEngine()
