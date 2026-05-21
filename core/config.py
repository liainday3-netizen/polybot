"""
POLYBOT — Core Configuration Module
Loads and validates all settings from .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)


class Config:
    """Central configuration for PolyBot."""

    # Wallet
    PRIVATE_KEY: str = os.getenv('POLYMARKET_PK', '')
    WALLET_ADDRESS: str = os.getenv('POLYMARKET_FUNDER', '')

    # API Credentials
    API_KEY: str = os.getenv('POLYMARKET_API_KEY', '')
    API_SECRET: str = os.getenv('POLYMARKET_API_SECRET', '')
    API_PASSPHRASE: str = os.getenv('POLYMARKET_API_PASSPHRASE', '')

    # Target Wallets
    TARGET_WALLETS: list = [
        w.strip() for w in os.getenv('TARGET_WALLETS', '').split(',')
        if w.strip()
    ]

    # Capital
    TOTAL_USDC: float = float(os.getenv('TOTAL_USDC', '15.0'))
    POL_RESERVE: float = float(os.getenv('POL_RESERVE', '10.0'))

    # Risk
    MAX_PER_TRADE_PCT: float = float(os.getenv('MAX_PER_TRADE_PCT', '15'))
    MAX_OPEN_POSITIONS: int = int(os.getenv('MAX_OPEN_POSITIONS', '5'))
    STOP_LOSS_PCT: float = float(os.getenv('STOP_LOSS_PCT', '40'))
    TAKE_PROFIT_PCT: float = float(os.getenv('TAKE_PROFIT_PCT', '80'))
    DAILY_LOSS_LIMIT: float = float(os.getenv('DAILY_LOSS_LIMIT', '8.0'))
    MIN_SIGNAL_SIZE: float = float(os.getenv('MIN_SIGNAL_SIZE', '5.0'))

    # Copy Settings
    COPY_SCALE_FACTOR: float = float(os.getenv('COPY_SCALE_FACTOR', '10'))
    COPY_DELAY_SECONDS: int = int(os.getenv('COPY_DELAY_SECONDS', '3'))
    MONITOR_INTERVAL: int = int(os.getenv('MONITOR_INTERVAL', '30'))
    POSITION_CHECK_INTERVAL: int = int(os.getenv('POSITION_CHECK_INTERVAL', '15'))

    # Auto-Scaling
    AUTO_SCALE_UP_PCT: float = float(os.getenv('AUTO_SCALE_UP_PCT', '15'))
    AUTO_SCALE_WINS_REQUIRED: int = int(os.getenv('AUTO_SCALE_WINS_REQUIRED', '2'))

    # MEV Protection
    MEV_PROTECTION: bool = os.getenv('MEV_PROTECTION', 'true').lower() == 'true'
    PRIVATE_RPC: str = os.getenv('PRIVATE_RPC', 'https://rpc-mainnet.private.polygon.technology')
    PUBLIC_RPC: str = os.getenv('PUBLIC_RPC', 'https://polygon-rpc.com')

    # Network
    CHAIN_ID: int = int(os.getenv('CHAIN_ID', '137'))
    CLOB_API_URL: str = os.getenv('CLOB_API_URL', 'https://clob.polymarket.com')
    USDC_ADDRESS: str = os.getenv('USDC_ADDRESS', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174')
    CTF_ADDRESS: str = os.getenv('CTF_ADDRESS', '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045')
    EXCHANGE_ADDRESS: str = os.getenv('EXCHANGE_ADDRESS', '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E')
    NEG_RISK_ADAPTER: str = os.getenv('NEG_RISK_ADAPTER', '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296')

    @property
    def rpc_url(self) -> str:
        """Return the appropriate RPC based on MEV protection setting."""
        return self.PRIVATE_RPC if self.MEV_PROTECTION else self.PUBLIC_RPC

    @property
    def max_per_trade(self) -> float:
        """Maximum USDC per trade based on percentage of capital."""
        return self.TOTAL_USDC * (self.MAX_PER_TRADE_PCT / 100)

    def validate(self) -> list:
        """Validate configuration. Returns list of errors."""
        errors = []
        if not self.PRIVATE_KEY or self.PRIVATE_KEY == '0xYOUR_PRIVATE_KEY_HERE':
            errors.append("POLYMARKET_PK not set in .env")
        if not self.WALLET_ADDRESS or self.WALLET_ADDRESS == '0xYOUR_WALLET_ADDRESS_HERE':
            errors.append("POLYMARKET_FUNDER not set in .env")
        if not self.TARGET_WALLETS:
            errors.append("TARGET_WALLETS not set in .env")
        if self.TOTAL_USDC < 1:
            errors.append("TOTAL_USDC must be at least $1")
        return errors


config = Config()
