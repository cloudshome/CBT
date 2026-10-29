"""
tests/test_lean_github_researcher.py
====================================
Tests the Lean & Zero-Junk GitHub Researcher:
1. File size limits (< 256 KB)
2. Quality filter (rejects spam, martingale, unhedged code)
3. Test-Before-Store gate (positive expectancy promoted, negative expectancy rejected)
4. Storage quota discipline (25 MB max)
"""

from pathlib import Path

import pytest

from core.github_researcher import GitHubResearcher


@pytest.fixture
def temp_researcher(tmp_path: Path):
    sandbox = tmp_path / "sandbox"
    researcher = GitHubResearcher(sandbox_dir=sandbox)
    return researcher


def test_rejects_heavy_files(temp_researcher: GitHubResearcher):
    # Create oversized code (> 256 KB)
    heavy_code = "stop_loss = 0.01\n# Comment line padding\n" + ("# filler line\n" * 25000)  # > 300 KB
    passed, reason = temp_researcher.filter_quality_hurdle(heavy_code)
    assert not passed
    assert "File size exceeds lean ceiling" in reason


def test_rejects_spam_and_promotional_hype(temp_researcher: GitHubResearcher):
    spam_code = """
    # 100% WIN RATE GUARANTEED PROFIT
    # Join our VIP signals at t.me/pumppump
    stop_loss = 0.02
    def buy_signal():
        return True
    """
    passed, reason = temp_researcher.filter_quality_hurdle(spam_code)
    assert not passed
    assert "promotional/spam" in reason


def test_rejects_unhedged_code_without_stop_loss(temp_researcher: GitHubResearcher):
    unhedged_code = """
    def execute_trade(price):
        if price > 100:
            return "BUY"
        return "HOLD"
    """
    passed, reason = temp_researcher.filter_quality_hurdle(unhedged_code)
    assert not passed
    assert "Unhedged strategy" in reason


def test_promotes_disciplined_strategy(temp_researcher: GitHubResearcher):
    valid_code = """
    # Institutional Mean Reversion with Dynamic ATR Invalidation
    stop_loss = 0.015
    atr_mult = 2.0
    take_profit_ratio = 2.5

    def check_entry_signal(close, sma):
        if close > sma:
            return "BUY"
        return "HOLD"

    def check_exit_risk(price, entry, stop_loss):
        if price <= entry * (1 - stop_loss):
            return "EXIT_STOP"
        return "HOLD"
    """
    res = temp_researcher.ingest_lean_strategy(
        name="ATR_Mean_Reversion",
        code_str=valid_code,
        source_url="https://github.com/quant/valid-repo/strategy.py",
        repo_meta={"stars": 120},
        simulated_edge=0.35,  # Positive edge
    )
    assert res["verdict"] == "PROMOTED_CANDIDATE"
    assert res["passed"] is True
    assert "candidate_id" in res


def test_rejects_strategy_with_negative_expectancy(temp_researcher: GitHubResearcher):
    valid_syntax_bad_edge = """
    stop_loss = 0.05
    def check_entry(p): return "BUY"
    def check_exit(p): return "SELL"
    """
    res = temp_researcher.ingest_lean_strategy(
        name="Losing_Strategy",
        code_str=valid_syntax_bad_edge,
        source_url="https://github.com/quant/losing-repo/strategy.py",
        repo_meta={"stars": 50},
        simulated_edge=-0.20,  # Negative edge
    )
    assert res["verdict"] == "REJECTED"
    assert res["passed"] is False
    assert "Insufficient expectancy" in res["reason"]
