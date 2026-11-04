import json

res = json.load(open('research/m36_independent_edges_results.json'))
for fam, title in [
    ('FAMILY_1', 'Family 1: Trend Pullback & Continuation'),
    ('FAMILY_2', 'Family 2: Volatility Squeeze & Breakout Expansion'),
    ('FAMILY_3', 'Family 3: Liquidity Sweep & Reclaim Reversal')
]:
    print(f"\n========================================================")
    print(f"{title}")
    print(f"========================================================")
    for sym_tf in ['BTCUSDT_1h', 'ETHUSDT_1h', 'BTCUSDT_4h', 'ETHUSDT_4h']:
        k = f"{fam}_{sym_tf}_FULL_SERIES"
        if k in res:
            m = res[k]['strict_mixed_metrics']
            print(f"  {sym_tf:12s} Full Series: Trades={m['total_trades']:3d} | WR={m['win_rate_pct']:4.1f}% | NetR={m['mean_net_r']:+6.3f}R | PF={m['profit_factor']:4.2f} | MaxDD={m['max_drawdown_r']:5.2f}R")
        # Also print OOS 2025 and Forward 2026
        k_oos = f"{fam}_{sym_tf}_SEALED_OOS_2025"
        k_fwd = f"{fam}_{sym_tf}_FORWARD_2026"
        if k_oos in res and k_fwd in res:
            m_oos = res[k_oos]['strict_mixed_metrics']
            m_fwd = res[k_fwd]['strict_mixed_metrics']
            print(f"    --> 2025 OOS: N={m_oos['total_trades']:2d}, NetR={m_oos['mean_net_r']:+5.2f}R, PF={m_oos['profit_factor']:4.2f} | 2026 Replay: N={m_fwd['total_trades']:2d}, NetR={m_fwd['mean_net_r']:+5.2f}R, PF={m_fwd['profit_factor']:4.2f}")
