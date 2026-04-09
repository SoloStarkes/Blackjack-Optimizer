"""
test_simulator.py — Tests for backend/simulator.py.

Covers:
- RoundResult and SimulationResult structure
- _bet_for_tc() step-function bet lookup
- Wong-out filtering (bet=0 rounds excluded from results)
- simulate_session() reproducibility and basic mechanics
- aggregate_results() correctness
- Statistical properties:
    * Flat-bet house edge ≈ −0.5 % (tolerance ±1.2 %)
    * Positive edge at high true counts (TC ≥ 3)
    * Counting spread improves EV over flat betting
"""

from __future__ import annotations

import sys, os, math, statistics
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.engine import GameRules
from backend.strategy import basic_strategy
from backend.simulator import (
    RoundResult,
    SimulationResult,
    _bet_for_tc,
    aggregate_results,
    simulate_session,
)


# ---------------------------------------------------------------------------
# Shared fixtures / constants
# ---------------------------------------------------------------------------

RULES = GameRules(decks=6, penetration=0.75, h17=True, das=True,
                  rsa=True, max_splits=3, surrender=True, bj_payout=1.5)

# Flat-bet spread: always bet $25, regardless of count
FLAT_SPREAD: dict = {-100: 25.0}

# Wonging spread: bet $0 at TC ≤ 0, $25 at TC=1, $100 at TC=3, $200 at TC=5+
COUNTING_SPREAD: dict = {0: 0.0, 1: 25.0, 2: 50.0, 3: 100.0, 4: 150.0, 5: 200.0}


# ---------------------------------------------------------------------------
# _bet_for_tc
# ---------------------------------------------------------------------------

class TestBetForTc:
    def test_exact_match(self):
        spread = {1: 25.0, 2: 50.0, 3: 100.0}
        assert _bet_for_tc(spread, 2) == 50.0

    def test_step_function_uses_highest_eligible_key(self):
        spread = {1: 25.0, 3: 100.0}
        # TC=2 → largest key ≤ 2 is 1 → bet=25
        assert _bet_for_tc(spread, 2) == 25.0

    def test_tc_above_all_keys_uses_max_key(self):
        spread = {1: 25.0, 5: 200.0}
        assert _bet_for_tc(spread, 10) == 200.0

    def test_tc_below_all_keys_wongs_out(self):
        spread = {1: 25.0, 2: 50.0}
        assert _bet_for_tc(spread, 0) == 0.0

    def test_zero_bet_key_wongs_out(self):
        spread = {0: 0.0, 1: 25.0}
        assert _bet_for_tc(spread, 0) == 0.0
        assert _bet_for_tc(spread, 1) == 25.0

    def test_negative_tc_with_negative_key(self):
        spread = {-5: 10.0, 0: 25.0}
        assert _bet_for_tc(spread, -3) == 10.0

    def test_empty_spread_returns_zero(self):
        assert _bet_for_tc({}, 5) == 0.0

    def test_exact_tc_boundary(self):
        spread = {3: 100.0, 4: 150.0}
        assert _bet_for_tc(spread, 3) == 100.0
        assert _bet_for_tc(spread, 4) == 150.0


# ---------------------------------------------------------------------------
# RoundResult / SimulationResult structure
# ---------------------------------------------------------------------------

class TestResultTypes:
    def test_round_result_is_namedtuple(self):
        r = RoundResult(true_count=2, bet=50.0, payout=50.0)
        assert r.true_count == 2
        assert r.bet == 50.0
        assert r.payout == 50.0

    def test_round_result_unpacks(self):
        tc, bet, payout = RoundResult(true_count=1, bet=25.0, payout=-25.0)
        assert (tc, bet, payout) == (1, 25.0, -25.0)

    def test_simulation_result_fields(self):
        res = SimulationResult(
            total_hands=100,
            total_wagered=2500.0,
            total_won=-50.0,
            ev_per_hand=-0.50,
            std_dev_per_hand=28.0,
            edge_by_true_count={1: -0.01, 3: 0.01},
        )
        assert res.total_hands == 100
        assert res.total_wagered == 2500.0
        assert res.total_won == -50.0
        assert isinstance(res.edge_by_true_count, dict)


# ---------------------------------------------------------------------------
# aggregate_results
# ---------------------------------------------------------------------------

class TestAggregateResults:
    def test_empty_rounds_returns_zero_result(self):
        res = aggregate_results([])
        assert res.total_hands == 0
        assert res.total_wagered == 0.0
        assert res.total_won == 0.0
        assert res.ev_per_hand == 0.0
        assert res.std_dev_per_hand == 0.0
        assert res.edge_by_true_count == {}

    def test_single_win(self):
        rounds = [RoundResult(true_count=2, bet=100.0, payout=100.0)]
        res = aggregate_results(rounds)
        assert res.total_hands == 1
        assert res.total_wagered == pytest.approx(100.0)
        assert res.total_won == pytest.approx(100.0)
        assert res.ev_per_hand == pytest.approx(100.0)
        assert res.std_dev_per_hand == 0.0   # stdev of one value
        assert res.edge_by_true_count[2] == pytest.approx(1.0)  # 100% edge

    def test_single_loss(self):
        rounds = [RoundResult(true_count=0, bet=25.0, payout=-25.0)]
        res = aggregate_results(rounds)
        assert res.total_won == pytest.approx(-25.0)
        assert res.ev_per_hand == pytest.approx(-25.0)
        assert res.edge_by_true_count[0] == pytest.approx(-1.0)

    def test_totals_are_correct(self):
        rounds = [
            RoundResult(true_count=1, bet=25.0, payout=25.0),   # win
            RoundResult(true_count=1, bet=25.0, payout=-25.0),  # loss
            RoundResult(true_count=2, bet=50.0, payout=50.0),   # win
        ]
        res = aggregate_results(rounds)
        assert res.total_hands == 3
        assert res.total_wagered == pytest.approx(100.0)
        assert res.total_won == pytest.approx(50.0)
        assert res.ev_per_hand == pytest.approx(50.0 / 3)

    def test_ev_per_hand_equals_mean_payout(self):
        rounds = [RoundResult(2, 50.0, p) for p in [25.0, -50.0, 75.0, -25.0]]
        res = aggregate_results(rounds)
        expected_ev = statistics.mean([25.0, -50.0, 75.0, -25.0])
        assert res.ev_per_hand == pytest.approx(expected_ev)

    def test_std_dev_is_sample_stdev(self):
        payouts = [100.0, -25.0, 50.0, -100.0, 150.0]
        rounds = [RoundResult(1, 25.0, p) for p in payouts]
        res = aggregate_results(rounds)
        assert res.std_dev_per_hand == pytest.approx(statistics.stdev(payouts))

    def test_edge_by_tc_groups_correctly(self):
        rounds = [
            RoundResult(true_count=1, bet=25.0, payout=25.0),
            RoundResult(true_count=1, bet=25.0, payout=-25.0),
            RoundResult(true_count=3, bet=100.0, payout=100.0),
        ]
        res = aggregate_results(rounds)
        # TC=1: mean payout=0, mean bet=25 → edge=0
        assert res.edge_by_true_count[1] == pytest.approx(0.0)
        # TC=3: mean payout=100, mean bet=100 → edge=1.0
        assert res.edge_by_true_count[3] == pytest.approx(1.0)

    def test_edge_is_ratio_not_percentage(self):
        """edge_by_true_count stores raw ratio (0.01 = 1%), not 1.0."""
        rounds = [RoundResult(2, 100.0, -0.5) for _ in range(100)]
        res = aggregate_results(rounds)
        assert abs(res.edge_by_true_count[2]) < 1.0   # not percent-scaled


# ---------------------------------------------------------------------------
# simulate_session — structural / mechanical tests (fast, small shoe count)
# ---------------------------------------------------------------------------

FAST_SHOES = 50    # enough to check mechanics without statistical rigor

class TestSimulateSessionMechanics:
    def test_returns_list(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, FAST_SHOES, seed=0)
        assert isinstance(rounds, list)

    def test_rounds_are_round_results(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, FAST_SHOES, seed=0)
        assert all(isinstance(r, RoundResult) for r in rounds)

    def test_produces_rounds(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, FAST_SHOES, seed=0)
        assert len(rounds) > 0

    def test_round_counts_scale_with_num_shoes(self):
        r10  = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 10,  seed=7)
        r100 = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 100, seed=7)
        assert len(r100) > len(r10)

    def test_bet_matches_spread(self):
        """Every bet in the result must be a value from the spread."""
        spread = {-100: 25.0, 3: 100.0}
        rounds = simulate_session(RULES, spread, basic_strategy, FAST_SHOES, seed=1)
        allowed_bets = set(spread.values()) - {0.0}
        for r in rounds:
            assert r.bet in allowed_bets, f"unexpected bet {r.bet}"

    def test_no_zero_bet_rounds(self):
        """Wonged-out rounds (bet=0) must not appear in results."""
        rounds = simulate_session(RULES, COUNTING_SPREAD, basic_strategy,
                                  FAST_SHOES, seed=2)
        assert all(r.bet > 0 for r in rounds)

    def test_payout_is_float(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, FAST_SHOES, seed=3)
        assert all(isinstance(r.payout, float) for r in rounds)

    def test_true_count_is_integer(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, FAST_SHOES, seed=4)
        assert all(isinstance(r.true_count, int) for r in rounds)

    def test_seed_gives_reproducible_results(self):
        r1 = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 20, seed=99)
        r2 = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 20, seed=99)
        assert r1 == r2

    def test_different_seeds_give_different_results(self):
        r1 = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 20, seed=1)
        r2 = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 20, seed=2)
        assert r1 != r2

    def test_no_seed_runs_without_error(self):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 5)
        assert len(rounds) > 0


# ---------------------------------------------------------------------------
# Wong-out mechanics
# ---------------------------------------------------------------------------

class TestWongOut:
    def test_all_bets_wong_out_returns_empty(self):
        """If every TC maps to bet=0, no rounds should be played."""
        zero_spread = {-100: 0.0}
        rounds = simulate_session(RULES, zero_spread, basic_strategy, 10, seed=0)
        assert rounds == []

    def test_wonging_reduces_round_count(self):
        """A spread that sits out negative counts plays fewer rounds than flat."""
        flat_rounds    = simulate_session(RULES, FLAT_SPREAD,    basic_strategy, 100, seed=5)
        wonging_rounds = simulate_session(RULES, COUNTING_SPREAD, basic_strategy, 100, seed=5)
        # Wonging skips low-count rounds → fewer total rounds
        assert len(wonging_rounds) < len(flat_rounds)

    def test_wonging_rounds_have_higher_average_tc(self):
        """Wonging filters out low-TC rounds, so mean TC should be higher."""
        flat    = simulate_session(RULES, FLAT_SPREAD,    basic_strategy, 200, seed=6)
        wonging = simulate_session(RULES, COUNTING_SPREAD, basic_strategy, 200, seed=6)
        if wonging:
            mean_flat    = statistics.mean(r.true_count for r in flat)
            mean_wonging = statistics.mean(r.true_count for r in wonging)
            assert mean_wonging > mean_flat

    def test_wonging_only_plays_when_positive_count(self):
        """With wong_in at TC=1, all played rounds should have TC ≥ 1."""
        spread = {1: 25.0}      # no key ≤ 0 → wong out everything below 1
        rounds = simulate_session(RULES, spread, basic_strategy, 50, seed=8)
        for r in rounds:
            assert r.true_count >= 1, f"played round at TC={r.true_count}"


# ---------------------------------------------------------------------------
# Counting deviations wired correctly
# ---------------------------------------------------------------------------

class TestDeviations:
    def test_session_with_deviations_runs_without_error(self):
        """Smoke test: deviations layer does not crash the simulation."""
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy, 30, seed=10)
        assert len(rounds) > 0

    def test_custom_strategy_fn_is_called(self):
        """Passing a custom base strategy should work (callable contract)."""
        calls = {"n": 0}

        def counting_strategy(hand, upcard, rules):
            calls["n"] += 1
            return basic_strategy(hand, upcard, rules)

        simulate_session(RULES, FLAT_SPREAD, counting_strategy, 5, seed=11)
        assert calls["n"] > 0


# ---------------------------------------------------------------------------
# Statistical validation  (larger shoe count — runs in a few seconds)
# ---------------------------------------------------------------------------

# Number of shoes used for statistical tests.  5 000 six-deck shoes at 75%
# penetration ≈ 5000 × ~40 hands = ~200 000 hands, giving a standard error
# on the edge of roughly ±0.26 % (SD≈1.15 units, SE = 1.15/√200000 ≈ 0.0026).
STAT_SHOES = 5_000
STAT_SEED  = 42


class TestHouseEdge:
    """
    6-deck H17 DAS basic strategy house edge is ~0.46 %.
    With 200 000 hands the SE is ≈ 0.26 %, so at 3 σ we allow ±0.78 %.
    We use a generous tolerance of ±1.2 % to stay reliable across seeds.
    """

    EDGE_TOLERANCE = 0.012    # 1.2 percentage points (as a fraction)

    def _run(self, spread=FLAT_SPREAD, shoes=STAT_SHOES, seed=STAT_SEED):
        rounds = simulate_session(RULES, spread, basic_strategy, shoes, seed=seed)
        return aggregate_results(rounds)

    def test_flat_bet_ev_is_negative(self):
        """Basic strategy has a negative EV (house edge)."""
        res = self._run()
        assert res.ev_per_hand < 0, f"EV was positive: {res.ev_per_hand:.4f}"

    def test_flat_bet_overall_edge_near_minus_half_percent(self):
        """Overall edge should be near −0.46 %, within ±1.2 %."""
        res = self._run()
        # edge = total_won / total_wagered
        overall_edge = res.total_won / res.total_wagered
        assert abs(overall_edge - (-0.0046)) < self.EDGE_TOLERANCE, (
            f"Overall edge {overall_edge:.4%} outside ±{self.EDGE_TOLERANCE:.1%} "
            f"window around −0.46 %"
        )

    def test_std_dev_per_hand_reasonable(self):
        """SD per $25-unit hand should be in [20, 40] for typical 6-deck play."""
        res = self._run()
        assert 20.0 < res.std_dev_per_hand < 40.0, (
            f"std_dev_per_hand = {res.std_dev_per_hand:.2f}"
        )

    def test_total_hands_reasonable_for_shoe_count(self):
        """6-deck 75% pen shoe has ~40 rounds.  Allow 20–70 per shoe."""
        res = self._run()
        hands_per_shoe = res.total_hands / STAT_SHOES
        assert 20 < hands_per_shoe < 70, (
            f"hands_per_shoe = {hands_per_shoe:.1f}"
        )


class TestHighCountEdge:
    """
    At TC ≥ 3 the Hi-Lo count gives the player roughly +1 % per true-count
    unit above the neutral point, so combined edge at TC ≥ 3 should be > 0.
    """

    def _high_tc_rounds(self, seed=STAT_SEED):
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy,
                                  STAT_SHOES, seed=seed)
        return [r for r in rounds if r.true_count >= 3]

    def test_positive_edge_at_high_counts(self):
        """Mean payout / bet should be positive for TC ≥ 3 rounds."""
        high = self._high_tc_rounds()
        assert len(high) > 500, f"too few high-TC rounds to test: {len(high)}"

        mean_payout = statistics.mean(r.payout for r in high)
        mean_bet    = statistics.mean(r.bet    for r in high)
        edge = mean_payout / mean_bet
        assert edge > 0, (
            f"Expected positive edge at TC≥3, got {edge:.4%} "
            f"({len(high)} rounds)"
        )

    def test_negative_edge_at_low_counts(self):
        """Mean payout / bet should be negative for TC ≤ −1 rounds."""
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy,
                                  STAT_SHOES, seed=STAT_SEED)
        low = [r for r in rounds if r.true_count <= -1]
        assert len(low) > 500, f"too few low-TC rounds to test: {len(low)}"

        mean_payout = statistics.mean(r.payout for r in low)
        mean_bet    = statistics.mean(r.bet    for r in low)
        edge = mean_payout / mean_bet
        assert edge < 0, (
            f"Expected negative edge at TC≤−1, got {edge:.4%} "
            f"({len(low)} rounds)"
        )

    def test_edge_increases_with_true_count(self):
        """
        Mean edge at TC ≥ 3 should exceed mean edge at TC = 1.
        Use 20 000 shoes so TC=3+ buckets have enough samples to be stable.
        Each TC unit adds ≈ +0.5% edge; TC=3 vs TC=1 ≈ +1% expected gap.
        """
        rounds = simulate_session(RULES, FLAT_SPREAD, basic_strategy,
                                  20_000, seed=STAT_SEED)
        res = aggregate_results(rounds)

        if 1 not in res.edge_by_true_count:
            pytest.skip("insufficient data at TC=1")

        # Aggregate all high-count rounds (TC >= 3) for a stable estimate.
        high_tc_rounds = [r for r in rounds if r.true_count >= 3]
        if len(high_tc_rounds) < 50:
            pytest.skip("too few high-TC rounds to measure edge reliably")

        edge_tc1 = res.edge_by_true_count[1]
        total_payout = sum(r.payout for r in high_tc_rounds)
        total_bet    = sum(r.bet    for r in high_tc_rounds)
        edge_high    = total_payout / total_bet

        assert edge_high > edge_tc1, (
            f"Expected edge(TC≥3) > edge(TC=1): "
            f"{edge_high:.4%} vs {edge_tc1:.4%}"
        )


class TestCountingSpreadImproveEV:
    """
    A 1-8 counting spread should yield a higher EV per 100 hands than
    flat-betting, because the player bets more when they have an edge.
    """

    def test_spread_ev_higher_than_flat_ev(self):
        flat    = simulate_session(RULES, FLAT_SPREAD,    basic_strategy,
                                   STAT_SHOES, seed=STAT_SEED)
        wonging = simulate_session(RULES, COUNTING_SPREAD, basic_strategy,
                                   STAT_SHOES, seed=STAT_SEED)

        flat_res    = aggregate_results(flat)
        wonging_res = aggregate_results(wonging)

        flat_edge    = flat_res.total_won    / flat_res.total_wagered
        wonging_edge = wonging_res.total_won / wonging_res.total_wagered

        assert wonging_edge > flat_edge, (
            f"Counting spread edge {wonging_edge:.4%} not better than "
            f"flat-bet edge {flat_edge:.4%}"
        )
