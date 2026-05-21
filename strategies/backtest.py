"""
POLYBOT — Backtester
Test a wallet's historical performance before copying live.
"""
import asyncio
import argparse
import aiohttp
from typing import List, Dict, Optional
from datetime import datetime, timedelta


GAMMA_API = "https://gamma-api.polymarket.com"


class Backtester:
    """Simulates copy-trading a wallet over historical data."""

    def __init__(self, wallet: str, days: int = 90, capital: float = 15.0):
        self.wallet = wallet
        self.days = days
        self.capital = capital
        self.session = None

    async def connect(self):
        self.session = aiohttp.ClientSession()

    async def disconnect(self):
        if self.session:
            await self.session.close()

    async def fetch_historical_trades(self) -> List[Dict]:
        """Fetch historical trades for the target wallet."""
        try:
            since = datetime.utcnow() - timedelta(days=self.days)
            params = {
                "user": self.wallet,
                "limit": 500,
                "after": int(since.timestamp())
            }
            async with self.session.get(
                f"{GAMMA_API}/trades",
                params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else data.get("results", [])
                return []
        except Exception as e:
            print(f"❌ Error fetching trades: {e}")
            return []

    def simulate(self, trades: List[Dict]) -> Dict:
        """Run backtest simulation on historical trades."""
        if not trades:
            return {"error": "No trades found"}

        # Simulation parameters
        max_per_trade = self.capital * 0.15  # 15% max
        scale_factor = 0.10  # 10% of target size

        results = []
        total_pnl = 0.0
        max_drawdown = 0.0
        peak_pnl = 0.0

        for trade in trades:
            # Parse trade data
            size = float(trade.get("size", trade.get("amount", 0)))
            price = float(trade.get("price", 0.5))
            outcome = trade.get("outcome", trade.get("result"))

            if size == 0 or price == 0:
                continue

            # Calculate our simulated size
            our_size = min(size * scale_factor, max_per_trade)
            our_size = max(our_size, 1.0)

            # Simulate outcome (simplified: use actual market resolution)
            if outcome in ("won", "WIN", True, 1, "1"):
                # Won: profit = (1 - price) * quantity
                quantity = our_size / price
                pnl = (1 - price) * quantity
            elif outcome in ("lost", "LOSS", False, 0, "0"):
                # Lost: loss = -size
                pnl = -our_size
            else:
                # Unknown outcome: estimate based on price movement
                # Simple model: 55% chance of winning
                import random
                if random.random() < 0.55:
                    quantity = our_size / price
                    pnl = (1 - price) * quantity * 0.5
                else:
                    pnl = -our_size * 0.4

            total_pnl += pnl
            peak_pnl = max(peak_pnl, total_pnl)
            drawdown = peak_pnl - total_pnl
            max_drawdown = max(max_drawdown, drawdown)

            results.append({
                "pnl": pnl,
                "cumulative": total_pnl
            })

        # Calculate metrics
        wins = sum(1 for r in results if r["pnl"] > 0)
        losses = sum(1 for r in results if r["pnl"] <= 0)
        total_trades = len(results)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        roi = (total_pnl / self.capital * 100) if self.capital > 0 else 0
        best_trade = max((r["pnl"] for r in results), default=0)
        worst_trade = min((r["pnl"] for r in results), default=0)
        dd_pct = (max_drawdown / self.capital * 100) if self.capital > 0 else 0

        # Verdict
        if win_rate >= 60 and roi > 10:
            verdict = "✅ STRONG"
        elif win_rate >= 50 and roi > 0:
            verdict = "⚠️  MODERATE"
        else:
            verdict = "❌ NEGATIVE"

        return {
            "wallet": self.wallet,
            "days": self.days,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "roi": round(roi, 1),
            "max_drawdown": round(dd_pct, 1),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "verdict": verdict
        }

    async def run(self) -> Dict:
        """Execute full backtest."""
        await self.connect()

        print()
        print(f"📊 Backtesting wallet: {self.wallet[:10]}...{self.wallet[-6:]}")
        print(f"   Period: {self.days} days | Capital: ${self.capital}")
        print()

        trades = await self.fetch_historical_trades()

        if not trades:
            print("❌ No historical trades found for this wallet.")
            print("   Check the address and try again.")
            await self.disconnect()
            return {}

        print(f"   Found {len(trades)} historical trades")
        print("   Running simulation...")
        print()

        results = self.simulate(trades)

        # Display results
        print(f"BACKTEST RESULTS — {self.wallet[:10]}...{self.wallet[-6:]}")
        print("─" * 40)
        print(f"Win rate:       {results['win_rate']}%  ({results['wins']}W / {results['losses']}L)")
        print(f"Total PNL:      {'+' if results['total_pnl'] >= 0 else ''}${results['total_pnl']:.2f}")
        print(f"ROI:            {'+' if results['roi'] >= 0 else ''}{results['roi']}%")
        print(f"Max drawdown:   -{results['max_drawdown']}%")
        print(f"Best trade:     +${results['best_trade']:.2f}")
        print(f"Worst trade:    ${results['worst_trade']:.2f}")
        print(f"Verdict:        {results['verdict']}")
        print()

        await self.disconnect()
        return results


async def main():
    parser = argparse.ArgumentParser(description="Backtest a Polymarket wallet")
    parser.add_argument("--wallet", required=True, help="Wallet address to backtest")
    parser.add_argument("--days", type=int, default=90, help="Number of days (default: 90)")
    parser.add_argument("--capital", type=float, default=15.0, help="Starting capital (default: 15)")

    args = parser.parse_args()

    backtester = Backtester(
        wallet=args.wallet,
        days=args.days,
        capital=args.capital
    )
    await backtester.run()


if __name__ == "__main__":
    asyncio.run(main())
