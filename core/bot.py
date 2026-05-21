"""
POLYBOT — Main Trading Bot Orchestrator
Monitors target wallets, detects signals, and executes copy-trades.
"""
import asyncio
import time
import signal
import sys
from typing import Dict, List

from core.config import config
from core.polymarket_client import PolymarketClient
from core.risk_manager import RiskManager
from core.position_manager import PositionManager
from utils.logger import BotLogger


class PolyBot:
    """Main copy-trading bot that monitors wallets and mirrors trades."""

    def __init__(self):
        self.client = PolymarketClient()
        self.risk = RiskManager()
        self.positions = PositionManager()
        self.logger = BotLogger()
        self.running = False
        self.last_seen: Dict[str, int] = {}  # wallet -> last trade timestamp

    async def start(self):
        """Initialize and start the bot."""
        # Validate configuration
        errors = config.validate()
        if errors:
            for e in errors:
                print(f"❌ Config error: {e}")
            print("\n⚠️  Fix .env file and try again. See .env.example for reference.")
            return

        # Connect to API
        await self.client.connect()
        self.running = True

        # Print startup banner
        self._print_banner()

        # Initialize last seen timestamps
        for wallet in config.TARGET_WALLETS:
            self.last_seen[wallet] = int(time.time())

        self.logger.info("Bot started successfully")
        self.logger.info(f"Monitoring {len(config.TARGET_WALLETS)} target wallet(s)")
        self.logger.info(f"Capital: ${config.TOTAL_USDC} USDC | Max/trade: ${config.max_per_trade:.2f}")
        self.logger.info(f"MEV Protection: {'ON' if config.MEV_PROTECTION else 'OFF'}")

        # Start main loops
        try:
            await asyncio.gather(
                self._copy_trade_loop(),
                self._position_monitor_loop()
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self):
        """Gracefully stop the bot."""
        self.running = False
        await self.client.disconnect()
        self.logger.info("Bot stopped")
        print("\n🛑 Bot stopped gracefully.")

    def _print_banner(self):
        """Print startup banner."""
        print("═" * 50)
        print("  POLYMARKET COPY-TRADE BOT  v1.0")
        print(f"  Capital: ${config.TOTAL_USDC} USDC | Gas reserve: ${config.POL_RESERVE} POL")
        print("═" * 50)
        print()
        print(f"Bot started | Capital: ${config.TOTAL_USDC} USDC | Targets: {len(config.TARGET_WALLETS)} wallets")
        print("Connected to Polymarket CLOB API ✓")
        print("Copy-trade loop started")
        print("Position monitor started")
        print()

    async def _copy_trade_loop(self):
        """Main loop: monitor target wallets and copy new trades."""
        while self.running:
            try:
                for wallet in config.TARGET_WALLETS:
                    await self._check_wallet(wallet)
                    await asyncio.sleep(1)  # Small delay between wallet checks

                await asyncio.sleep(config.MONITOR_INTERVAL)

            except Exception as e:
                self.logger.error(f"Copy-trade loop error: {e}")
                await asyncio.sleep(10)  # Wait before retrying

    async def _check_wallet(self, wallet: str):
        """Check a target wallet for new trades."""
        try:
            trades = await self.client.get_wallet_activity(
                wallet, 
                since_timestamp=self.last_seen.get(wallet, 0)
            )

            for trade in trades:
                await self._process_signal(wallet, trade)

            # Update last seen
            if trades:
                latest_ts = max(int(t.get("timestamp", 0)) for t in trades)
                self.last_seen[wallet] = max(self.last_seen.get(wallet, 0), latest_ts)

        except Exception as e:
            self.logger.error(f"Error checking wallet {wallet[:10]}...: {e}")

    async def _process_signal(self, source_wallet: str, trade: Dict):
        """Process a detected trade signal and execute copy-trade."""
        market = trade.get("market", "Unknown")
        token_id = trade.get("asset_id", trade.get("token_id", ""))
        side = trade.get("side", "BUY").upper()
        target_size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))

        # Check minimum signal size
        if target_size < config.MIN_SIGNAL_SIZE:
            return

        self.logger.signal(source_wallet, market, price)

        # Calculate our position size
        our_size = self.risk.calculate_position_size(target_size)

        # Validate trade against risk parameters
        is_valid, reason = self.risk.validate_trade(
            size_usdc=our_size,
            price=price,
            open_positions=self.positions.open_count
        )

        if not is_valid:
            self.logger.warning(f"Trade rejected: {reason}")
            return

        # Delay before execution (configurable)
        await asyncio.sleep(config.COPY_DELAY_SECONDS)

        # Execute the copy trade
        self.logger.info(f"🚀 Placing order | ${our_size:.2f} @ {price}")

        result = await self.client.place_order(
            token_id=token_id,
            side=side,
            price=price,
            size=our_size
        )

        if result:
            order_id = result.get("id", result.get("orderID", ""))
            self.logger.trade_executed(our_size, price, order_id)

            # Record position
            self.positions.open_position(
                market=market,
                token_id=token_id,
                side=side,
                entry_price=price,
                size_usdc=our_size,
                source_wallet=source_wallet,
                order_id=order_id
            )
        else:
            self.logger.error(f"Order failed for {market}")

    async def _position_monitor_loop(self):
        """Monitor open positions for stop-loss and take-profit exits."""
        while self.running:
            try:
                open_positions = self.positions.get_open_positions()

                for pos in open_positions:
                    current_price = await self.client.get_price(pos.token_id)
                    if current_price is None:
                        continue

                    pos.update_pnl(current_price)

                    # Check stop-loss
                    if self.risk.check_stop_loss(pos.entry_price, current_price, pos.side):
                        self.logger.warning(
                            f"⛔ Stop-loss triggered: {pos.market} "
                            f"(entry: {pos.entry_price:.3f}, current: {current_price:.3f})"
                        )
                        trade = self.positions.close_position(pos.id, current_price, "stopped")
                        if trade:
                            self.risk.record_trade_result(trade["pnl"])

                    # Check take-profit
                    elif self.risk.check_take_profit(pos.entry_price, current_price, pos.side):
                        self.logger.info(
                            f"💰 Take-profit hit: {pos.market} "
                            f"(entry: {pos.entry_price:.3f}, current: {current_price:.3f})"
                        )
                        trade = self.positions.close_position(pos.id, current_price, "profit_taken")
                        if trade:
                            self.risk.record_trade_result(trade["pnl"])

                    # Log position status
                    else:
                        self.logger.position_update(pos)

                await asyncio.sleep(config.POSITION_CHECK_INTERVAL)

            except Exception as e:
                self.logger.error(f"Position monitor error: {e}")
                await asyncio.sleep(10)
