"""
POLYBOT — Main Entry Point
Start the copy-trading bot with a health-check HTTP server
for Render free-tier web service compatibility.
"""
import asyncio
import signal
import os
from aiohttp import web

from core.bot import PolyBot


async def health_check(request):
    """Simple health-check endpoint for Render."""
    return web.Response(text="OK", status=200)


async def run_server():
    """Run a lightweight HTTP server for health checks."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"\U0001f6a8 Health-check server running on port {port}")


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
