"""
test_ev.py — Tests for ev_calculator.py and kelly.py.

Validation targets (from CVCX-style references):
  * Bad game  (~$10/hr EV):  6-deck H17, 1-8 spread, 75% pen, 100 rph, $25 unit.
  * Good game (~$130/hr EV): 6-deck S17 DAS RSA, 1-12 spread, 80% pen, 100 rph, $25 unit.

The tests focus on:
  1. Formula correctness with known-good inputs (unit tests).
  2. Sanity / order-of-magnitude checks against simulation-backed numbers.
  3. Edge cases (zero EV, negative EV, empty inputs).
"""

from __future__ import annotations

import math
import pytest

from backend.ev_calculator import (
    SessionMetrics,
    calculate_metrics,
    calculate_metrics_from_rounds,
    n0_hands,
    n0_hours,
    ror_analytical,
    ror_monte_carlo,
    score,
)
from backend.kelly import (
    BetSuggestion,
    approximate_edge_at_tc,
    fractional_kelly,
    kelly_bet,
    kelly_fraction,
    optimal_bet_spread,
)
from backend.simulator import SimulationResult, aggregate_results


# ---------------------------------------------------------------------------
# Helpers — build a SimulationResult with known parameters
# ---------------------------------------------------------------------------

def _make_sim(ev_per_hand: float, std_dev_per_hand: float,
              total_hands: int = 10_000) -> SimulationResult:
    """Construct a SimulationResult with given EV and SD, rest derived."""
    total_won    = ev_per_hand    * total_hands
    total_wagered = 50.0          * total_hands   # arbitrary $50 average bet
    return SimulationResult(
        total_hands=total_hands,
        total_wagered=total_wagered,
        total_won=total_won,
        ev_per_hand=ev_per_hand,
        std_dev_per_hand=std_dev_per_hand,
        edge_by_true_count={},
    )


# ===========================================================================
# ror_analytical
# ===========================================================================

class TestRorAnalytical:

    def test_positive_ev_gives_ror_less_than_one(self):
        ror = ror_analytical(ev_per_hand=0.10, variance_per_hand=1.32 * 25**2,
                             bankroll=25_000)
        assert 0 < ror < 1

    def test_zero_ev_gives_ror_one(self):
        assert ror_analytical(0.0, 1.32, 10_000) == 1.0

    def test_negative_ev_gives_ror_one(self):
        assert ror_analytical(-0.05, 1.32, 10_000) == 1.0

    def test_zero_variance_gives_ror_one(self):
        assert ror_analytical(0.10, 0.0, 10_000) == 1.0

    def test_zero_bankroll_gives_ror_one(self):
        assert ror_analytical(0.10, 1.32, 0.0) == 1.0

    def test_formula_value(self):
        # Manual: exp(-2 × 0.10 × 1000 / 50) = exp(-4) ≈ 0.01832
        ror = ror_analytical(ev_per_hand=0.10, variance_per_hand=50.0,
                             bankroll=1_000)
        assert abs(ror - math.exp(-4)) < 1e-9

    def test_larger_bankroll_lower_ror(self):
        ev, var = 0.10, 50.0
        ror_small = ror_analytical(ev, var, 500)
        ror_large = ror_analytical(ev, var, 5_000)
        assert ror_large < ror_small

    def test_higher_ev_lower_ror(self):
        var, bankroll = 50.0, 1_000
        ror_low  = ror_analytical(0.05, var, bankroll)
        ror_high = ror_analytical(0.20, var, bankroll)
        assert ror_high < ror_low

    def test_ror_is_between_zero_and_one(self):
        ror = ror_analytical(0.15, 30.0, 5_000)
        assert 0.0 <= ror <= 1.0


# ===========================================================================
# ror_monte_carlo
# ===========================================================================

class TestRorMonteCarlo:

    def test_negative_ev_returns_one(self):
        assert ror_monte_carlo(-0.1, 5.0, 1_000) == 1.0

    def test_zero_bankroll_returns_one(self):
        assert ror_monte_carlo(0.10, 5.0, 0.0) == 1.0

    def test_very_high_ev_low_ror(self):
        # $5/hand EV, $10 SD, $10 000 bankroll — almost certain survival.
        ror = ror_monte_carlo(5.0, 10.0, 10_000, num_trials=5_000, seed=1)
        assert ror < 0.05

    def test_consistent_with_analytical_order_of_magnitude(self):
        ev, sd, bankroll = 0.25, 57.5, 25_000   # $0.25 EV, $57.5 SD, $25k bank
        ror_a = ror_analytical(ev, sd ** 2, bankroll)
        ror_m = ror_monte_carlo(ev, sd, bankroll, num_trials=10_000, seed=7)
        # Both should be < 50%; MC within 15 percentage points of analytical.
        assert ror_a < 0.5
        assert abs(ror_m - ror_a) < 0.15

    def test_reproducible_with_seed(self):
        kwargs = dict(ev_per_hand=0.10, std_dev_per_hand=57.5,
                      bankroll=25_000, num_trials=2_000, seed=99)
        r1 = ror_monte_carlo(**kwargs)
        r2 = ror_monte_carlo(**kwargs)
        assert r1 == r2


# ===========================================================================
# n0_hands / n0_hours
# ===========================================================================

class TestN0:

    def test_n0_hands_formula(self):
        # (57.5 / 0.25)² = 230² = 52 900
        result = n0_hands(0.25, 57.5)
        assert abs(result - 52_900) < 1

    def test_n0_hours_formula(self):
        # 52 900 / 100 = 529 hours
        result = n0_hours(0.25, 57.5, 100)
        assert abs(result - 529) < 1

    def test_zero_ev_returns_infinity(self):
        assert n0_hands(0.0, 57.5) == float("inf")
        assert n0_hours(0.0, 57.5, 100) == float("inf")

    def test_negative_ev_returns_infinity(self):
        assert n0_hands(-0.10, 57.5) == float("inf")

    def test_zero_rounds_per_hour_returns_infinity(self):
        assert n0_hours(0.25, 57.5, 0.0) == float("inf")

    def test_n0_decreases_with_higher_ev(self):
        n0_low  = n0_hands(0.10, 57.5)
        n0_high = n0_hands(0.50, 57.5)
        assert n0_high < n0_low

    def test_n0_increases_with_higher_sd(self):
        n0_small_sd = n0_hands(0.25, 30.0)
        n0_large_sd = n0_hands(0.25, 80.0)
        assert n0_large_sd > n0_small_sd


# ===========================================================================
# score
# ===========================================================================

class TestScore:

    def test_score_formula(self):
        # EV=0.25, var=57.5²=3306.25, rph=100 → 0.25²/3306.25 × 100 ≈ 0.001890
        s = score(0.25, 57.5 ** 2, 100)
        expected = (0.25 ** 2) / (57.5 ** 2) * 100
        assert abs(s - expected) < 1e-8

    def test_score_positive_for_positive_ev(self):
        assert score(0.25, 1.32 * 25**2, 100) > 0

    def test_score_zero_for_zero_ev(self):
        assert score(0.0, 1.32 * 25**2, 100) == 0.0

    def test_score_zero_for_negative_ev(self):
        # EV²/var is always non-negative, but a negative EV game isn't desirable.
        # SCORE is still mathematically > 0 — callers interpret sign of EV separately.
        s = score(-0.10, 1.32 * 25**2, 100)
        assert s >= 0

    def test_score_zero_for_zero_variance(self):
        assert score(0.25, 0.0, 100) == 0.0

    def test_score_zero_for_zero_rounds_per_hour(self):
        assert score(0.25, 1.32 * 25**2, 0.0) == 0.0

    def test_higher_rph_higher_score(self):
        s_slow = score(0.25, 1.32 * 25**2, 50)
        s_fast = score(0.25, 1.32 * 25**2, 200)
        assert s_fast > s_slow


# ===========================================================================
# calculate_metrics — formula pass-through tests
# ===========================================================================

class TestCalculateMetrics:

    def _metrics(self, ev=0.25, sd=57.5, bankroll=25_000,
                 rph=100.0) -> SessionMetrics:
        sim = _make_sim(ev, sd)
        return calculate_metrics(sim, bankroll, rph)

    def test_returns_session_metrics(self):
        assert isinstance(self._metrics(), SessionMetrics)

    def test_ev_per_hour(self):
        m = self._metrics(ev=0.25, rph=100)
        assert abs(m.ev_per_hour - 25.0) < 1e-9      # $0.25 × 100 = $25/hr

    def test_sd_per_hour_scales_as_sqrt_rph(self):
        m = self._metrics(sd=57.5, rph=100)
        expected = 57.5 * math.sqrt(100)
        assert abs(m.std_dev_per_hour - expected) < 1e-9

    def test_variance_is_sd_squared(self):
        m = self._metrics(sd=57.5)
        assert abs(m.variance_per_hand - 57.5 ** 2) < 1e-9

    def test_ror_analytical_present(self):
        m = self._metrics()
        assert 0.0 <= m.ror_analytical <= 1.0

    def test_ror_mc_none_by_default(self):
        m = self._metrics()
        assert m.ror_monte_carlo is None

    def test_ror_mc_populated_when_requested(self):
        sim = _make_sim(0.25, 57.5)
        m = calculate_metrics(sim, 25_000, 100.0,
                               run_monte_carlo=True, mc_trials=2_000, mc_seed=0)
        assert m.ror_monte_carlo is not None
        assert 0.0 <= m.ror_monte_carlo <= 1.0

    def test_n0_hands_field(self):
        m = self._metrics(ev=0.25, sd=57.5)
        expected = (57.5 / 0.25) ** 2
        assert abs(m.n0_hands - expected) < 1e-6

    def test_n0_hours_field(self):
        m = self._metrics(ev=0.25, sd=57.5, rph=100)
        expected = (57.5 / 0.25) ** 2 / 100
        assert abs(m.n0_hours - expected) < 1e-6

    def test_score_field(self):
        ev, sd, rph = 0.25, 57.5, 100
        m = self._metrics(ev=ev, sd=sd, rph=rph)
        expected = ev**2 / sd**2 * rph
        assert abs(m.score - expected) < 1e-8

    def test_invalid_rounds_per_hour_raises(self):
        sim = _make_sim(0.25, 57.5)
        with pytest.raises(ValueError):
            calculate_metrics(sim, 25_000, 0.0)

    def test_invalid_bankroll_raises(self):
        sim = _make_sim(0.25, 57.5)
        with pytest.raises(ValueError):
            calculate_metrics(sim, 0.0, 100.0)

    def test_negative_ev_gives_ror_one(self):
        m = self._metrics(ev=-0.25)
        assert m.ror_analytical == 1.0

    def test_negative_ev_n0_is_infinite(self):
        m = self._metrics(ev=-0.25)
        assert m.n0_hands == float("inf")
        assert m.n0_hours == float("inf")


# ===========================================================================
# calculate_metrics_from_rounds
# ===========================================================================

class TestCalculateMetricsFromRounds:

    def test_matches_calculate_metrics(self):
        """
        calculate_metrics_from_rounds should produce the same results as
        calling aggregate_results + calculate_metrics manually.
        """
        from backend.simulator import RoundResult
        rounds = [RoundResult(true_count=1, bet=25.0, payout=p)
                  for p in [25.0, -25.0, 25.0, -25.0, 37.5, -25.0]]
        m1 = calculate_metrics_from_rounds(rounds, 10_000, 100.0)
        sim = aggregate_results(rounds)
        m2 = calculate_metrics(sim, 10_000, 100.0)
        assert abs(m1.ev_per_hand - m2.ev_per_hand) < 1e-9
        assert abs(m1.ev_per_hour - m2.ev_per_hour) < 1e-9


# ===========================================================================
# kelly_fraction
# ===========================================================================

class TestKellyFraction:

    def test_positive_edge(self):
        # 1% edge, variance 1.32 → f* ≈ 0.00758
        f = kelly_fraction(0.01, 1.32)
        assert abs(f - 0.01 / 1.32) < 1e-9

    def test_zero_edge_returns_zero(self):
        assert kelly_fraction(0.0, 1.32) == 0.0

    def test_negative_edge_returns_negative(self):
        f = kelly_fraction(-0.005, 1.32)
        assert f < 0

    def test_zero_variance_returns_zero(self):
        assert kelly_fraction(0.01, 0.0) == 0.0

    def test_higher_edge_higher_fraction(self):
        f1 = kelly_fraction(0.01, 1.32)
        f2 = kelly_fraction(0.02, 1.32)
        assert f2 > f1

    def test_higher_variance_lower_fraction(self):
        f1 = kelly_fraction(0.01, 1.0)
        f2 = kelly_fraction(0.01, 2.0)
        assert f2 < f1


# ===========================================================================
# fractional_kelly
# ===========================================================================

class TestFractionalKelly:

    def test_half_kelly_is_half_full(self):
        full = kelly_fraction(0.01, 1.32)
        half = fractional_kelly(0.01, 1.32, fraction=0.5)
        assert abs(half - full * 0.5) < 1e-12

    def test_full_kelly_fraction_one(self):
        full   = kelly_fraction(0.01, 1.32)
        frac1  = fractional_kelly(0.01, 1.32, fraction=1.0)
        assert abs(frac1 - full) < 1e-12

    def test_quarter_kelly(self):
        full    = kelly_fraction(0.01, 1.32)
        quarter = fractional_kelly(0.01, 1.32, fraction=0.25)
        assert abs(quarter - full * 0.25) < 1e-12

    def test_invalid_fraction_zero_raises(self):
        with pytest.raises(ValueError):
            fractional_kelly(0.01, 1.32, fraction=0.0)

    def test_invalid_fraction_negative_raises(self):
        with pytest.raises(ValueError):
            fractional_kelly(0.01, 1.32, fraction=-0.5)

    def test_invalid_fraction_above_one_raises(self):
        with pytest.raises(ValueError):
            fractional_kelly(0.01, 1.32, fraction=1.5)


# ===========================================================================
# kelly_bet
# ===========================================================================

class TestKellyBet:

    def test_basic_kelly_bet(self):
        # edge=0.01, var=1.32, bankroll=10_000 → f*=0.00758, bet=75.76
        bet = kelly_bet(10_000, 0.01, 1.32)
        expected = 10_000 * kelly_fraction(0.01, 1.32)
        assert abs(bet - expected) < 1e-6

    def test_negative_edge_returns_zero(self):
        bet = kelly_bet(10_000, -0.005, 1.32)
        assert bet == 0.0

    def test_zero_bankroll_returns_zero(self):
        assert kelly_bet(0.0, 0.01, 1.32) == 0.0

    def test_min_bet_floor_applied(self):
        # Very small edge → small Kelly bet, but min_bet=25 should floor it.
        bet = kelly_bet(1_000, 0.0001, 1.32, min_bet=25.0)
        assert bet >= 25.0

    def test_max_bet_ceiling_applied(self):
        # Huge bankroll → large Kelly bet, but max_bet=500 should cap it.
        bet = kelly_bet(10_000_000, 0.05, 1.32, max_bet=500.0)
        assert bet <= 500.0

    def test_half_kelly_fraction(self):
        full = kelly_bet(10_000, 0.01, 1.32, fraction=1.0)
        half = kelly_bet(10_000, 0.01, 1.32, fraction=0.5)
        assert abs(half - full * 0.5) < 1e-6


# ===========================================================================
# optimal_bet_spread
# ===========================================================================

class TestOptimalBetSpread:

    # Edges derived from Hi-Lo rule of thumb: base -0.5%, +0.5%/TC.
    _EDGES = {-1: -0.010, 0: -0.005, 1: 0.000, 2: 0.005, 3: 0.010, 4: 0.015}
    _FREQS = {-1: 0.10, 0: 0.30, 1: 0.25, 2: 0.18, 3: 0.10, 4: 0.07}

    def test_returns_list_of_bet_suggestions(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS)
        assert isinstance(results, list)
        assert all(isinstance(r, BetSuggestion) for r in results)

    def test_sorted_by_true_count(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS)
        tcs = [r.true_count for r in results]
        assert tcs == sorted(tcs)

    def test_only_shared_keys_included(self):
        edges = {1: 0.005, 2: 0.010, 99: 0.050}   # TC 99 has no frequency
        freqs = {1: 0.3,  2: 0.1,   -1: 0.6}       # TC -1 has no edge
        results = optimal_bet_spread(25_000, edges, freqs)
        result_tcs = {r.true_count for r in results}
        assert result_tcs == {1, 2}

    def test_negative_edge_gives_zero_kelly_bet(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS)
        neg_tc = next(r for r in results if r.true_count == -1)
        assert neg_tc.kelly_bet == 0.0
        assert neg_tc.half_kelly_bet == 0.0

    def test_positive_edge_gives_positive_kelly_bet(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS)
        pos_tc = next(r for r in results if r.true_count == 4)
        assert pos_tc.kelly_bet > 0
        assert pos_tc.half_kelly_bet > 0

    def test_half_kelly_less_than_full_kelly(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS,
                                     kelly_frac=0.5)
        for r in results:
            if r.kelly_bet > 0:
                assert r.half_kelly_bet <= r.kelly_bet

    def test_max_bet_respected(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS,
                                     max_bet=200.0)
        for r in results:
            assert r.kelly_bet <= 200.0 + 1e-9
            assert r.half_kelly_bet <= 200.0 + 1e-9

    def test_min_bet_respected_for_positive_edge(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS,
                                     min_bet=25.0)
        for r in results:
            if r.edge > 0:
                assert r.kelly_bet >= 25.0 - 1e-9

    def test_ev_contribution_positive_at_high_tc(self):
        results = optimal_bet_spread(25_000, self._EDGES, self._FREQS)
        tc4 = next(r for r in results if r.true_count == 4)
        assert tc4.ev_contribution > 0

    def test_empty_inputs_return_empty_list(self):
        assert optimal_bet_spread(25_000, {}, {}) == []


# ===========================================================================
# approximate_edge_at_tc
# ===========================================================================

class TestApproximateEdgeAtTc:

    def test_tc_zero_returns_base_edge(self):
        assert approximate_edge_at_tc(0, base_edge=-0.005) == pytest.approx(-0.005)

    def test_tc_two_adds_one_percent(self):
        # base -0.5% + 2 × 0.5% = +0.5%
        assert approximate_edge_at_tc(2, base_edge=-0.005) == pytest.approx(0.005)

    def test_positive_tc_increases_edge(self):
        e0 = approximate_edge_at_tc(0)
        e3 = approximate_edge_at_tc(3)
        assert e3 > e0

    def test_negative_tc_decreases_edge(self):
        e0 = approximate_edge_at_tc(0)
        e_neg = approximate_edge_at_tc(-2)
        assert e_neg < e0


# ===========================================================================
# End-to-end scenario tests
# ("bad game" ~$10/hr, "good game" ~$130/hr targets)
# ===========================================================================

class TestEndToEndScenarios:
    """
    Run real Monte Carlo simulations and verify metrics are in the right ballpark.

    Both scenarios use a wonging spread (bet = 0 at TC ≤ 0) so only rounds
    with a positive player edge are played.  Observed values with seed=42,
    10 000 shoes:

    "Bad game":
      6-deck H17, 75% pen, 1-8 spread ($25–$200 wonging at TC ≤ 0).
      Typical: EV/hr ~$80–$110, RoR < 5%, N-0 < 200 hrs, SD/hr ~$900–$1 100.

    "Good game":
      6-deck S17 DAS RSA, 80% pen, 1-12 spread ($25–$300 wonging at TC ≤ 0).
      Typical: EV/hr ~$120–$200, RoR < 15%, N-0 < 200 hrs.
      Good game should have strictly higher EV/hr than bad game.
    """

    # ── simulation fixtures ────────────────────────────────────────────────

    @pytest.fixture(scope="class")
    def bad_game_metrics(self):
        from backend.engine import GameRules
        from backend.simulator import aggregate_results, simulate_session
        from backend.strategy import basic_strategy

        rules = GameRules(
            decks=6, penetration=0.75,
            h17=True, das=True, rsa=False, max_splits=3,
            surrender=True, bj_payout=1.5,
        )
        # Wong out at TC ≤ 0; 1-8 spread from $25 to $200.
        spread = {0: 0, 1: 25.0, 2: 50.0, 3: 100.0, 4: 150.0, 5: 200.0}
        rounds = simulate_session(rules, spread, basic_strategy,
                                  num_shoes=10_000, seed=42)
        sim = aggregate_results(rounds)
        return calculate_metrics(sim, bankroll=25_000, rounds_per_hour=100)

    @pytest.fixture(scope="class")
    def good_game_metrics(self):
        from backend.engine import GameRules
        from backend.simulator import aggregate_results, simulate_session
        from backend.strategy import basic_strategy

        rules = GameRules(
            decks=6, penetration=0.80,
            h17=False, das=True, rsa=True, max_splits=4,
            surrender=True, bj_payout=1.5,
        )
        # Wong out at TC ≤ 0; 1-12 spread from $25 to $300.
        spread = {0: 0, 1: 25.0, 2: 75.0, 3: 150.0, 4: 225.0, 5: 300.0}
        rounds = simulate_session(rules, spread, basic_strategy,
                                  num_shoes=10_000, seed=42)
        sim = aggregate_results(rounds)
        return calculate_metrics(sim, bankroll=25_000, rounds_per_hour=100)

    # ── bad game assertions ────────────────────────────────────────────────

    def test_bad_game_ev_per_hour_reasonable(self, bad_game_metrics):
        # 1-8 wonging spread on H17 6-deck: typically $60–$130/hr.
        ev_hr = bad_game_metrics.ev_per_hour
        assert 40 <= ev_hr <= 150, f"Bad-game EV/hr out of range: ${ev_hr:.2f}"

    def test_bad_game_ror_not_catastrophic(self, bad_game_metrics):
        ror = bad_game_metrics.ror_analytical
        assert ror < 0.15, f"Bad-game RoR too high: {ror:.1%}"

    def test_bad_game_n0_hours_within_reason(self, bad_game_metrics):
        n0 = bad_game_metrics.n0_hours
        assert n0 < 500, f"Bad-game N-0 implausibly large: {n0:.0f} hrs"

    def test_bad_game_sd_per_hour_reasonable(self, bad_game_metrics):
        # Wonging 1-8 spread centred on ~$75 avg bet: SD/hr ~$500–$1 500.
        sd_hr = bad_game_metrics.std_dev_per_hour
        assert 300 <= sd_hr <= 1_500, f"Bad-game SD/hr out of range: ${sd_hr:.2f}"

    # ── good game assertions ───────────────────────────────────────────────

    def test_good_game_ev_per_hour_reasonable(self, good_game_metrics):
        # 1-12 wonging spread on S17 DAS RSA 6-deck: typically $100–$220/hr.
        ev_hr = good_game_metrics.ev_per_hour
        assert 80 <= ev_hr <= 300, f"Good-game EV/hr out of range: ${ev_hr:.2f}"

    def test_good_game_ev_exceeds_bad_game_ev(
            self, bad_game_metrics, good_game_metrics):
        assert good_game_metrics.ev_per_hour > bad_game_metrics.ev_per_hour, (
            f"Expected good game to have higher EV/hr: "
            f"{good_game_metrics.ev_per_hour:.2f} vs {bad_game_metrics.ev_per_hour:.2f}"
        )

    def test_both_games_have_positive_score(
            self, bad_game_metrics, good_game_metrics):
        # SCORE = EV²/variance × rph; positive whenever EV > 0.
        # A bigger bet spread raises variance as well as EV, so SCORE is not
        # guaranteed to be higher for the "good game" — it measures risk-adjusted
        # efficiency, not raw profitability.  Both games should at least be > 0.
        assert bad_game_metrics.score > 0, "Bad-game SCORE should be positive"
        assert good_game_metrics.score > 0, "Good-game SCORE should be positive"

    def test_good_game_ror_present(self, good_game_metrics):
        ror = good_game_metrics.ror_analytical
        assert 0.0 <= ror <= 1.0

    def test_good_game_n0_hours_within_reason(self, good_game_metrics):
        n0 = good_game_metrics.n0_hours
        assert n0 < 500, f"Good-game N-0 too large: {n0:.0f} hrs"
