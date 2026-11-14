import json

data = json.load(open("research/m36_1_portfolio_results.json"))
print("=== Correlation Analysis ===")
print("Daily Pearson:")
for k, v in data["correlation_analysis"]["daily_pearson"].items():
    print(f"  {k:15s}: {v}")

print("\nMonthly Pearson:")
for k, v in data["correlation_analysis"]["monthly_pearson"].items():
    print(f"  {k:15s}: {v}")

print("\nDownside Correlation (when Benchmark < 0):")
print(json.dumps(data["correlation_analysis"]["downside_correlation"], indent=2))

print("\n=== Portfolio Combinations ===")
for p_name, metrics in data["portfolio_combinations"].items():
    print(
        f"{p_name:35s} | Ret={metrics['cumulative_return_r']:+7.2f}R | MaxDD={metrics['max_drawdown_r']:6.2f}R | Ulcer={metrics['ulcer_index']:5.2f} | Sharpe={metrics['sharpe_annualized_daily']:+5.2f} | CVaR95={metrics['cvar_95_daily_r']:+6.3f}R"
    )

print("\n=== Family 3 Verdict ===")
print(json.dumps(data["family3_classification"], indent=2))
