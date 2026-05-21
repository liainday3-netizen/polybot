"""
POLYBOT — Trade Journal
CSV export of all trading activity.
"""
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict


JOURNAL_FILE = Path(__file__).parent.parent / "logs" / "trades.csv"
DAILY_FILE = Path(__file__).parent.parent / "logs" / "daily_summary.csv"


class TradeJournal:
    """Exports trade history to CSV files."""

    @staticmethod
    def export_trades(trades: List[Dict], filepath: str = None) -> str:
        """Export trade list to CSV. Returns filepath."""
        output = Path(filepath) if filepath else JOURNAL_FILE
        output.parent.mkdir(exist_ok=True)

        if not trades:
            return str(output)

        fieldnames = [
            "id", "market", "side", "entry_price", "exit_price",
            "size_usdc", "pnl", "pnl_pct", "reason",
            "source_wallet", "open_time", "close_time", "duration_minutes"
        ]

        with open(output, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for trade in trades:
                writer.writerow(trade)

        return str(output)

    @staticmethod
    def append_daily_summary(date: str, pnl: float, trades: int, wins: int, losses: int):
        """Append daily P&L summary to CSV."""
        DAILY_FILE.parent.mkdir(exist_ok=True)
        file_exists = DAILY_FILE.exists()

        with open(DAILY_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["date", "pnl", "trades", "wins", "losses", "win_rate"])
            win_rate = (wins / trades * 100) if trades > 0 else 0
            writer.writerow([date, f"{pnl:.2f}", trades, wins, losses, f"{win_rate:.1f}"])
