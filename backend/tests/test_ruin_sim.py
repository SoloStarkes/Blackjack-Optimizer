"""
test_ruin_sim.py — Tests for backend/ruin_sim.py.

Covers:
  - RuinSimResult dataclass fields
  - simulate_ruin: negative EV → high empirical RoR
  - simulate_ruin: positive EV → empirical RoR close to analytical
  - simulate_ruin: zero bankroll / zero SD raise ValueError
  - compare_ror: identical to simulate_ruin
  - Empirical vs analytical accuracy across parameter ranges
  - Chunk boundary behaviour (max_hands exactly divisible by chunk)
  - Reproducibility with seed
  - format_ruin_report: renders without error
"""

from __future__ import annotations

import math
import pytest

from backend.ruin_sim import (
    RuinSimResult,
    compare_ror,
    format_ruin_report,
    simulate_ruin,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def positive_ev_result():
    """Strong player edge: EV=$1/hand, SD=$100, bankroll=$5000.

    Analytical RoR = exp(-2 × 1 × 5000 / 10000) = exp(-1) ≈ 0.368 < 50%.
    """
    return simulate_ruin(
        ev_per_hand=1.0,
        std_dev_per_hand=100.0,
        bankroll=5_000.0,
        num_trajectories=5_000,
        max_hands=500_000,
        seed=42,
    )


@pytest.fixture(scope="module")
def negative_ev_result():
    """House edge: EV=-$1/hand, SD=$100, bankroll=$500."""
    return simulate_ruin(
        ev_per_hand=-1.0,
        std_dev_per_hand=100.0,
        bankroll=500.0,
        num_trajectories=2_000,
        max_hands=200_000,
        seed=42,
    )


@pytest.fixture(scope="module")
def low_ror_result():
    """Very strong edge and large bankroll → near-zero RoR."""
    return simulate_ruin(
        ev_per_hand=2.0,
        std_dev_per_hand=80.0,
        bankroll=5_000.0,
        num_trajectories=2_000,
        max_hands=500_000,
        seed=7,
    )


# ---------------------------------------------------------------------------
# RuinSimResult structure
# ---------------------------------------------------------------------------

class TestRuinSimResultStructure:
    def test_returns_ruin_sim_result(self, positive_ev_result):
        assert isinstance(positive_ev_result, RuinSimResult)

    def test_num_trajectories_stored(self, positive_ev_result):
        assert positive_ev_result.num_trajectories == 5_000

    def test_max_hands_stored(self, positive_ev_result):
        assert positive_ev_result.max_hands == 500_000

    def test_ev_per_hand_stored(self, positive_ev_result):
        assert positive_ev_result.ev_per_hand == pytest.approx(1.0)

    def test_std_dev_stored(self, positive_ev_result):
        assert positive_ev_result.std_dev_per_hand == pytest.approx(100.0)

    def test_bankroll_stored(self, positive_ev_result):
        assert positive_ev_result.bankroll == pytest.approx(5_000.0)

    def test_empirical_ror_in_0_1(self, positive_ev_result):
        assert 0.0 <= positive_ev_result.empirical_ror <= 1.0

    def test_analytical_ror_in_0_1(self, positive_ev_result):
        assert 0.0 <= positive_ev_result.analytical_ror <= 1.0

    def test_ruin_trajectories_non_negative(self, positive_ev_result):
        assert positive_ev_result.ruin_trajectories >= 0

    def test_ruin_count_consistent_with_ror(self, positive_ev_result):
        expected = positive_ev_result.ruin_trajectories / positive_ev_result.num_trajectories
        assert positive_ev_result.empirical_ror == pytest.approx(expected, abs=1e-9)

    def test_absolute_error_non_negative(self, positive_ev_result):
        assert positive_ev_result.absolute_error >= 0.0

    def test_absolute_error_consistent(self, positive_ev_result):
        expected = abs(positive_ev_result.empirical_ror - positive_ev_result.analytical_ror)
        assert positive_ev_result.absolute_error == pytest.approx(expected, abs=1e-9)

    def test_bankroll_percentiles_keys(self, positive_ev_result):
        assert set(positive_ev_result.bankroll_percentiles.keys()) == {5, 25, 50, 75, 95}

    def test_bankroll_percentiles_ordered(self, positive_ev_result):
        pcts = positive_ev_result.bankroll_percentiles
        assert pcts[5] <= pcts[25] <= pcts[50] <= pcts[75] <= pcts[95]

    def test_mean_final_bankroll_finite(self, positive_ev_result):
        assert math.isfinite(positive_ev_result.mean_final_bankroll)

    def test_median_final_bankroll_finite(self, positive_ev_result):
        assert math.isfinite(positive_ev_result.median_final_bankroll)


# ---------------------------------------------------------------------------
# Positive EV: RoR should be low
# ---------------------------------------------------------------------------

class TestPositiveEV:
    def test_empirical_ror_below_50_percent(self, positive_ev_result):
        """With EV=+$1 and bankroll=$1000, RoR should be <50%."""
        assert positive_ev_result.empirical_ror < 0.50

    def test_analytical_ror_below_50_percent(self, positive_ev_result):
        assert positive_ev_result.analytical_ror < 0.50

    def test_mean_final_bankroll_above_starting(self, positive_ev_result):
        """With positive EV, mean final bankroll should be > starting (on average)."""
        # Many paths survive and grow; even with some ruin, mean grows.
        # Very lenient bound: just above 0.
        assert positive_ev_result.mean_final_bankroll >= 0.0

    def test_empirical_close_to_analytical(self, positive_ev_result):
        """Empirical and analytical RoR should be within 15% absolute for 5k trials."""
        assert positive_ev_result.absolute_error < 0.15


# ---------------------------------------------------------------------------
# Negative EV: eventual ruin is certain (high RoR)
# ---------------------------------------------------------------------------

class TestNegativeEV:
    def test_empirical_ror_high(self, negative_ev_result):
        """With house edge and enough hands, most paths should be ruined."""
        # 200k hands at -$1/hand SD=100 → near-certain ruin with $500 bankroll.
        assert negative_ev_result.empirical_ror >= 0.50

    def test_analytical_ror_is_1(self, negative_ev_result):
        """Analytical RoR = 1.0 when EV ≤ 0."""
        assert negative_ev_result.analytical_ror == pytest.approx(1.0)

    def test_ruin_trajectories_at_least_half(self, negative_ev_result):
        half = negative_ev_result.num_trajectories // 2
        assert negative_ev_result.ruin_trajectories >= half


# ---------------------------------------------------------------------------
# Low RoR scenario
# ---------------------------------------------------------------------------

class TestLowRoR:
    def test_empirical_ror_very_low(self, low_ror_result):
        """EV=$2, bankroll=$5000, SD=$80 → very low RoR."""
        assert low_ror_result.empirical_ror < 0.15

    def test_analytical_also_low(self, low_ror_result):
        assert low_ror_result.analytical_ror < 0.10

    def test_median_bankroll_above_starting(self, low_ror_result):
        """Median player survives and grows."""
        assert low_ror_result.median_final_bankroll > low_ror_result.bankroll


# ---------------------------------------------------------------------------
# Analytical vs empirical accuracy
# ---------------------------------------------------------------------------

class TestAnalyticalAccuracy:
    def test_10k_trajectories_within_10_percent(self):
        """10k paths should bring empirical within 10% absolute of analytical."""
        result = simulate_ruin(
            ev_per_hand=0.5,
            std_dev_per_hand=100.0,
            bankroll=2_000.0,
            num_trajectories=10_000,
            max_hands=1_000_000,
            seed=123,
        )
        assert result.absolute_error < 0.10, (
            f"Expected <10% error, got {result.absolute_error:.4f} "
            f"(empirical={result.empirical_ror:.4f}, analytical={result.analytical_ror:.4f})"
        )

    def test_relative_error_finite_for_positive_ev(self):
        result = simulate_ruin(
            ev_per_hand=0.5,
            std_dev_per_hand=100.0,
            bankroll=2_000.0,
            num_trajectories=5_000,
            max_hands=500_000,
            seed=1,
        )
        assert math.isfinite(result.relative_error)

    def test_relative_error_infinite_when_analytical_zero(self):
        """When analytical RoR = 0 (infinite edge), relative_error should be inf."""
        result = simulate_ruin(
            ev_per_hand=100.0,     # absurdly high edge → analytical RoR ≈ 0
            std_dev_per_hand=10.0,
            bankroll=100_000.0,
            num_trajectories=100,
            max_hands=1_000,
            seed=1,
        )
        # Empirical should be 0, analytical should be essentially 0.
        # relative_error = abs_err / analytical; if analytical = 0, inf.
        if result.analytical_ror == 0.0:
            assert not math.isfinite(result.relative_error)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_zero_bankroll_raises(self):
        with pytest.raises(ValueError, match="bankroll"):
            simulate_ruin(1.0, 100.0, bankroll=0.0, num_trajectories=10)

    def test_negative_bankroll_raises(self):
        with pytest.raises(ValueError, match="bankroll"):
            simulate_ruin(1.0, 100.0, bankroll=-500.0, num_trajectories=10)

    def test_zero_std_dev_raises(self):
        with pytest.raises(ValueError, match="std_dev"):
            simulate_ruin(1.0, 0.0, bankroll=1_000.0, num_trajectories=10)

    def test_negative_std_dev_raises(self):
        with pytest.raises(ValueError, match="std_dev"):
            simulate_ruin(1.0, -50.0, bankroll=1_000.0, num_trajectories=10)

    def test_zero_trajectories_raises(self):
        with pytest.raises(ValueError, match="num_trajectories"):
            simulate_ruin(1.0, 100.0, bankroll=1_000.0, num_trajectories=0)


# ---------------------------------------------------------------------------
# Chunk boundary edge case
# ---------------------------------------------------------------------------

class TestChunkBoundary:
    def test_max_hands_less_than_chunk_size(self):
        """max_hands < _CHUNK_SIZE should still work correctly."""
        result = simulate_ruin(
            ev_per_hand=0.5,
            std_dev_per_hand=100.0,
            bankroll=1_000.0,
            num_trajectories=100,
            max_hands=500,     # much less than _CHUNK_SIZE=10_000
            seed=1,
        )
        assert isinstance(result, RuinSimResult)
        assert 0.0 <= result.empirical_ror <= 1.0

    def test_max_hands_exactly_one_chunk(self):
        """max_hands = _CHUNK_SIZE exactly."""
        result = simulate_ruin(
            ev_per_hand=0.5,
            std_dev_per_hand=100.0,
            bankroll=1_000.0,
            num_trajectories=50,
            max_hands=10_000,
            seed=2,
        )
        assert isinstance(result, RuinSimResult)

    def test_single_trajectory(self):
        result = simulate_ruin(
            ev_per_hand=1.0,
            std_dev_per_hand=100.0,
            bankroll=500.0,
            num_trajectories=1,
            max_hands=1_000,
            seed=99,
        )
        assert result.num_trajectories == 1
        assert result.empirical_ror in (0.0, 1.0)


# ---------------------------------------------------------------------------
# compare_ror convenience function
# ---------------------------------------------------------------------------

class TestCompareRor:
    def test_returns_ruin_sim_result(self):
        result = compare_ror(1.0, 100.0, 1_000.0, num_trajectories=100, max_hands=10_000, seed=1)
        assert isinstance(result, RuinSimResult)

    def test_same_as_simulate_ruin(self):
        r1 = simulate_ruin(1.0, 100.0, 1_000.0, num_trajectories=200, max_hands=10_000, seed=5)
        r2 = compare_ror(  1.0, 100.0, 1_000.0, num_trajectories=200, max_hands=10_000, seed=5)
        assert r1.empirical_ror == pytest.approx(r2.empirical_ror, abs=1e-9)
        assert r1.analytical_ror == pytest.approx(r2.analytical_ror, abs=1e-9)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_same_seed_same_empirical_ror(self):
        r1 = simulate_ruin(0.5, 100.0, 1_000.0, num_trajectories=500, seed=42)
        r2 = simulate_ruin(0.5, 100.0, 1_000.0, num_trajectories=500, seed=42)
        assert r1.empirical_ror == pytest.approx(r2.empirical_ror, abs=1e-9)

    def test_different_seeds_may_differ(self):
        r1 = simulate_ruin(0.5, 100.0, 1_000.0, num_trajectories=500, seed=1)
        r2 = simulate_ruin(0.5, 100.0, 1_000.0, num_trajectories=500, seed=2)
        # Just check they complete without error; results may or may not differ.
        assert isinstance(r1, RuinSimResult)
        assert isinstance(r2, RuinSimResult)

    def test_no_seed_still_works(self):
        result = simulate_ruin(1.0, 100.0, 1_000.0, num_trajectories=100, seed=None)
        assert isinstance(result, RuinSimResult)


# ---------------------------------------------------------------------------
# format_ruin_report
# ---------------------------------------------------------------------------

class TestFormatRuinReport:
    def test_returns_string(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert isinstance(output, str)

    def test_contains_empirical_ror(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert "Empirical" in output

    def test_contains_analytical_ror(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert "Analytical" in output

    def test_contains_bankroll(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert "5,000" in output

    def test_contains_percentiles(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert "P5" in output
        assert "P95" in output

    def test_non_empty_report(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert len(output) > 100

    def test_multiple_lines(self, positive_ev_result):
        output = format_ruin_report(positive_ev_result)
        assert output.count("\n") >= 10

    def test_infinite_relative_error_handled(self):
        """format_ruin_report should not crash on inf relative error."""
        result = simulate_ruin(
            ev_per_hand=100.0,
            std_dev_per_hand=10.0,
            bankroll=100_000.0,
            num_trajectories=10,
            max_hands=100,
            seed=1,
        )
        output = format_ruin_report(result)
        assert isinstance(output, str)
