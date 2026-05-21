# PolyBot 🤖

**Polymarket copy-trading on autopilot.** Mirror the smartest prediction market traders with $15 starting capital.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

---

## What is PolyBot?

PolyBot monitors top-performing wallets on [Polymarket](https://polymarket.com) and automatically copies their trades in real-time. It's designed for small capital ($15-$100) with aggressive risk management.

**Key Features:**
- 🎯 **Auto Copy-Trading** — Mirror trades from top wallets the instant they execute
- 🛡️ **MEV Protection** — Orders routed through protected channels (no front-running)
- 📊 **Risk Management** — Stop-loss, take-profit, daily circuit breaker, auto-scaling
- 🔍 **Wallet Discovery** — Built-in leaderboard scanner to find profitable traders
- 📄 **Paper Trading** — Test with virtual capital before risking real money
- ⚡ **Live Dashboard** — Real-time P&L, positions, and signal feed
- 🌐 **24/7 Deployment** — Free hosting on Render (always-on worker)

---

## Quick Start

### Prerequisites

- Python 3.9+
- [Phantom Wallet](https://phantom.app) (or any EVM wallet)
- $15 USDC + $10 POL on Polygon network
- 5 minutes

### Installation

```bash
# Extract and enter project
tar -xzf polymarket_bot.tar.gz
cd polymarket_bot

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Add your private key + wallet address
```

### Setup (One-Time)

```bash
# Generate API credentials from your private key
python setup_credentials.py

# Approve token spending (4 transactions, ~$0.01 gas)
python set_allowances.py
```

### Find Wallets to Copy

```bash
# Scan the leaderboard for top traders
python -m strategies.leaderboard_scanner

# Backtest a specific wallet before copying
python -m strategies.backtest --wallet 0xABC... --days 90 --capital 15
```

### Run the Bot

```bash
# Start live copy-trading
python main.py

# Or view your portfolio
python portfolio.py
```

### Web Dashboard

```bash
# Serve the frontend locally
python -m http.server 8000 --directory frontend

# Open in browser:
# Simple UI:    http://localhost:8000/index.html
# Pro Dashboard: http://localhost:8000/dashboard.html
```

---

## Configuration

All settings are in `.env`. Key parameters:

| Variable | Default | Description |
|----------|---------|-------------|
| `POLYMARKET_PK` | — | Your wallet private key |
| `POLYMARKET_FUNDER` | — | Your wallet address |
| `TARGET_WALLETS` | — | Comma-separated addresses to copy |
| `TOTAL_USDC` | 15 | Trading capital in USDC |
| `MAX_PCT_PER_TRADE` | 15 | Max % of capital per trade |
| `STOP_LOSS_PCT` | 40 | Close position at -40% |
| `TAKE_PROFIT_PCT` | 80 | Close position at +80% |
| `DAILY_LOSS_LIMIT` | 8 | Circuit breaker (pause if daily loss > $8) |
| `COPY_SCALE_FACTOR` | 10 | Copy 10% of target's position size |
| `MONITOR_INTERVAL` | 15 | Check for new trades every 15 seconds |
| `MEV_PROTECTION` | true | Route orders through MEV protection |

---

## Architecture

```
polymarket_bot/
├── main.py                    # Entry point
├── core/
│   ├── bot.py                 # Main orchestrator
│   ├── config.py              # Settings from .env
│   ├── polymarket_client.py   # CLOB API + order signing
│   ├── risk_manager.py        # SL/TP/circuit breaker
│   └── position_manager.py    # Position tracking (JSON)
├── strategies/
│   ├── leaderboard_scanner.py # Discover top wallets
│   ├── backtest.py            # Historical simulation
│   └── live_feed.py           # WebSocket real-time feed
├── utils/
│   ├── logger.py              # Colored console + file logging
│   └── trade_journal.py       # CSV trade journal
├── frontend/
│   ├── index.html             # Simple trading UI
│   ├── dashboard.html         # Advanced Pro dashboard
│   └── landing.html           # Marketing page
├── setup_credentials.py       # API key generation
├── set_allowances.py          # Token approvals
├── portfolio.py               # View positions
├── requirements.txt
├── .env.example
├── render.yaml                # Render deployment
├── Dockerfile                 # Container deployment
└── Procfile                   # Heroku/Railway
```

---

## Deployment (24/7)

### Render (Recommended — Free)

1. Push this project to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your repo (auto-reads `render.yaml`)
4. Add environment variables in the Render dashboard
5. Deploy — bot runs 24/7 on the free worker tier

### Docker

```bash
docker build -t polybot .
docker run -d --env-file .env --name polybot polybot
```

### Railway / Heroku

```bash
# Uses Procfile automatically
railway up
# or
heroku create && git push heroku main
```

---

## Risk Management

PolyBot includes multiple safety layers:

| Layer | Trigger | Action |
|-------|---------|--------|
| Stop-Loss | Position down 40% | Auto-close |
| Take-Profit | Position up 80% | Auto-close |
| Position Cap | Single trade > 15% of capital | Reduce size |
| Daily Circuit Breaker | Daily loss > $8 | Pause all trading |
| Max Positions | 5 open positions | Skip new signals |
| MEV Shield | Every trade | Route through protected relay |

---

## How Copy-Trading Works

1. **Monitor** — Bot polls target wallets every 15s for new trades
2. **Detect** — New trade found → validate against risk rules
3. **Scale** — Calculate position size (10% of target's size, capped at $2.25)
4. **Execute** — Place limit order on Polymarket CLOB via signed API
5. **Track** — Monitor position, apply SL/TP rules automatically
6. **Journal** — Log everything to CSV for analysis

---

## Paper Trading

Test risk-free before going live:

1. Open `frontend/dashboard.html`
2. Click "Paper" mode toggle
3. Adjust virtual capital with the slider ($10-$1000)
4. Click "Simulate" on any signal to place paper trades
5. Watch simulated P&L accumulate

Paper mode uses the same logic as live trading but skips on-chain execution.

---

## Security Notes

⚠️ **Important:**
- Your private key is stored locally in `.env` — never commit this file
- `.env` is in `.gitignore` by default
- API credentials are derived from your key (not stored on any server)
- Bot only has access to USDC and CTF tokens you explicitly approve
- All trading happens on-chain (verifiable on Polygonscan)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "No wallet detected" | Install Phantom or MetaMask browser extension |
| "Insufficient POL" | Send $10 worth of POL to your wallet for gas |
| "API credentials failed" | Re-run `python setup_credentials.py` |
| "Order rejected" | Check USDC balance, ensure allowances are set |
| "No trades detected" | Verify `TARGET_WALLETS` addresses are active traders |

---

## License

MIT — do whatever you want with it.

---

## Disclaimer

This software is for educational purposes. Trading prediction markets involves risk. Never invest more than you can afford to lose. Past performance of copied wallets does not guarantee future results.

---

Built with 🤖 for the Polymarket community.
