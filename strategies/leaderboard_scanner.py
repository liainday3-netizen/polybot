"""
POLYBOT — Leaderboard Scanner
Auto-discover top traders from Polymarket leaderboard.
"""
import asyncio
import aiohttp
import json
from typing import List, Dict


LEADERBOARD_URL = "https://polymarket.com/api/leaderboard"
GAMMA_API = "https://gamma-api.polymarket.com"


class LeaderboardScanner:
    """Scans Polymarket leaderboard for top performing wallets."""

    def __init__(self):
        self.session = None

    async def connect(self):
        self.session = aiohttp.ClientSession()

    async def disconnect(self):
        if self.session:
            await self.session.close()

    async def fetch_leaderboard(self, limit: int = 50, period: str = "90d") -> List[Dict]:
        """Fetch top traders from Polymarket leaderboard API."""
        try:
            params = {
                "limit": limit,
                "period": period,
                "sortBy": "profit"
            }
            async with self.session.get(
                f"{GAMMA_API}/leaderboard",
                params=params
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data if isinstance(data, list) else data.get("results", [])
                else:
                    print(f"⚠️  Leaderboard API returned {resp.status}")
                    return []
        except Exception as e:
            print(f"❌ Error fetching leaderboard: {e}")
            return []

    def score_trader(self, trader: Dict) -> float:
        """Score a trader 0-100 based on performance metrics."""
        pnl = float(trader.get("pnl", trader.get("profit", 0)))
        volume = float(trader.get("volume", 0))
        markets = int(trader.get("markets_traded", trader.get("marketsTraded", 0)))
        win_rate = float(trader.get("win_rate", trader.get("winRate", 0)))

        # Scoring formula
        score = 0.0

        # PNL contribution (0-30 points)
        if pnl > 50000:
            score += 30
        elif pnl > 20000:
            score += 25
        elif pnl > 10000:
            score += 20
        elif pnl > 5000:
            score += 15
        elif pnl > 1000:
            score += 10
        elif pnl > 0:
            score += 5

        # Win rate contribution (0-30 points)
        if win_rate > 0:
            score += min(30, win_rate * 0.4)

        # Volume contribution (0-20 points)
        if volume > 100000:
            score += 20
        elif volume > 50000:
            score += 15
        elif volume > 10000:
            score += 10
        elif volume > 1000:
            score += 5

        # Diversification (0-20 points)
        if markets > 100:
            score += 20
        elif markets > 50:
            score += 15
        elif markets > 20:
            score += 10
        elif markets > 5:
            score += 5

        return round(min(100, score), 1)

    def categorize_trader(self, trader: Dict) -> str:
        """Categorize trader by primary market type."""
        # Simple heuristic based on available data
        username = trader.get("username", trader.get("name", "")).lower()
        if any(w in username for w in ["election", "politics", "vote", "trump", "biden"]):
            return "politics"
        elif any(w in username for w in ["crypto", "btc", "eth", "defi"]):
            return "crypto"
        elif any(w in username for w in ["sport", "nfl", "nba", "soccer"]):
            return "sports"
        return "general"

    async def scan(self, top_n: int = 10) -> List[Dict]:
        """Full scan: fetch, score, and rank traders."""
        await self.connect()

        print()
        print("🔍 Scanning Polymarket leaderboard...")
        print()

        traders = await self.fetch_leaderboard(limit=50)

        if not traders:
            print("❌ Could not fetch leaderboard data.")
            print("   Try visiting https://polymarket.com/leaderboard manually.")
            await self.disconnect()
            return []

        # Score and rank
        scored = []
        for t in traders:
            score = self.score_trader(t)
            category = self.categorize_trader(t)
            scored.append({
                "username": t.get("username", t.get("name", "Unknown")),
                "address": t.get("address", t.get("wallet", "0x???")),
                "pnl": float(t.get("pnl", t.get("profit", 0))),
                "win_rate": float(t.get("win_rate", t.get("winRate", 0))),
                "markets": int(t.get("markets_traded", t.get("marketsTraded", 0))),
                "score": score,
                "category": category
            })

        # Sort by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_n]

        # Display results
        print(f"Top {top_n} wallets for copy-trading:")
        print()
        print(f"{'#':<4} {'Username':<18} {'PNL':<12} {'Win%':<7} {'Markets':<9} {'Score':<7} {'Category'}")
        print("─" * 75)

        for i, t in enumerate(top, 1):
            pnl_str = f"${t['pnl']:,.0f}"
            win_str = f"{t['win_rate']:.0f}%" if t['win_rate'] > 0 else "N/A"
            print(
                f"{i:<4} {t['username'][:17]:<18} {pnl_str:<12} {win_str:<7} "
                f"{t['markets']:<9} {t['score']:<7} {t['category']}"
            )

        # Output TARGET_WALLETS format
        addresses = [t["address"] for t in top[:5] if t["address"] != "0x???"]
        if addresses:
            print()
            print("Copy this into your .env:")
            print(f"TARGET_WALLETS={','.join(addresses)}")

        await self.disconnect()
        return top


async def main():
    scanner = LeaderboardScanner()
    await scanner.scan(top_n=10)


if __name__ == "__main__":
    asyncio.run(main())
