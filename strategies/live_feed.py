"""
POLYBOT — Live WebSocket Feed
Real-time trade monitoring via WebSocket.
"""
import asyncio
import json
from typing import Callable, Optional

import websockets


WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RECONNECT_DELAY_S = 5


class LiveFeed:
    """WebSocket connection for real-time Polymarket trade feeds."""

    def __init__(self, on_trade: Optional[Callable] = None):
        self.on_trade = on_trade
        self.ws = None
        self.running = False

    async def connect(self, market_ids: list = None):
        """Connect to Polymarket WebSocket with automatic reconnection."""
        self.running = True

        # FIX: outer reconnection loop — break inside only retries, doesn't exit
        while self.running:
            try:
                async with websockets.connect(WS_URL) as ws:
                    self.ws = ws

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

                            if data.get("type") == "trade" and self.on_trade:
                                # FIX: isolate callback — an error in on_trade won't kill the feed
                                try:
                                    if asyncio.iscoroutinefunction(self.on_trade):
                                        await self.on_trade(data)
                                    else:
                                        self.on_trade(data)
                                except Exception as cb_exc:
                                    print(f"⚠️  on_trade callback error (feed kept alive): {cb_exc}")

                        except asyncio.TimeoutError:
                            await ws.ping()
                        except websockets.ConnectionClosed:
                            print("⚠️  WebSocket disconnected. Reconnecting in 5s...")
                            break   # break inner loop → outer loop retries

            except Exception as e:
                print(f"❌ WebSocket error: {e}. Retrying in {RECONNECT_DELAY_S}s...")

            if self.running:
                await asyncio.sleep(RECONNECT_DELAY_S)

    async def disconnect(self):
        """Disconnect WebSocket."""
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass


async def main():
    """Demo: print live trades."""
    async def print_trade(data):
        print(f"[TRADE] {data}")

    feed = LiveFeed(on_trade=print_trade)
    # FIX: use create_task so the feed runs in background alongside other bot logic
    asyncio.create_task(feed.connect())
    await asyncio.sleep(60)   # demo: run for 60 seconds


if __name__ == "__main__":
    asyncio.run(main())
