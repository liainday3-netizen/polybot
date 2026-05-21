"""
POLYBOT — Logging Utility
Structured logging for all bot activity.
"""
import time
import logging
from pathlib import Path
from datetime import datetime


LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "bot.log"


class BotLogger:
    """Structured logger for PolyBot."""

    def __init__(self):
        LOG_DIR.mkdir(exist_ok=True)

        self.logger = logging.getLogger("polybot")
        self.logger.setLevel(logging.DEBUG)

        # File handler
        fh = logging.FileHandler(LOG_FILE)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter(
            '[%(asctime)s] %(message)s',
            datefmt='%H:%M:%S'
        ))

        if not self.logger.handlers:
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def info(self, msg: str):
        self.logger.info(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(f"❌ {msg}")

    def signal(self, wallet: str, market: str, price: float):
        msg = f"Signal: {wallet[:10]}... → '{market}' @ {price:.3f}"
        self.logger.info(msg)

    def trade_executed(self, size: float, price: float, order_id: str):
        msg = f"✅ Filled! ${size:.2f} @ {price:.3f} | OrderID: {order_id[:12]}..."
        self.logger.info(msg)

    def position_update(self, position):
        pnl_sign = "+" if position.pnl >= 0 else ""
        msg = (
            f"Position: {position.market[:30]} | "
            f"entry {position.entry_price:.3f}, "
            f"current {position.current_price:.3f}, "
            f"PNL {pnl_sign}${position.pnl:.2f}"
        )
        self.logger.debug(msg)
