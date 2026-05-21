"""
POLYBOT — Polymarket CLOB API Client
Handles all interactions with Polymarket's order book.
"""
import time
import json
import hmac
import hashlib
import base64
import asyncio
from typing import Optional, Dict, List, Any

import aiohttp
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from core.config import config


class PolymarketClient:
    """Async client for Polymarket CLOB API."""

    def __init__(self):
        self.base_url = config.CLOB_API_URL
        self.api_key = config.API_KEY
        self.api_secret = config.API_SECRET
        self.api_passphrase = config.API_PASSPHRASE
        self.session: Optional[aiohttp.ClientSession] = None
        self.w3 = Web3(Web3.HTTPProvider(config.rpc_url))
        self.account = Account.from_key(config.PRIVATE_KEY) if config.PRIVATE_KEY and config.PRIVATE_KEY != '0xYOUR_PRIVATE_KEY_HERE' else None

    async def connect(self):
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession(
            headers=self._auth_headers()
        )

    async def disconnect(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    def _auth_headers(self) -> Dict[str, str]:
        """Generate authentication headers for CLOB API."""
        timestamp = str(int(time.time()))
        message = timestamp + "GET" + "/auth/api-key"

        if self.api_secret:
            signature = hmac.new(
                base64.b64decode(self.api_secret),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            sig_b64 = base64.b64encode(signature).decode('utf-8')
        else:
            sig_b64 = ""

        return {
            "POLY_API_KEY": self.api_key,
            "POLY_SIGNATURE": sig_b64,
            "POLY_TIMESTAMP": timestamp,
            "POLY_PASSPHRASE": self.api_passphrase,
            "Content-Type": "application/json"
        }

    async def get_markets(self, limit: int = 50, active_only: bool = True) -> List[Dict]:
        """Fetch available markets from Polymarket."""
        params = {"limit": limit}
        if active_only:
            params["active"] = "true"

        async with self.session.get(f"{self.base_url}/markets", params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

    async def get_market(self, condition_id: str) -> Optional[Dict]:
        """Fetch a specific market by condition ID."""
        async with self.session.get(f"{self.base_url}/markets/{condition_id}") as resp:
            if resp.status == 200:
                return await resp.json()
            return None

    async def get_order_book(self, token_id: str) -> Dict:
        """Fetch order book for a specific token."""
        params = {"token_id": token_id}
        async with self.session.get(f"{self.base_url}/book", params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return {"bids": [], "asks": []}

    async def get_price(self, token_id: str) -> Optional[float]:
        """Get current mid-price for a token."""
        book = await self.get_order_book(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])

        if bids and asks:
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            return (best_bid + best_ask) / 2
        elif bids:
            return float(bids[0]["price"])
        elif asks:
            return float(asks[0]["price"])
        return None

    def sign_order(self, order_data: Dict) -> str:
        """Sign an order with EIP-712 typed data."""
        if not self.account:
            raise ValueError("No wallet configured")

        # Create EIP-712 order hash
        order_message = json.dumps(order_data, sort_keys=True)
        message = encode_defunct(text=order_message)
        signed = self.account.sign_message(message)
        return signed.signature.hex()

    async def place_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        price: float,
        size: float,
        order_type: str = "FOK"  # Fill-or-Kill
    ) -> Optional[Dict]:
        """Place an order on Polymarket CLOB."""
        order_data = {
            "tokenID": token_id,
            "side": side,
            "price": str(price),
            "size": str(size),
            "type": order_type,
            "funder": config.WALLET_ADDRESS,
            "nonce": str(int(time.time() * 1000)),
            "expiration": str(int(time.time()) + 3600),  # 1 hour expiry
        }

        # Sign the order
        signature = self.sign_order(order_data)
        order_data["signature"] = signature

        async with self.session.post(
            f"{self.base_url}/order",
            json=order_data
        ) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return result
            else:
                error = await resp.text()
                print(f"❌ Order failed: {resp.status} — {error}")
                return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        async with self.session.delete(
            f"{self.base_url}/order/{order_id}"
        ) as resp:
            return resp.status == 200

    async def get_trades(self, wallet: str, limit: int = 50) -> List[Dict]:
        """Fetch recent trades for a wallet address."""
        params = {
            "maker_address": wallet,
            "limit": limit
        }
        async with self.session.get(
            f"{self.base_url}/trades",
            params=params
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

    async def get_positions(self, wallet: Optional[str] = None) -> List[Dict]:
        """Fetch open positions for a wallet."""
        address = wallet or config.WALLET_ADDRESS
        async with self.session.get(
            f"{self.base_url}/positions",
            params={"user": address}
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

    async def get_wallet_activity(self, wallet: str, since_timestamp: int = 0) -> List[Dict]:
        """Monitor a target wallet for new activity."""
        params = {
            "maker_address": wallet,
            "limit": 10
        }
        if since_timestamp:
            params["after"] = str(since_timestamp)

        async with self.session.get(
            f"{self.base_url}/trades",
            params=params
        ) as resp:
            if resp.status == 200:
                trades = await resp.json()
                # Filter to only trades after our timestamp
                if since_timestamp:
                    trades = [
                        t for t in trades
                        if int(t.get("timestamp", 0)) > since_timestamp
                    ]
                return trades
            return []
