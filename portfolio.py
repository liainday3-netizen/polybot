"""
POLYBOT — Portfolio Viewer
Display current positions and P&L summary.
"""
from core.position_manager import PositionManager


def main():
    pm = PositionManager()
    summary = pm.get_summary()
    positions = pm.get_open_positions()

    print()
    print("POLYMARKET COPY-BOT PORTFOLIO")
    print("─" * 40)
    print(f"Realized PNL:    {'+' if summary['realized_pnl'] >= 0 else ''}${summary['realized_pnl']:.2f}")
    print(f"Unrealized PNL:  {'+' if summary['unrealized_pnl'] >= 0 else ''}${summary['unrealized_pnl']:.2f}")
    print(f"Total PNL:       {'+' if summary['total_pnl'] >= 0 else ''}${summary['total_pnl']:.2f}")
    print(f"Open positions:  {summary['open_positions']}")
    print(f"Closed trades:   {summary['total_trades']}")
    print(f"Win rate:        {summary['win_rate']}%")
    print()

    if positions:
        print("OPEN POSITIONS")
        print(f"{'Market':<35} {'Spent':<10} {'Entry':<8} {'Current':<8} {'PNL':<10}")
        print("─" * 75)
        for p in positions:
            pnl_str = f"{'+'if p.pnl >= 0 else ''}${p.pnl:.2f}"
            print(f"{p.market[:34]:<35} ${p.size_usdc:<9.2f} {p.entry_price:<8.3f} {p.current_price:<8.3f} {pnl_str:<10}")
    else:
        print("No open positions.")
    print()


if __name__ == "__main__":
    main()
