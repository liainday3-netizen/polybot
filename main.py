"""
POLYBOT — Main Entry Point
Start the copy-trading bot with a health-check HTTP server
for Render free-tier web service compatibility.
"""
import asyncio
import signal
import os
from pathlib import Path
from aiohttp import web

from core.bot import PolyBot
from strategies.capital_projection import project as _project_capital
from core.config import config

FRONTEND_DIR = Path(__file__).parent / "frontend"


# Track server start time for uptime
_START_TIME = __import__('time').time()


async def health_check(request):
    """JSON health check — returns bot state for monitoring tools."""
    from time import time as _t
    return web.json_response({
        "status": "ok",
        "uptime_seconds": int(_t() - _START_TIME),
        "version": "1.2",
        "auto_trade": True,
    })


async def serve_dashboard(request):
    """Serve the trading dashboard."""
    dashboard_file = FRONTEND_DIR / "dashboard.html"
    if dashboard_file.exists():
        return web.FileResponse(dashboard_file)
    return web.Response(text="Dashboard not found", status=404)


async def serve_index(request):
    """Serve the landing/index page."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return web.FileResponse(index_file)
    return web.Response(text="OK", status=200)


async def api_projection(request):
    """Return capital projection JSON for the dashboard."""
    try:
        start = float(getattr(config, "TOTAL_USDC", 15.0))
    except Exception:
        start = 15.0
    months = int(request.rel_url.query.get("months", 12))
    months = min(max(months, 3), 36)
    from strategies.capital_projection import project as _cp
    data = _cp(start_capital=start, months=months)
    return web.json_response(data)


async def api_performance(request):
    """Return live trade performance stats from the trade journal."""
    import csv
    from pathlib import Path
    trades_file = Path(__file__).parent / "logs" / "trades.csv"
    trades = []
    if trades_file.exists():
        try:
            with open(trades_file, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    trades.append({
                        "market": row.get("market", "")[:50],
                        "side": row.get("side", ""),
                        "pnl": float(row.get("pnl", 0)),
                        "pnl_pct": float(row.get("pnl_pct", 0)),
                        "reason": row.get("reason", ""),
                        "duration_minutes": int(row.get("duration_minutes", 0)),
                        "source": row.get("source_wallet", "")[:12],
                    })
        except Exception as e:
            pass
    total = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    realized_pnl = round(sum(t["pnl"] for t in trades), 4)
    win_rate = round((wins / total * 100) if total > 0 else 0, 1)
    best = max((t["pnl"] for t in trades), default=0)
    worst = min((t["pnl"] for t in trades), default=0)
    recent = trades[-10:][::-1]   # last 10, newest first
    return web.json_response({
        "total_trades": total,
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
        "best_trade": round(best, 4),
        "worst_trade": round(worst, 4),
        "recent_trades": recent,
    })


async def run_server():
    """Run a lightweight HTTP server for health checks and dashboard."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/dashboard", serve_dashboard)
    app.router.add_get("/", serve_index)
    app.router.add_get("/api/projection", api_projection)
    app.router.add_get("/api/performance", api_performance)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"\U0001f6a8 Health-check server running on port {port}")
    print(f"\U0001f4ca Dashboard available at /dashboard")


async def run_bot():
    """Run the trading bot."""
    bot = PolyBot()

    def shutdown(sig, frame):
        print("\n\u23f9\ufe0f  Shutting down...")
        bot.running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await bot.start()


async def main():
    """Start both the health-check server and the bot concurrently."""
    await run_server()
    await run_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\U0001f6d1 Bot stopped.")
