"""
POLYBOT — Main Entry Point
Start the copy-trading bot.
"""
import asyncio
import signal
import sys

from core.bot import PolyBot


def main():
    """Start PolyBot."""
    bot = PolyBot()

    # Handle Ctrl+C gracefully
    def shutdown(sig, frame):
        print("\n⏹️  Shutting down...")
        bot.running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run the bot
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")


if __name__ == "__main__":
    main()
