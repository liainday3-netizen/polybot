"""
POLYBOT — Live WebSocket Feed
Real-time trade monitoring via WebSocket.
"""
import asyncio
import json
from typing import Callable, Optional

import websockets


WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class LiveFeed:
    """WebSocket connection for real-time Polymarket trade feeds."""

    def __init__(self, on_trade: Optional[Callable] = None):
        self.on_trade = on_trade
        self.ws = None
        self.running = False

    async def connect(self, market_ids: list = None):
        """Connect to Polymarket WebSocket."""
        self.running = True

        try:
            async with websockets.connect(WS_URL) as ws:
                self.ws = ws

                # Subscribe to trade events
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": "trades",
                    "markets": market_ids or []
                }
                await ws.send(json.dumps(subscribe_msg))

                print("📡 WebSocket connected — listening for trades...")

                while self.running:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)

                        if data.get("type") == "trade":
                            if self.on_trade:
                                await self.on_trade(data)

                    except asyncio.TimeoutError:
                        # Send ping to keep alive
                        await ws.ping()
                    except websockets.ConnectionClosed:
                        print("⚠️  WebSocket disconnected. Reconnecting...")
                        break

        except Exception as e:
            print(f"❌ WebSocket error: {e}")

    async def disconnect(self):
        """Disconnect WebSocket."""
        self.running = False
        if self.ws:
            await self.ws.close()


async def main():
    """Demo: print live trades."""
    async def print_trade(data):
        print(f"[TRADE] {data}")

    feed = LiveFeed(on_trade=print_trade)
    await feed.connect()


if __name__ == "__main__":
    asyncio.run(main())
