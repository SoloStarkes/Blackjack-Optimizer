"""
comparison.py — Side-by-side comparison of three bet-sizing strategies.

Given the same game rules and bankroll, compares:

    A) Flat bet      — fixed wager regardless of true count
    B) Full Kelly    — Kelly-optimal bet per true-count bucket
    C) Half Kelly    — 0.5 × full Kelly per true-count bucket

Returns EV/hr, standard deviation, Risk of Ruin, and N-0 for each strategy,
along with a summary table.

Public surface:
    StrategyResult       — dataclass for one strategy's metrics
    ComparisonResult     — dataclass holding all three results
    compare_strategies   — main entry point
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from backend.counting import true_count_frequencies
from backend.engine import GameRules
from backend.ev_calculator import (
    SessionMetrics,
    calculate_metrics,
    ror_analytical,
    n0_hands as _n0_hands,
    n0_hours as _n0_hours,
    score as _score,
)
from backend.kelly import approximate_edge_at_tc, kelly_bet, optimal_bet_spread
from backend.simulator import aggregate_results, simulate_session
from backend.strategy import basic_strategy


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class StrategyResult:
    """Metrics for a single bet-sizing strategy.

    Attributes:
        name:              Human-readable strategy label.
        bet_spread:        TC → dollar bet mapping used in simulation.
        ev_per_hour:       Expected net win per hour (dollars).
        std_dev_per_hour:  Per-hour standard deviation (dollars).
        risk_of_ruin:      Analytical probability of losing entire bankroll.
        n0_hours:          Hours until EV exceeds one SD; float('inf') if EV ≤ 0.
        score:             SCORE desirability index.
        ev_per_hand:       Mean net payout per played hand.
        std_dev_per_hand:  Per-hand standard deviation.
        total_hands:       Total hands simulated.
    """
    name: str
    bet_spread: Dict[int, float]
    ev_per_hour: float
    std_dev_per_hour: float
    risk_of_ruin: float
    n0_hours: float
    score: float
    ev_per_hand: float
    std_dev_per_hand: float
    total_hands: int


@dataclass
class ComparisonResult:
    """Side-by-side comparison of three bet-sizing strategies.

    Attributes:
        flat_bet:    Metrics for the fixed flat-bet strategy.
        full_kelly:  Metrics for the full-Kelly bet-spread strategy.
        half_kelly:  Metrics for the half-Kelly bet-spread strategy.
        rules:       The GameRules shared by all three runs.
        bankroll:    Starting bankroll used for RoR / N-0 calculations.
        rounds_per_hour: Hands per hour assumption.
    """
    flat_bet: StrategyResult
    full_kelly: StrategyResult
    half_kelly: StrategyResult
    rules: GameRules
    bankroll: float
    rounds_per_hour: float


# ---------------------------------------------------------------------------
# Bet-spread builders
# ---------------------------------------------------------------------------

def _flat_bet_spread(flat_amount: float, min_tc: int = 1) -> Dict[int, float]:
    """Return a flat bet spread: bet ``flat_amount`` at TC ≥ ``min_tc``, wong out below.

    Args:
        flat_amount: Constant dollar bet for all counts ≥ min_tc.
        min_tc:      Minimum true count to play (default 1).

    Returns:
        ``{min_tc: flat_amount}`` — step function stays constant above min_tc.
    """
    return {min_tc: flat_amount}


def _kelly_spread(
    bankroll: float,
    tc_edges: Dict[int, float],
    tc_freqs: Dict[int, float],
    kelly_fraction: float,
    variance_per_unit: float = 1.32,
    min_bet: float = 1.0,
    max_bet: Optional[float] = None,
) -> Dict[int, float]:
    """Build a Kelly-sized bet spread from TC-edge estimates.

    Only true counts with a positive player edge receive a non-zero bet.
    Counts with a negative edge receive 0 (wong out).

    Args:
        bankroll:          Starting bankroll in dollars.
        tc_edges:          TC → player edge mapping (fraction of bet).
        tc_freqs:          TC → frequency mapping.
        kelly_fraction:    Fraction of full Kelly to apply (1.0 or 0.5).
        variance_per_unit: Per-hand variance in units² (default 1.32).
        min_bet:           Minimum dollar bet.
        max_bet:           Maximum dollar bet, or None.

    Returns:
        ``{tc: dollar_bet}`` dict suitable for ``simulate_session``.
    """
    suggestions = optimal_bet_spread(
        bankroll=bankroll,
        tc_edges=tc_edges,
        tc_frequencies=tc_freqs,
        kelly_frac=kelly_fraction,
        variance_per_unit=variance_per_unit,
        min_bet=min_bet,
        max_bet=max_bet,
    )

    spread: Dict[int, float] = {}
    for s in suggestions:
        bet = s.half_kelly_bet if kelly_fraction < 1.0 else s.kelly_bet
        spread[s.true_count] = round(bet, 2) if bet > 0 else 0.0

    # Ensure at least one non-zero bet; if none found (all negative TC), fall back to TC+1.
    if all(v == 0 for v in spread.values()):
        spread[1] = min_bet

    return spread


def _build_tc_edges(rules: GameRules, num_shoes: int = 5_000, seed: Optional[int] = None) -> Dict[int, float]:
    """Estimate player edge at each integer true count by simulation.

    Runs a quick simulation with a wide bet spread (bet $1 at every TC)
    to collect edge statistics across all TC buckets, then returns the
    edge-by-TC mapping from the aggregated result.

    Args:
        rules:     Game rules to simulate under.
        num_shoes: Number of shoes (default 5 000 for reasonable accuracy).
        seed:      Optional RNG seed.

    Returns:
        ``{tc: edge}`` mapping for all integer TCs observed in simulation.
    """
    # Bet $1 at all TCs from -6 to +10 (no wonging) to get full edge distribution.
    bet_spread: Dict[int, float] = {tc: 1.0 for tc in range(-6, 11)}
    rounds = simulate_session(rules, bet_spread, basic_strategy, num_shoes=num_shoes, seed=seed)
    if not rounds:
        return {}
    sim = aggregate_results(rounds)
    return sim.edge_by_true_count


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compare_strategies(
    rules: GameRules,
    bankroll: float,
    rounds_per_hour: float = 100.0,
    flat_bet_amount: Optional[float] = None,
    min_tc: int = 1,
    max_bet: Optional[float] = None,
    num_shoes: int = 10_000,
    seed: Optional[int] = None,
) -> ComparisonResult:
    """Compare flat-bet, full-Kelly, and half-Kelly strategies under identical conditions.

    All three strategies are simulated using the same ``rules`` and ``num_shoes``
    for a fair comparison.  The Kelly spreads are built from TC-edge estimates
    derived from a preliminary simulation.

    Strategy A — Flat bet:
        Wagers ``flat_bet_amount`` at every true count ≥ ``min_tc``.
        Wongs out below ``min_tc``.  Default flat amount is bankroll / 400
        (roughly 1/4 Kelly for a typical counting edge).

    Strategy B — Full Kelly:
        Uses ``kelly_bet(bankroll, edge, variance)`` at each TC.
        Wongs out at negative-edge counts.

    Strategy C — Half Kelly:
        Uses ``0.5 × kelly_bet(bankroll, edge, variance)`` at each TC.
        Wongs out at negative-edge counts.

    Args:
        rules:            Game rules (decks, penetration, H17, DAS, etc.).
        bankroll:         Starting bankroll in dollars.
        rounds_per_hour:  Hands per hour assumption for hourly metrics.
        flat_bet_amount:  Dollar amount for the flat-bet strategy.  If None,
                          defaults to ``bankroll / 400``.
        min_tc:           Minimum true count to play for flat-bet strategy.
        max_bet:          Maximum bet cap for Kelly strategies.
        num_shoes:        Shoes to simulate per strategy (default 10 000).
        seed:             Optional RNG seed for reproducibility.

    Returns:
        :class:`ComparisonResult` containing all three strategy results.
    """
    if flat_bet_amount is None:
        flat_bet_amount = bankroll / 400.0
        flat_bet_amount = max(flat_bet_amount, 1.0)

    # ── Step 1: estimate TC → edge from a quick simulation ──────────────────
    edge_seed = (seed + 99999) if seed is not None else None
    tc_edges = _build_tc_edges(rules, num_shoes=max(num_shoes // 2, 3_000), seed=edge_seed)

    # Fall back to approximate edges if simulation produced nothing.
    if not tc_edges:
        tc_edges = {tc: approximate_edge_at_tc(tc) for tc in range(-5, 8)}

    # ── Step 2: estimate TC frequencies ─────────────────────────────────────
    tc_freqs = true_count_frequencies(
        num_decks=rules.decks,
        penetration=rules.penetration,
        num_shoes=max(num_shoes // 4, 2_000),
        seed=(seed + 12345) if seed is not None else None,
    )

    # ── Step 3: build Kelly spreads ──────────────────────────────────────────
    full_kelly_spread = _kelly_spread(
        bankroll, tc_edges, tc_freqs, kelly_fraction=1.0,
        min_bet=1.0, max_bet=max_bet,
    )
    half_kelly_spread = _kelly_spread(
        bankroll, tc_edges, tc_freqs, kelly_fraction=0.5,
        min_bet=1.0, max_bet=max_bet,
    )

    # ── Step 4: build flat bet spread ────────────────────────────────────────
    flat_spread = _flat_bet_spread(flat_bet_amount, min_tc=min_tc)

    # ── Step 5: simulate all three strategies ────────────────────────────────
    seeds = [
        seed,
        (seed + 1) if seed is not None else None,
        (seed + 2) if seed is not None else None,
    ]
    spreads = [flat_spread, full_kelly_spread, half_kelly_spread]
    names   = ["Flat Bet", "Full Kelly", "Half Kelly"]

    results: List[StrategyResult] = []
    for name, spread, s in zip(names, spreads, seeds):
        rounds = simulate_session(rules, spread, basic_strategy, num_shoes=num_shoes, seed=s)
        if not rounds:
            results.append(StrategyResult(
                name=name,
                bet_spread=spread,
                ev_per_hour=0.0,
                std_dev_per_hour=0.0,
                risk_of_ruin=1.0,
                n0_hours=float("inf"),
                score=0.0,
                ev_per_hand=0.0,
                std_dev_per_hand=0.0,
                total_hands=0,
            ))
            continue

        sim     = aggregate_results(rounds)
        metrics = calculate_metrics(sim, bankroll, rounds_per_hour)

        n0_h = metrics.n0_hours
        if not math.isfinite(n0_h):
            n0_h = float("inf")

        results.append(StrategyResult(
            name=name,
            bet_spread=spread,
            ev_per_hour=metrics.ev_per_hour,
            std_dev_per_hour=metrics.std_dev_per_hour,
            risk_of_ruin=metrics.ror_analytical,
            n0_hours=n0_h,
            score=metrics.score,
            ev_per_hand=sim.ev_per_hand,
            std_dev_per_hand=sim.std_dev_per_hand,
            total_hands=sim.total_hands,
        ))

    return ComparisonResult(
        flat_bet=results[0],
        full_kelly=results[1],
        half_kelly=results[2],
        rules=rules,
        bankroll=bankroll,
        rounds_per_hour=rounds_per_hour,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_comparison_table(result: ComparisonResult) -> str:
    """Render a ComparisonResult as a plain-text table.

    Args:
        result: Output of :func:`compare_strategies`.

    Returns:
        Multi-line string suitable for printing or logging.
    """
    rows = [result.flat_bet, result.full_kelly, result.half_kelly]
    lines: List[str] = []

    lines.append("=" * 72)
    lines.append("  BET-SIZING STRATEGY COMPARISON")
    lines.append(
        f"  Bankroll: ${result.bankroll:,.0f}   "
        f"RPH: {result.rounds_per_hour:.0f}   "
        f"Decks: {result.rules.decks}   "
        f"Pen: {result.rules.penetration:.0%}"
    )
    lines.append("=" * 72)
    lines.append(
        f"  {'Strategy':<14} {'EV/hr':>10} {'SD/hr':>10} {'RoR':>8} "
        f"{'N-0 hrs':>10} {'SCORE':>10}"
    )
    lines.append("-" * 72)

    for r in rows:
        n0_str = f"{r.n0_hours:.1f}" if math.isfinite(r.n0_hours) else "∞"
        lines.append(
            f"  {r.name:<14} "
            f"${r.ev_per_hour:>9,.2f} "
            f"${r.std_dev_per_hour:>9,.2f} "
            f"{r.risk_of_ruin:>7.2%} "
            f"{n0_str:>10} "
            f"{r.score:>10.6f}"
        )

    lines.append("=" * 72)
    return "\n".join(lines)
