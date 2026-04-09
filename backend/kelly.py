"""
kelly.py — Kelly Criterion bet sizing for blackjack counting.

The Kelly Criterion determines the fraction of bankroll to wager on each bet
to maximise the long-run geometric growth rate while avoiding ruin.

For blackjack the relevant formula is:

    f* = edge / variance

where *edge* is the per-hand expected value expressed as a fraction of the
unit bet and *variance* is the per-hand variance expressed in units².

Public surface:
    kelly_fraction          — full Kelly fraction f*
    fractional_kelly        — scaled Kelly (e.g. half-Kelly)
    kelly_bet               — dollar bet from bankroll × Kelly fraction
    optimal_bet_spread      — compute optimal bets per true-count bucket
    BetSuggestion           — NamedTuple returned by optimal_bet_spread
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Core Kelly formulas
# ---------------------------------------------------------------------------

def kelly_fraction(edge: float, variance: float) -> float:
    """Return the full Kelly fraction f* = edge / variance.

    The Kelly fraction is the fraction of bankroll to wager on each hand to
    maximise the expected logarithmic growth rate (equivalent to maximising
    long-run wealth).

    Args:
        edge:     Player's per-hand expected value expressed as a fraction of
                  the *unit* bet (e.g., 0.005 for a 0.5% edge).  Can be
                  negative (house edge).
        variance: Per-hand variance expressed in *units*² (dimensionless).
                  Typical blackjack variance ≈ 1.32 (i.e., SD ≈ 1.15 units).

    Returns:
        Kelly fraction f* in [−∞, +∞].  A negative value means the Kelly
        criterion recommends not betting (the house has the edge).  Returns
        0.0 when variance ≤ 0.

    Examples:
        >>> kelly_fraction(0.01, 1.32)   # 1% edge, typical BJ variance
        0.007575...
        >>> kelly_fraction(-0.005, 1.32) # house edge → don't bet
        -0.003787...
    """
    if variance <= 0:
        return 0.0
    return edge / variance


def fractional_kelly(
    edge: float,
    variance: float,
    fraction: float = 0.5,
) -> float:
    """Return a fractional Kelly bet size.

    Fractional Kelly reduces bet size by a constant multiplier to trade some
    EV growth for substantially lower variance and drawdown risk.  Half-Kelly
    (fraction=0.5) cuts variance in half while retaining ~75% of EV growth.

    Args:
        edge:     Player's per-hand expected value as a fraction of unit bet.
        variance: Per-hand variance in units².
        fraction: Multiplier applied to full Kelly (0 < fraction ≤ 1).
                  Common values: 0.5 (half), 0.25 (quarter), 0.33 (third).

    Returns:
        Fractional Kelly fraction f = fraction × (edge / variance).
        Returns 0.0 when variance ≤ 0 or fraction ≤ 0.

    Raises:
        ValueError: If ``fraction`` is not in (0, 1].
    """
    if fraction <= 0 or fraction > 1:
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")
    return fraction * kelly_fraction(edge, variance)


def kelly_bet(
    bankroll: float,
    edge: float,
    variance: float,
    fraction: float = 1.0,
    min_bet: float = 0.0,
    max_bet: Optional[float] = None,
) -> float:
    """Return the dollar bet recommended by (fractional) Kelly.

    Converts the Kelly fraction to a dollar amount:
        bet = bankroll × fractional_kelly(edge, variance, fraction)

    Bets are clamped to [min_bet, max_bet].  If the Kelly fraction is
    negative the bet is 0 (don't play).

    Args:
        bankroll: Current bankroll in dollars.
        edge:     Per-hand edge as a fraction of unit bet.
        variance: Per-hand variance in units².
        fraction: Kelly fraction multiplier (default 1.0 = full Kelly).
        min_bet:  Minimum allowed bet in dollars (floor).
        max_bet:  Maximum allowed bet in dollars (ceiling), or None.

    Returns:
        Dollar bet amount ≥ 0.
    """
    fk = fractional_kelly(edge, variance, fraction) if fraction < 1.0 \
        else kelly_fraction(edge, variance)
    if fk <= 0 or bankroll <= 0:
        return 0.0
    bet = bankroll * fk
    bet = max(bet, min_bet)
    if max_bet is not None:
        bet = min(bet, max_bet)
    return bet


# ---------------------------------------------------------------------------
# Optimal bet spread
# ---------------------------------------------------------------------------

class BetSuggestion(NamedTuple):
    """Optimal bet for a single true-count bucket.

    Attributes:
        true_count:    Integer true count.
        edge:          Player edge at this TC (fraction of unit bet).
        kelly_bet:     Full Kelly dollar bet.
        half_kelly_bet: Half-Kelly dollar bet.
        frequency:     Fraction of rounds played at this TC.
        ev_contribution: EV per 100 hands at this TC (= edge × bet × freq × 100).
    """
    true_count: int
    edge: float
    kelly_bet: float
    half_kelly_bet: float
    frequency: float
    ev_contribution: float


def optimal_bet_spread(
    bankroll: float,
    tc_edges: Dict[int, float],
    tc_frequencies: Dict[int, float],
    kelly_frac: float = 0.5,
    variance_per_unit: float = 1.32,
    min_bet: float = 0.0,
    max_bet: Optional[float] = None,
) -> List[BetSuggestion]:
    """Compute optimal Kelly-sized bets for each true-count bucket.

    Given the player's edge at each integer true count and the frequency with
    which each count is encountered, returns the Kelly-optimal dollar bet for
    each TC and a per-TC EV contribution.

    Only true counts with a positive player edge receive a non-zero bet.
    Negative-edge buckets return a bet of 0 (wong out / sit out).

    The ``edge`` values in ``tc_edges`` should be expressed as a fraction of
    the *average bet* at that count (i.e., mean(payout) / mean(bet) from
    :attr:`~backend.simulator.SimulationResult.edge_by_true_count`).

    Args:
        bankroll:         Current bankroll in dollars.
        tc_edges:         ``{true_count: edge}`` mapping.  Edge is a fraction
                          of bet (e.g., 0.01 = 1% player advantage).
        tc_frequencies:   ``{true_count: frequency}`` from
                          :func:`~backend.counting.true_count_frequencies`.
                          Values should sum to ~1.0.
        kelly_frac:       Kelly multiplier (default 0.5 = half-Kelly).
        variance_per_unit: Per-hand variance in units² (default 1.32,
                           typical for multi-deck blackjack with basic
                           strategy; higher if doubling/splitting more).
        min_bet:          Minimum dollar bet (table minimum).
        max_bet:          Maximum dollar bet (table maximum), or None.

    Returns:
        List of :class:`BetSuggestion`, sorted ascending by true count.
        Only true counts present in both ``tc_edges`` and ``tc_frequencies``
        are included.
    """
    results: List[BetSuggestion] = []

    all_tcs = sorted(set(tc_edges) & set(tc_frequencies))
    for tc in all_tcs:
        edge = tc_edges[tc]
        freq = tc_frequencies.get(tc, 0.0)

        # Full and half-Kelly bets.
        fk_bet   = kelly_bet(bankroll, edge, variance_per_unit, fraction=1.0,
                             min_bet=min_bet, max_bet=max_bet)
        half_bet = kelly_bet(bankroll, edge, variance_per_unit,
                             fraction=kelly_frac,
                             min_bet=min_bet, max_bet=max_bet)

        # EV contribution per 100 hands = edge × applied_bet × frequency × 100.
        # Use the selected fractional-Kelly bet as the applied bet.
        ev_contrib = edge * half_bet * freq * 100.0

        results.append(BetSuggestion(
            true_count=tc,
            edge=edge,
            kelly_bet=fk_bet,
            half_kelly_bet=half_bet,
            frequency=freq,
            ev_contribution=ev_contrib,
        ))

    return results


# ---------------------------------------------------------------------------
# Utility: edge from TC using the rule-of-thumb +0.5%/TC
# ---------------------------------------------------------------------------

# Standard Hi-Lo approximation: each true-count unit adds ~0.5% player edge
# on top of the base game edge (itself a function of rules).
_TC_EDGE_PER_UNIT: float = 0.005


def approximate_edge_at_tc(
    true_count: int,
    base_edge: float = -0.005,
) -> float:
    """Approximate player edge at a given true count.

    Uses the standard Hi-Lo rule of thumb: each integer true-count unit adds
    approximately 0.5% to the player's edge over the base game edge.

    This is a quick estimate — use simulation-derived edges from
    :attr:`~backend.simulator.SimulationResult.edge_by_true_count` for
    accurate results.

    Args:
        true_count: Integer Hi-Lo true count.
        base_edge:  House edge at TC=0 for the specific rule set (e.g.,
                    −0.005 = −0.5% for a typical 6-deck H17 game).

    Returns:
        Estimated player edge as a fraction of bet.  Positive = player
        advantage, negative = house advantage.
    """
    return base_edge + true_count * _TC_EDGE_PER_UNIT
