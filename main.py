"""
POLYBOT — Main Entry Point
Start the copy-trading bot with a health-check HTTP server
for Render free-tier web service compatibility.
"""
import asyncio
import signal
import os
import csv
import time
from pathlib import Path
from typing import Optional
from aiohttp import web

from core.bot import PolyBot
from strategies.capital_projection import project as _project_capital
from core.config import config

FRONTEND_DIR = Path(__file__).parent / "frontend"
LOGS_DIR = Path(__file__).parent / "logs"

# ─── Shared bot reference (set once run_bot() creates it) ────────────────
_bot: Optional[PolyBot] = None
_START_TIME = time.time()


# ─── Helpers ───────────────────────────────────────────────────────────────

def _read_trades():
    """Read all closed trades from CSV log. Returns list of dicts."""
    trades_file = LOGS_DIR / "trades.csv"
    rows = []
    if trades_file.exists():
        try:
            with open(trades_file, newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception:
            pass
    return rows


def _day_key(ts: int) -> str:
    """Convert a unix timestamp to YYYY-MM-DD in local time."""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


# ─── HTTP Handlers ────────────────────────────────────────────────────────────

async def health_check(request):
    """JSON health check — returns bot state for uptime monitors."""
    bot_alive = _bot is not None and getattr(_bot, "running", False)
    return web.json_response({
        "status": "ok",
        "bot_running": bot_alive,
        "uptime_seconds": int(time.time() - _START_TIME),
        "version": "1.3",
        "auto_trade": config.AUTO_TRADE_ENABLED,
    })


async def serve_dashboard(request):
    """Serve the trading dashboard."""
    f = FRONTEND_DIR / "dashboard.html"
    return web.FileResponse(f) if f.exists() else web.Response(text="Dashboard not found", status=404)


async def serve_index(request):
    """Serve the landing page."""
    f = FRONTEND_DIR / "index.html"
    return web.FileResponse(f) if f.exists() else web.Response(text="OK", status=200)


async def api_projection(request):
    """Capital projection JSON."""
    start = float(getattr(config, "TOTAL_USDC", 15.0))
    months = min(max(int(request.rel_url.query.get("months", 12)), 3), 36)
    from strategies.capital_projection import project as _cp
    return web.json_response(_cp(start_capital=start, months=months))


async def api_portfolio(request):
    """
    Live portfolio snapshot.
    Reads from the in-memory bot state (positions + risk manager) so it
    reflects current unrealized P&L without waiting for a trade to close.
    """
    CORS_HEADERS = {"Access-Control-Allow-Origin": "*"}

    # ── closed trade stats from CSV ────────────────────────────────────
    trades = _read_trades()
    total_trades  = len(trades)
    wins          = sum(1 for t in trades if float(t.get("pnl", 0)) > 0)
    realized_pnl  = round(sum(float(t.get("pnl", 0)) for t in trades), 4)
    win_rate      = round((wins / total_trades * 100) if total_trades > 0 else 0, 1)

    # ── daily P&L from risk manager ───────────────────────────────────
    daily_pnl    = round(_bot.risk.daily_pnl, 4) if _bot else 0.0
    daily_limit  = config.DAILY_LOSS_LIMIT
    scale        = round(_bot.risk.current_scale, 2) if _bot else 1.0
    circuit_breaker = bool(_bot and _bot.risk.daily_pnl <= -daily_limit)

    # ── open positions from position manager ──────────────────────────
    open_positions = []
    total_invested  = 0.0
    unrealized_pnl  = 0.0

    if _bot:
        for pos in _bot.positions.get_open_positions():
            cur = pos.current_price if pos.current_price > 0 else pos.entry_price
            open_positions.append({
                "id":          pos.id,
                "market":      pos.market[:50],
                "side":        pos.side,
                "entry_price": round(pos.entry_price, 4),
                "current_price": round(cur, 4),
                "size_usdc":   round(pos.size_usdc, 2),
                "pnl":         round(pos.pnl, 4),
                "pnl_pct":     round(pos.pnl_pct, 2),
                "source":      pos.source_wallet[:14],
                "age_minutes": int((time.time() - pos.timestamp) / 60),
            })
        total_invested = round(_bot.positions.total_invested, 2)
        unrealized_pnl = round(_bot.positions.unrealized_pnl, 4)

    capital_total     = config.TOTAL_USDC
    capital_available = round(max(capital_total - total_invested, 0), 2)
    total_pnl         = round(realized_pnl + unrealized_pnl, 4)
    roi_pct           = round((total_pnl / capital_total * 100) if capital_total > 0 else 0, 2)

    return web.json_response({
        "capital_total":      capital_total,
        "capital_invested":   total_invested,
        "capital_available":  capital_available,
        "unrealized_pnl":     unrealized_pnl,
        "realized_pnl":       realized_pnl,
        "total_pnl":          total_pnl,
        "roi_pct":            roi_pct,
        "daily_pnl":          daily_pnl,
        "daily_limit":        daily_limit,
        "circuit_breaker":    circuit_breaker,
        "scale_factor":       scale,
        "win_rate":           win_rate,
        "total_trades":       total_trades,
        "open_count":         len(open_positions),
        "open_positions":     open_positions,
        "bot_running":        bool(_bot and _bot.running),
    }, headers=CORS_HEADERS)


async def api_pnl_history(request):
    """
    Daily realized P&L for the last N days (default 7).
    Returns [{date, pnl, trades}, ...] oldest-first.
    """
    days = min(max(int(request.rel_url.query.get("days", 7)), 1), 90)
    trades = _read_trades()

    import datetime
    today = datetime.date.today()
    day_map: dict = {}
    for t in trades:
        ts = int(t.get("close_time", t.get("open_time", 0)))
        key = _day_key(ts)
        if key not in day_map:
            day_map[key] = {"pnl": 0.0, "trades": 0}
        day_map[key]["pnl"]    += float(t.get("pnl", 0))
        day_map[key]["trades"] += 1

    result = []
    for i in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=i)).isoformat()
        entry = day_map.get(d, {"pnl": 0.0, "trades": 0})
        result.append({
            "date":   d,
            "pnl":    round(entry["pnl"], 4),
            "trades": entry["trades"],
        })

    return web.json_response(result)


async def api_attribution(request):
    """
    P&L breakdown by source wallet.
    Returns [{source, trades, pnl, win_rate}, ...] sorted by pnl desc.
    """
    trades = _read_trades()
    wallet_map: dict = {}
    for t in trades:
        src = t.get("source_wallet", "unknown")[:20]
        if src not in wallet_map:
            wallet_map[src] = {"trades": 0, "pnl": 0.0, "wins": 0}
        wallet_map[src]["trades"] += 1
        wallet_map[src]["pnl"]    += float(t.get("pnl", 0))
        if float(t.get("pnl", 0)) > 0:
            wallet_map[src]["wins"] += 1

    result = []
    for src, stats in sorted(wallet_map.items(), key=lambda x: -x[1]["pnl"]):
        n = stats["trades"]
        result.append({
            "source":   src,
            "trades":   n,
            "pnl":      round(stats["pnl"], 4),
            "win_rate": round((stats["wins"] / n * 100) if n > 0 else 0, 1),
        })

    return web.json_response(result)


async def api_performance(request):
    """Return live trade performance stats from the trade journal."""
    trades_raw = _read_trades()
    trades = []
    for row in trades_raw:
        try:
            trades.append({
                "market":           row.get("market", "")[:50],
                "side":             row.get("side", ""),
                "pnl":              float(row.get("pnl", 0)),
                "pnl_pct":          float(row.get("pnl_pct", 0)),
                "reason":           row.get("reason", ""),
                "duration_minutes": int(row.get("duration_minutes", 0)),
                "source":           row.get("source_wallet", "")[:12],
            })
        except Exception:
            pass
    total        = len(trades)
    wins         = sum(1 for t in trades if t["pnl"] > 0)
    realized_pnl = round(sum(t["pnl"] for t in trades), 4)
    win_rate     = round((wins / total * 100) if total > 0 else 0, 1)
    best         = max((t["pnl"] for t in trades), default=0)
    worst        = min((t["pnl"] for t in trades), default=0)
    recent       = trades[-10:][::-1]
    return web.json_response({
        "total_trades":  total,
        "win_rate":      win_rate,
        "realized_pnl":  realized_pnl,
        "best_trade":    round(best, 4),
        "worst_trade":   round(worst, 4),
        "recent_trades": recent,
    })



# ─── Bot control API ──────────────────────────────────────────────────────

async def api_start_bot(request):
    """Start / resume the bot loops."""
    global _bot
    if _bot is None:
        return web.json_response({"ok": False, "error": "bot not initialised"}, status=500)
    if _bot.running:
        return web.json_response({"ok": True, "status": "already_running"})
    _bot.running = True
    asyncio.ensure_future(_bot.start())
    return web.json_response({"ok": True, "status": "started"})


async def api_stop_bot(request):
    """Pause the bot loops."""
    global _bot
    if _bot is None:
        return web.json_response({"ok": False, "error": "bot not initialised"}, status=500)
    _bot.running = False
    return web.json_response({"ok": True, "status": "stopped"})


# ─── Server + Bot runners ──────────────────────────────────────────────────

async def run_server():
    """Run lightweight HTTP server."""
    app = web.Application()
    app.router.add_get("/health",          health_check)
    app.router.add_get("/dashboard",       serve_dashboard)
    app.router.add_get("/",                serve_index)
    app.router.add_get("/api/projection",  api_projection)
    app.router.add_get("/api/portfolio",   api_portfolio)
    app.router.add_get("/api/pnl_history", api_pnl_history)
    app.router.add_get("/api/attribution", api_attribution)
    app.router.add_get("/api/performance", api_performance)
    app.router.add_post("/api/start",       api_start_bot)
    app.router.add_post("/api/stop",        api_stop_bot)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"\U0001f6a8 Health-check server running on port {port}")
    print(f"\U0001f4ca Dashboard at /dashboard")


async def run_bot():
    """Create and start the trading bot; expose it to API handlers."""
    global _bot
    _bot = PolyBot()

    def shutdown(sig, frame):
        print("\n\u23f9\ufe0f  Shutting down...")
        _bot.running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    await _bot.start()


async def main():
    """
    Start HTTP server FIRST so Render's port scan succeeds immediately,
    then launch the bot as a background asyncio task.
    Keeps the event loop free for HTTP health-check responses during
    bot initialization - fixes the persistent port-scan-timeout deploys.
    """
    # 1. Bind port immediately -- Render scans within ~60s of deploy start
    await run_server()
    # 2. Yield once so the OS processes the initial accept() call
    await asyncio.sleep(0.1)
    # 3. Run bot as a background task -- HTTP server stays responsive during init
    asyncio.create_task(run_bot())
    # 4. Keep process alive (background tasks run until process exits)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\U0001f6d1 Bot stopped.")
