"""
POLYBOT — Autonomous Trading Strategy
Scans Polymarket markets independently for high-value opportunities
based on momentum, liquidity, and probability-zone signals.
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple

from core.config import config
from utils.logger import BotLogger


class MarketSignal:
    """Represents a detected trading opportunity."""

    def __init__(
        self,
        token_id: str,
        market_name: str,
        side: str,
        price: float,
        score: float,
        reason: str,
    ):
        self.token_id = token_id
        self.market_name = market_name
        self.side = side
        self.price = price
        self.score = score
        self.reason = reason

    def __repr__(self):
        return (
            f"<Signal {self.market_name[:30]} | {self.side} @ {self.price:.3f} "
            f"| score={self.score:.0f} | {self.reason}>"
        )


class AutoTrader:
    """
    Autonomous market scanner and signal generator.

    Scoring model (0–100):
      - Liquidity  (0–30): tight spread and decent order depth
      - Price zone (0–30): probability between 15% and 85% (tradeable range)
      - Momentum   (0–40): recent price movement above noise threshold

    A signal fires when score >= AUTO_TRADE_MIN_SCORE (default 65).
    """

    # Price history: {token_id: [(timestamp, price), ...]}
    _price_history: Dict[str, List[Tuple[float, float]]] = {}
    # Momentum window: compare current price against price N seconds ago
    MOMENTUM_WINDOW_S = 20 * 60   # 20 minutes
    HISTORY_RETENTION_S = 60 * 60  # keep 1 hour of history

    # Min spread to consider a market tradeable (in price units, 0–1)
    MAX_SPREAD = 0.08
    # Probability extremes to skip (too close to certainty)
    MIN_PRICE = 0.10
    MAX_PRICE = 0.90
    # Minimum price movement to register momentum
    MOMENTUM_THRESHOLD = 0.06   # 6 cents / 6 probability points

    def __init__(self, client, logger: Optional[BotLogger] = None):
        self.client = client
        self.logger = logger or BotLogger()
        self._daily_auto_trades = 0
        self._last_reset_day = -1

    def _reset_daily_counter(self):
        today = int(time.time() // 86400)
        if today != self._last_reset_day:
            self._daily_auto_trades = 0
            self._last_reset_day = today

    def _record_price(self, token_id: str, price: float):
        """Store a price sample; prune old entries."""
        now = time.time()
        if token_id not in self._price_history:
            self._price_history[token_id] = []
        self._price_history[token_id].append((now, price))
        # Prune stale entries
        cutoff = now - self.HISTORY_RETENTION_S
        self._price_history[token_id] = [
            (ts, p) for ts, p in self._price_history[token_id] if ts > cutoff
        ]

    def _get_momentum(self, token_id: str, current_price: float) -> Tuple[float, str]:
        """
        Returns (momentum_delta, direction_str).
        delta = current_price - price MOMENTUM_WINDOW_S ago (positive = price rising).
        """
        history = self._price_history.get(token_id, [])
        if not history:
            return 0.0, "none"

        cutoff = time.time() - self.MOMENTUM_WINDOW_S
        # Find the oldest sample within our window
        baseline_samples = [(ts, p) for ts, p in history if ts <= cutoff]
        if not baseline_samples:
            # Not enough history yet — use oldest available
            baseline_price = history[0][1]
        else:
            baseline_price = baseline_samples[-1][1]

        delta = current_price - baseline_price
        direction = "up" if delta > 0 else "down"
        return delta, direction

    def _score_market(
        self,
        token_id: str,
        bid: float,
        ask: float,
    ) -> Tuple[float, str]:
        """
        Score a market token and return (score, reason_string).
        Score ranges 0–100.
        """
        reasons = []
        score = 0.0

        mid = (bid + ask) / 2
        spread = ask - bid

        # ── Liquidity score (0–30) ──────────────────────────────────
        if spread > self.MAX_SPREAD:
            return 0.0, f"spread too wide ({spread:.3f})"

        liquidity_score = max(0, 30 * (1 - spread / self.MAX_SPREAD))
        score += liquidity_score
        reasons.append(f"spread={spread:.3f}")

        # ── Price zone score (0–30) ─────────────────────────────────
        if mid < self.MIN_PRICE or mid > self.MAX_PRICE:
            return 0.0, f"price out of tradeable zone ({mid:.3f})"

        # Sweet zone: 25–75¢ gets full marks; taper toward edges
        distance_from_centre = abs(mid - 0.50)
        zone_score = 30 * max(0, 1 - (distance_from_centre / 0.25) ** 2)
        score += zone_score
        reasons.append(f"mid={mid:.3f}")

        # ── Momentum score (0–40) ─────────────────────────────────
        delta, direction = self._get_momentum(token_id, mid)
        abs_delta = abs(delta)

        if abs_delta >= self.MOMENTUM_THRESHOLD:
            # Cap momentum contribution at 3× threshold
            momentum_score = min(40, 40 * (abs_delta / (3 * self.MOMENTUM_THRESHOLD)))
            score += momentum_score
            reasons.append(f"momentum={delta:+.3f} ({direction})")
        else:
            reasons.append(f"low-momentum={delta:+.3f}")

        reason_str = " | ".join(reasons)
        return round(score, 1), reason_str

    def _pick_side(self, token_id: str, mid: float) -> str:
        """
        Follow momentum direction: if price is rising → BUY (bet it goes higher),
        if falling → SELL (short via NO).
        Fallback: BUY when below 50, SELL when above.
        """
        delta, _ = self._get_momentum(token_id, mid)
        if delta > self.MOMENTUM_THRESHOLD:
            return "BUY"
        elif delta < -self.MOMENTUM_THRESHOLD:
            return "SELL"
        return "BUY" if mid < 0.50 else "SELL"

    async def scan(self) -> Optional[MarketSignal]:
        """
        Scan active markets and return the best signal found, or None.
        Updates internal price history on every scan.
        """
        self._reset_daily_counter()
        max_daily = getattr(config, "AUTO_TRADE_MAX_DAILY", 3)
        if self._daily_auto_trades >= max_daily:
            self.logger.info(
                f"[AutoTrader] Daily limit reached ({max_daily} auto-trades). Skipping."
            )
            return None

        try:
            markets = await self.client.get_markets(limit=100, active_only=True)
        except Exception as e:
            self.logger.error(f"[AutoTrader] Failed to fetch markets: {e}")
            return None

        if not markets:
            return None

        best_signal: Optional[MarketSignal] = None
        best_score = getattr(config, "AUTO_TRADE_MIN_SCORE", 65)

        for market in markets:
            tokens = market.get("tokens") or market.get("clob_token_ids") or []
            market_name = market.get("question") or market.get("title") or "Unknown"

            for token in tokens:
                token_id = token if isinstance(token, str) else token.get("token_id", "")
                if not token_id:
                    continue

                try:
                    book = await self.client.get_order_book(token_id)
                except Exception:
                    continue

                bids = book.get("bids", [])
                asks = book.get("asks", [])
                if not bids or not asks:
                    continue

                bid = float(bids[0]["price"])
                ask = float(asks[0]["price"])
                mid = (bid + ask) / 2

                # Record price sample for momentum tracking
                self._record_price(token_id, mid)

                score, reason = self._score_market(token_id, bid, ask)

                if score > best_score:
                    best_score = score
                    side = self._pick_side(token_id, mid)
                    best_signal = MarketSignal(
                        token_id=token_id,
                        market_name=market_name,
                        side=side,
                        price=ask if side == "BUY" else bid,
                        score=score,
                        reason=reason,
                    )

                await asyncio.sleep(0.05)  # gentle rate-limit

        if best_signal:
            self.logger.info(
                f"[AutoTrader] 🎯 Best opportunity: {best_signal}"
            )
        else:
            self.logger.info("[AutoTrader] No qualifying signals this scan.")

        return best_signal

    def record_trade(self):
        """Call after successfully placing an auto-trade."""
        self._daily_auto_trades += 1
