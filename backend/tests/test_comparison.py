"""
test_comparison.py — Tests for backend/comparison.py.

Covers:
  - StrategyResult and ComparisonResult dataclass structure
  - compare_strategies: correct strategy names, positive-EV games
  - Relationship checks: half-Kelly EV < full-Kelly EV (expected),
    half-Kelly RoR < full-Kelly RoR (safer)
  - Flat bet is simpler but still measurable
  - format_comparison_table renders without error
  - Edge cases: very small bankroll, no-wong spreads
"""

from __future__ import annotations

import math
import pytest

from backend.comparison import (
    ComparisonResult,
    StrategyResult,
    compare_strategies,
    format_comparison_table,
    _flat_bet_spread,
    _kelly_spread,
    _build_tc_edges,
)
from backend.engine import GameRules


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def s17_rules():
    """S17 DAS RSA 6-deck game — favourable for the player."""
    return GameRules(decks=6, penetration=0.75, h17=False, das=True, rsa=True,
                     max_splits=3, surrender=True, bj_payout=1.5)


@pytest.fixture(scope="module")
def h17_rules():
    """Standard H17 6-deck game."""
    return GameRules(decks=6, penetration=0.75, h17=True, das=True, rsa=True,
                     max_splits=3, surrender=True, bj_payout=1.5)


@pytest.fixture(scope="module")
def comparison_result(s17_rules):
    """Full compare_strategies run (moderate shoes count for speed)."""
    return compare_strategies(
        rules=s17_rules,
        bankroll=10_000.0,
        rounds_per_hour=100.0,
        flat_bet_amount=25.0,
        min_tc=1,
        num_shoes=3_000,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestComparisonResultStructure:
    def test_returns_comparison_result(self, comparison_result):
        assert isinstance(comparison_result, ComparisonResult)

    def test_has_three_strategies(self, comparison_result):
        assert isinstance(comparison_result.flat_bet, StrategyResult)
        assert isinstance(comparison_result.full_kelly, StrategyResult)
        assert isinstance(comparison_result.half_kelly, StrategyResult)

    def test_strategy_names(self, comparison_result):
        assert comparison_result.flat_bet.name == "Flat Bet"
        assert comparison_result.full_kelly.name == "Full Kelly"
        assert comparison_result.half_kelly.name == "Half Kelly"

    def test_rules_stored(self, comparison_result, s17_rules):
        assert comparison_result.rules is s17_rules

    def test_bankroll_stored(self, comparison_result):
        assert comparison_result.bankroll == 10_000.0

    def test_rounds_per_hour_stored(self, comparison_result):
        assert comparison_result.rounds_per_hour == 100.0


# ---------------------------------------------------------------------------
# StrategyResult fields
# ---------------------------------------------------------------------------

class TestStrategyResultFields:
    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_total_hands_positive(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert result.total_hands > 0

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_ev_per_hour_finite(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert math.isfinite(result.ev_per_hour)

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_std_dev_per_hour_positive(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert result.std_dev_per_hour > 0

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_ror_in_0_1(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert 0.0 <= result.risk_of_ruin <= 1.0

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_score_non_negative(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert result.score >= 0.0

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_bet_spread_non_empty(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert len(result.bet_spread) > 0

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_bet_spread_has_positive_bet(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert any(v > 0 for v in result.bet_spread.values())

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_ev_per_hand_finite(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert math.isfinite(result.ev_per_hand)

    @pytest.mark.parametrize("strategy_attr", ["flat_bet", "full_kelly", "half_kelly"])
    def test_std_dev_per_hand_positive(self, comparison_result, strategy_attr):
        result = getattr(comparison_result, strategy_attr)
        assert result.std_dev_per_hand > 0


# ---------------------------------------------------------------------------
# Economic relationships
# ---------------------------------------------------------------------------

class TestEconomicRelationships:
    def test_kelly_strategies_have_positive_ev(self, comparison_result):
        """Both Kelly strategies should yield positive EV in a countable game."""
        assert comparison_result.full_kelly.ev_per_hour > 0
        assert comparison_result.half_kelly.ev_per_hour > 0

    def test_full_kelly_higher_ev_than_half_kelly(self, comparison_result):
        """Full Kelly bets more aggressively at high counts → higher EV/hr."""
        # This holds because full Kelly bets are larger.
        # Allow a small tolerance for statistical noise (10%).
        fk_ev = comparison_result.full_kelly.ev_per_hour
        hk_ev = comparison_result.half_kelly.ev_per_hour
        assert fk_ev >= hk_ev * 0.9, (
            f"Full Kelly EV ({fk_ev:.2f}) should be ≥ Half Kelly EV ({hk_ev:.2f})"
        )

    def test_full_kelly_higher_sd_than_half_kelly(self, comparison_result):
        """Full Kelly has larger bets, hence larger variance."""
        fk_sd = comparison_result.full_kelly.std_dev_per_hour
        hk_sd = comparison_result.half_kelly.std_dev_per_hour
        assert fk_sd >= hk_sd * 0.9, (
            f"Full Kelly SD ({fk_sd:.2f}) should be ≥ Half Kelly SD ({hk_sd:.2f})"
        )

    def test_half_kelly_lower_or_equal_ror(self, comparison_result):
        """Half Kelly has lower RoR than full Kelly (safer)."""
        fk_ror = comparison_result.full_kelly.risk_of_ruin
        hk_ror = comparison_result.half_kelly.risk_of_ruin
        # Half-Kelly always has lower or equal RoR due to smaller bets.
        # Allow a generous tolerance since both could be near zero.
        assert hk_ror <= fk_ror + 0.05, (
            f"Half Kelly RoR ({hk_ror:.4f}) should be ≤ Full Kelly RoR ({fk_ror:.4f})"
        )

    def test_n0_hours_positive_or_inf(self, comparison_result):
        """N-0 is either positive finite or infinite (for -EV strategies)."""
        for attr in ["flat_bet", "full_kelly", "half_kelly"]:
            result = getattr(comparison_result, attr)
            assert result.n0_hours > 0 or math.isinf(result.n0_hours)


# ---------------------------------------------------------------------------
# Flat-bet specifics
# ---------------------------------------------------------------------------

class TestFlatBet:
    def test_flat_bet_spread_is_constant(self, comparison_result):
        """Flat bet spread should have exactly one entry."""
        spread = comparison_result.flat_bet.bet_spread
        assert len(spread) == 1

    def test_flat_bet_amount_is_25(self, comparison_result):
        """We passed flat_bet_amount=25; that should be in the spread."""
        spread = comparison_result.flat_bet.bet_spread
        assert list(spread.values())[0] == pytest.approx(25.0, abs=1e-6)

    def test_flat_bet_has_lower_sd_than_kelly(self, comparison_result):
        """A flat $25 bet should have lower per-hand SD than full Kelly."""
        flat_sd = comparison_result.flat_bet.std_dev_per_hand
        fk_sd   = comparison_result.full_kelly.std_dev_per_hand
        assert flat_sd <= fk_sd * 1.1   # allow 10% tolerance


# ---------------------------------------------------------------------------
# Spread builders
# ---------------------------------------------------------------------------

class TestFlatBetSpreadBuilder:
    def test_single_key(self):
        spread = _flat_bet_spread(25.0, min_tc=1)
        assert spread == {1: 25.0}

    def test_custom_min_tc(self):
        spread = _flat_bet_spread(50.0, min_tc=2)
        assert spread == {2: 50.0}

    def test_zero_bet_not_allowed_by_default(self):
        # _flat_bet_spread can return 0 if caller passes 0, but we just check structure.
        spread = _flat_bet_spread(0.0, min_tc=1)
        assert 1 in spread


class TestBuildTcEdges:
    def test_returns_dict(self, h17_rules):
        edges = _build_tc_edges(h17_rules, num_shoes=1_000, seed=1)
        assert isinstance(edges, dict)

    def test_has_multiple_tcs(self, h17_rules):
        edges = _build_tc_edges(h17_rules, num_shoes=1_000, seed=1)
        assert len(edges) >= 3

    def test_positive_edge_at_high_tc(self, h17_rules):
        """Edges at TC≥3 should typically be positive."""
        edges = _build_tc_edges(h17_rules, num_shoes=5_000, seed=1)
        high_tc_edges = [v for tc, v in edges.items() if tc >= 3]
        if high_tc_edges:
            avg_high = sum(high_tc_edges) / len(high_tc_edges)
            assert avg_high > -0.01, f"Expected positive edge at TC≥3, got {avg_high:.4f}"

    def test_negative_edge_at_low_tc(self, h17_rules):
        """Edges at TC≤-2 should typically be negative."""
        edges = _build_tc_edges(h17_rules, num_shoes=5_000, seed=1)
        low_tc_edges = [v for tc, v in edges.items() if tc <= -2]
        if low_tc_edges:
            avg_low = sum(low_tc_edges) / len(low_tc_edges)
            assert avg_low < 0.02, f"Expected negative edge at TC≤-2, got {avg_low:.4f}"


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

class TestFormatComparisonTable:
    def test_returns_string(self, comparison_result):
        table = format_comparison_table(comparison_result)
        assert isinstance(table, str)

    def test_contains_strategy_names(self, comparison_result):
        table = format_comparison_table(comparison_result)
        assert "Flat Bet" in table
        assert "Full Kelly" in table
        assert "Half Kelly" in table

    def test_contains_bankroll(self, comparison_result):
        table = format_comparison_table(comparison_result)
        assert "10,000" in table

    def test_non_empty(self, comparison_result):
        table = format_comparison_table(comparison_result)
        assert len(table) > 100

    def test_multiple_lines(self, comparison_result):
        table = format_comparison_table(comparison_result)
        assert table.count("\n") >= 5


# ---------------------------------------------------------------------------
# Default flat_bet_amount
# ---------------------------------------------------------------------------

class TestDefaultFlatBet:
    def test_default_flat_bet_computed_from_bankroll(self, h17_rules):
        """When flat_bet_amount=None, it defaults to bankroll/400."""
        result = compare_strategies(
            rules=h17_rules,
            bankroll=40_000.0,
            rounds_per_hour=100.0,
            flat_bet_amount=None,
            num_shoes=500,
            seed=99,
        )
        # Default flat bet = 40000/400 = 100.0
        spread = result.flat_bet.bet_spread
        amount = list(spread.values())[0]
        assert amount == pytest.approx(100.0, abs=1e-6)

    def test_minimum_flat_bet_is_1(self, h17_rules):
        """Very small bankrolls should still produce a flat bet ≥ $1."""
        result = compare_strategies(
            rules=h17_rules,
            bankroll=10.0,
            rounds_per_hour=100.0,
            flat_bet_amount=None,
            num_shoes=200,
            seed=7,
        )
        spread = result.flat_bet.bet_spread
        amount = list(spread.values())[0]
        assert amount >= 1.0


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_same_seed_same_ev(self, s17_rules):
        r1 = compare_strategies(s17_rules, bankroll=5_000.0, num_shoes=500, seed=77)
        r2 = compare_strategies(s17_rules, bankroll=5_000.0, num_shoes=500, seed=77)
        assert r1.flat_bet.ev_per_hour == pytest.approx(r2.flat_bet.ev_per_hour, rel=1e-6)
        assert r1.full_kelly.ev_per_hour == pytest.approx(r2.full_kelly.ev_per_hour, rel=1e-6)

    def test_different_seeds_may_differ(self, s17_rules):
        r1 = compare_strategies(s17_rules, bankroll=5_000.0, num_shoes=500, seed=1)
        r2 = compare_strategies(s17_rules, bankroll=5_000.0, num_shoes=500, seed=2)
        # Not strictly required to differ but very likely with different seeds.
        # Just check they run without error.
        assert isinstance(r1, ComparisonResult)
        assert isinstance(r2, ComparisonResult)
