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

        if pnl > 0:
            self.consecutive_wins += 1
            # Auto-scale up after consecutive wins
            if self.consecutive_wins >= config.AUTO_SCALE_WINS_REQUIRED:
                self.current_scale *= (1 + config.AUTO_SCALE_UP_PCT / 100)
                self.consecutive_wins = 0
                print(f"📈 Auto-scaled up! New scale: {self.current_scale:.2f}x")
        else:
            self.consecutive_wins = 0

    def check_stop_loss(self, entry_price: float, current_price: float, side: str) -> bool:
        """Check if position should be stopped out."""
        if side == "BUY":
            pnl_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

        return pnl_pct <= -config.STOP_LOSS_PCT

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
