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


async def health_check(request):
    """Simple health-check endpoint for Render."""
    return web.Response(text="OK", status=200)


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


async def run_server():
    """Run a lightweight HTTP server for health checks and dashboard."""
    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/dashboard", serve_dashboard)
    app.router.add_get("/", serve_index)
    app.router.add_get("/api/projection", api_projection)
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
