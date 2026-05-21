"""
POLYBOT — Position Manager
Tracks open positions, handles persistence, and monitors exits.
"""
import json
import time
import csv
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


POSITIONS_FILE = Path(__file__).parent.parent / "logs" / "positions.json"
TRADES_FILE = Path(__file__).parent.parent / "logs" / "trades.csv"
DAILY_FILE = Path(__file__).parent.parent / "logs" / "daily_summary.csv"


@dataclass
class Position:
    """Represents an open trading position."""
    id: str
    market: str
    token_id: str
    side: str  # "BUY" or "SELL"
    entry_price: float
    size_usdc: float
    quantity: float
    timestamp: int
    source_wallet: str
    order_id: str = ""
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: str = "open"  # open, closed, stopped, profit_taken

    def update_pnl(self, current_price: float):
        """Update P&L based on current price."""
        self.current_price = current_price
        if self.side == "BUY":
            self.pnl = (current_price - self.entry_price) * self.quantity
            self.pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            self.pnl = (self.entry_price - current_price) * self.quantity
            self.pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100


class PositionManager:
    """Manages all open and closed positions with persistence."""

    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[Dict] = []
        self._ensure_log_dir()
        self._load_positions()

    def _ensure_log_dir(self):
        """Create logs directory if it doesn't exist."""
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

    def _load_positions(self):
        """Load positions from persistent storage."""
        if POSITIONS_FILE.exists():
            try:
                data = json.loads(POSITIONS_FILE.read_text())
                for pid, pdata in data.items():
                    self.positions[pid] = Position(**pdata)
            except (json.JSONDecodeError, TypeError):
                self.positions = {}

    def _save_positions(self):
        """Save positions to persistent storage."""
        data = {pid: asdict(p) for pid, p in self.positions.items() if p.status == "open"}
        POSITIONS_FILE.write_text(json.dumps(data, indent=2))

    def open_position(
        self,
        market: str,
        token_id: str,
        side: str,
        entry_price: float,
        size_usdc: float,
        source_wallet: str,
        order_id: str = ""
    ) -> Position:
        """Record a new open position."""
        quantity = size_usdc / entry_price if entry_price > 0 else 0
        pos_id = f"POS-{int(time.time() * 1000)}"

        position = Position(
            id=pos_id,
            market=market,
            token_id=token_id,
            side=side,
            entry_price=entry_price,
            size_usdc=size_usdc,
            quantity=quantity,
            timestamp=int(time.time()),
            source_wallet=source_wallet,
            order_id=order_id
        )

        self.positions[pos_id] = position
        self._save_positions()
        return position

    def close_position(self, pos_id: str, exit_price: float, reason: str = "manual") -> Optional[Dict]:
        """Close a position and record the trade."""
        if pos_id not in self.positions:
            return None

        pos = self.positions[pos_id]
        pos.update_pnl(exit_price)
        pos.status = reason  # "stopped", "profit_taken", "manual"

        trade_record = {
            "id": pos.id,
            "market": pos.market,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "size_usdc": pos.size_usdc,
            "quantity": pos.quantity,
            "pnl": round(pos.pnl, 4),
            "pnl_pct": round(pos.pnl_pct, 2),
            "reason": reason,
            "source_wallet": pos.source_wallet,
            "open_time": pos.timestamp,
            "close_time": int(time.time()),
            "duration_minutes": (int(time.time()) - pos.timestamp) // 60
        }

        self.closed_trades.append(trade_record)
        self._log_trade(trade_record)
        del self.positions[pos_id]
        self._save_positions()

        return trade_record

    def _log_trade(self, trade: Dict):
        """Append trade to CSV journal."""
        file_exists = TRADES_FILE.exists()
        with open(TRADES_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=trade.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade)

    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.status == "open"]

    def get_position(self, pos_id: str) -> Optional[Position]:
        """Get a specific position."""
        return self.positions.get(pos_id)

    @property
    def open_count(self) -> int:
        """Number of open positions."""
        return len([p for p in self.positions.values() if p.status == "open"])

    @property
    def total_invested(self) -> float:
        """Total USDC currently in open positions."""
        return sum(p.size_usdc for p in self.positions.values() if p.status == "open")

    @property
    def unrealized_pnl(self) -> float:
        """Total unrealized P&L across open positions."""
        return sum(p.pnl for p in self.positions.values() if p.status == "open")

    def get_summary(self) -> Dict:
        """Get portfolio summary."""
        open_positions = self.get_open_positions()
        realized = sum(t["pnl"] for t in self.closed_trades)
        unrealized = sum(p.pnl for p in open_positions)
        wins = sum(1 for t in self.closed_trades if t["pnl"] > 0)
        total_trades = len(self.closed_trades)

        return {
            "open_positions": len(open_positions),
            "total_trades": total_trades,
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(realized + unrealized, 2),
            "win_rate": round((wins / total_trades * 100) if total_trades > 0 else 0, 1),
            "total_invested": round(self.total_invested, 2)
        }
