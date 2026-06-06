"""
POLYBOT — Risk Manager
Validates all trades against risk parameters before execution.
"""
import time
from typing import Optional, Dict, Tuple
from core.config import config


class RiskManager:
    """Enforces risk limits and circuit breakers."""

    def __init__(self):
        self.daily_pnl: float = 0.0
        self.daily_reset_time: int = self._get_day_start()
        self.consecutive_wins: int = 0
        self.current_scale: float = 1.0

    def _get_day_start(self) -> int:
        """Get timestamp for start of current day (UTC)."""
        now = int(time.time())
        return now - (now % 86400)

    def _check_day_reset(self):
        """Reset daily counters if new day."""
        current_day = self._get_day_start()
        if current_day > self.daily_reset_time:
            self.daily_pnl = 0.0
            self.daily_reset_time = current_day

    def validate_trade(
        self,
        size_usdc: float,
        price: float,
        open_positions: int
    ) -> Tuple[bool, str]:
        """
        Validate a trade against all risk parameters.
        Returns (is_valid, reason).
        """
        self._check_day_reset()

        # Check circuit breaker (daily loss limit)
        if abs(self.daily_pnl) >= config.DAILY_LOSS_LIMIT and self.daily_pnl < 0:
            return False, f"Circuit breaker: daily loss ${abs(self.daily_pnl):.2f} >= ${config.DAILY_LOSS_LIMIT}"

        # Check max open positions
        if open_positions >= config.MAX_OPEN_POSITIONS:
            return False, f"Max positions reached: {open_positions}/{config.MAX_OPEN_POSITIONS}"

        # Check trade size
        max_trade = config.max_per_trade * self.current_scale
        if size_usdc > max_trade:
            return False, f"Trade size ${size_usdc:.2f} exceeds max ${max_trade:.2f}"

        # Check minimum trade size
        if size_usdc < 1.0:
            return False, f"Trade size ${size_usdc:.2f} below minimum $1.00"

        # Check price bounds
        if price <= 0 or price >= 1:
            return False, f"Invalid price: {price} (must be 0 < price < 1)"

        return True, "OK"

    def calculate_position_size(self, target_size: float) -> float:
        """
        Calculate our position size based on target's trade.
        Applies scale factor and caps at max per trade.
        """
        # Scale to configured percentage of target's size
        our_size = target_size * (config.COPY_SCALE_FACTOR / 100)

        # Apply auto-scaling multiplier
        our_size *= self.current_scale

        # Cap at max per trade
        max_trade = config.max_per_trade * self.current_scale
        our_size = min(our_size, max_trade)

        # Floor at minimum
        our_size = max(our_size, 1.0)

        return round(our_size, 2)

    def record_trade_result(self, pnl: float):
        """Record a trade result for scaling and daily tracking."""
        self._check_day_reset()
        self.daily_pnl += pnl

        max_factor = getattr(config, "AUTO_SCALE_MAX_FACTOR", 3.0)
        loss_down  = getattr(config, "AUTO_SCALE_LOSS_DOWN_PCT", 10.0)
        dd_reset   = getattr(config, "AUTO_SCALE_DRAWDOWN_RESET_PCT", 15.0)

        if pnl > 0:
            self.consecutive_wins += 1
            if self.consecutive_wins >= config.AUTO_SCALE_WINS_REQUIRED:
                self.current_scale *= (1 + config.AUTO_SCALE_UP_PCT / 100)
                self.current_scale  = min(self.current_scale, max_factor)  # hard cap
                self.consecutive_wins = 0
                print(f"📈 Auto-scaled up! New scale: {self.current_scale:.2f}x (cap={max_factor:.1f}x)")
        else:
            self.consecutive_wins = 0
            # Shrink scale on every loss to prevent over-exposure during drawdowns
            self.current_scale *= (1 - loss_down / 100)
            self.current_scale  = max(self.current_scale, 0.25)  # floor at 25%
            print(f"📉 Scale trimmed on loss: {self.current_scale:.2f}x")

        # Drawdown circuit: if daily loss exceeds threshold, reset scale to 1.0
        if config.TOTAL_USDC > 0:
            daily_loss_pct = abs(self.daily_pnl) / config.TOTAL_USDC * 100
            if self.daily_pnl < 0 and daily_loss_pct >= dd_reset:
                self.current_scale = 1.0
                self.consecutive_wins = 0
                print(f"⚠️  Drawdown reset: daily loss {daily_loss_pct:.1f}% >= {dd_reset:.0f}% — scale reset to 1.0x")

    def check_stop_loss(self, entry_price: float, current_price: float, side: str) -> bool:
        """
        Check if position should be stopped out.
        Uses plain fixed stop-loss (fallback when no peak is available).
        Prefer check_trailing_stop() when peak_price is tracked.
        """
        if side == "BUY":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        return pnl_pct <= -config.STOP_LOSS_PCT

    def check_trailing_stop(
        self,
        peak_price: float,
        current_price: float,
        side: str,
    ) -> bool:
        """
        Trailing stop: fires when price retreats TRAILING_STOP_PCT% from peak.
        For BUY  → peak is the highest price seen since entry.
        For SELL → peak is the lowest price seen since entry.

        Falls back to plain stop-loss when peak hasn't moved past entry.
        """
        if peak_price <= 0:
            return False

        if side == "BUY":
            # Exit if current price is X% below the peak
            drawdown_pct = ((peak_price - current_price) / peak_price) * 100
        else:
            # For short, exit if price rose X% above the lowest point
            drawdown_pct = ((current_price - peak_price) / peak_price) * 100

        return drawdown_pct >= config.TRAILING_STOP_PCT

    def kelly_size(self, price: float) -> float:
        """
        Kelly Criterion position sizing.
        Estimates optimal bet fraction given:
          - b  = odds paid on win  = (1/price - 1)   [binary prediction market]
          - p  = estimated win probability = (1 - price) + edge
          - Kelly fraction f = (b*p - (1-p)) / b
        Uses half-Kelly (KELLY_FRACTION) for robustness.
        Always capped at max_per_trade.
        """
        edge = config.KELLY_EDGE_ESTIMATE
        # Clamp price to tradeable range
        p_market = max(min(price, 0.95), 0.05)
        p_win = min(max((1 - p_market) + edge, 0.05), 0.95)
        b = (1.0 / p_market) - 1.0
        if b <= 0:
            return max(1.0, round(config.max_per_trade * 0.1, 2))
        kelly_f = (b * p_win - (1 - p_win)) / b
        kelly_f = max(kelly_f, 0.0)
        # Apply fractional Kelly and convert to dollar amount
        size = config.TOTAL_USDC * kelly_f * config.KELLY_FRACTION
        size = max(size, 1.0)
        size = min(size, config.max_per_trade)
        return round(size, 2)

    def check_take_profit(self, entry_price: float, current_price: float, side: str) -> bool:
        """Check if position should take profit."""
        if side == "BUY":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        return pnl_pct >= config.TAKE_PROFIT_PCT

    def scale_up(self, pct: float = 25.0):
        """Manually scale up position sizing."""
        self.current_scale *= (1 + pct / 100)
        print(f"📈 Manual scale up: {self.current_scale:.2f}x")

    def scale_down(self, pct: float = 25.0):
        """Manually scale down position sizing."""
        self.current_scale *= (1 - pct / 100)
        self.current_scale = max(self.current_scale, 0.1)  # Floor at 10%
        print(f"📉 Manual scale down: {self.current_scale:.2f}x")

    def get_status(self) -> Dict:
        """Get current risk status."""
        return {
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_limit": config.DAILY_LOSS_LIMIT,
            "circuit_breaker_active": self.daily_pnl <= -config.DAILY_LOSS_LIMIT,
            "current_scale": round(self.current_scale, 2),
            "consecutive_wins": self.consecutive_wins,
            "max_per_trade": round(config.max_per_trade * self.current_scale, 2)
        }
