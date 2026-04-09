"""
ruin_sim.py — Empirical ruin probability simulator.

Runs many independent bankroll trajectories using a Gaussian random walk
and computes the fraction of paths that hit $0 ("ruin").  Compares this
empirical estimate to the analytical Gambler's Ruin formula from
ev_calculator.py.

This module is a standalone research tool — it does not depend on the
full blackjack simulator, only on the per-hand EV and SD extracted from
a simulation result.

Public surface:
    RuinSimResult    — dataclass holding simulation output and comparison
    simulate_ruin    — run N bankroll trajectories, return RuinSimResult
    compare_ror      — shortcut: simulate + compare in one call
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from backend.ev_calculator import ror_analytical as _ror_analytical


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class RuinSimResult:
    """Output of a ruin-probability simulation.

    Attributes:
        num_trajectories:    Number of simulated bankroll paths.
        max_hands:           Maximum hands per trajectory.
        ev_per_hand:         Mean net payout per hand used in simulation.
        std_dev_per_hand:    Per-hand standard deviation used.
        bankroll:            Starting bankroll.
        empirical_ror:       Fraction of trajectories that hit $0.
        analytical_ror:      Gambler's Ruin formula result.
        absolute_error:      abs(empirical_ror − analytical_ror).
        relative_error:      abs_error / analytical_ror (or inf if analytical = 0).
        ruin_trajectories:   Number of trajectories that ended in ruin.
        median_final_bankroll: Median bankroll at end of simulation (across non-ruined paths).
        mean_final_bankroll: Mean bankroll across all paths (ruined = 0).
        bankroll_percentiles: Dict of percentile → final bankroll (5/25/50/75/95).
    """
    num_trajectories: int
    max_hands: int
    ev_per_hand: float
    std_dev_per_hand: float
    bankroll: float
    empirical_ror: float
    analytical_ror: float
    absolute_error: float
    relative_error: float
    ruin_trajectories: int
    median_final_bankroll: float
    mean_final_bankroll: float
    bankroll_percentiles: dict


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 10_000   # hands per vectorised chunk (memory-efficient)


def simulate_ruin(
    ev_per_hand: float,
    std_dev_per_hand: float,
    bankroll: float,
    num_trajectories: int = 10_000,
    max_hands: int = 1_000_000,
    seed: Optional[int] = None,
) -> RuinSimResult:
    """Simulate ``num_trajectories`` independent bankroll paths and compute RoR.

    Each trajectory is a Gaussian random walk:
        balance_t+1 = balance_t + N(ev_per_hand, std_dev_per_hand)

    The trajectory ends (ruin) when ``balance_t ≤ 0`` or ``max_hands`` is
    reached.  Memory is bounded: paths are processed in chunks of
    ``_CHUNK_SIZE`` hands, so peak RAM is
    O(num_trajectories × _CHUNK_SIZE × 8 bytes) ≈ 800 MB for 10 k paths.

    Args:
        ev_per_hand:       Mean net payout per hand (dollars).  Positive = player
                           edge; negative = house edge.
        std_dev_per_hand:  Per-hand standard deviation (dollars).
        bankroll:          Starting bankroll (dollars).
        num_trajectories:  Number of independent paths (default 10 000).
        max_hands:         Max hands per trajectory before declaring survival
                           (default 1 000 000 ≈ 10 000 hours at 100 rph).
        seed:              Optional NumPy RNG seed for reproducibility.

    Returns:
        :class:`RuinSimResult` with empirical and analytical RoR, error metrics,
        and final-bankroll statistics.

    Raises:
        ValueError: If ``bankroll ≤ 0`` or ``std_dev_per_hand ≤ 0``.
    """
    if bankroll <= 0:
        raise ValueError(f"bankroll must be positive, got {bankroll}")
    if std_dev_per_hand <= 0:
        raise ValueError(f"std_dev_per_hand must be positive, got {std_dev_per_hand}")
    if num_trajectories < 1:
        raise ValueError(f"num_trajectories must be ≥ 1, got {num_trajectories}")

    rng = np.random.default_rng(seed)

    # Track running balance and ruin status for all paths simultaneously.
    running = np.full(num_trajectories, float(bankroll))
    ruined  = np.zeros(num_trajectories, dtype=bool)

    hands_done = 0
    while hands_done < max_hands:
        chunk = min(_CHUNK_SIZE, max_hands - hands_done)

        # Draw outcomes for all still-active paths.
        outcomes = rng.normal(
            loc=ev_per_hand,
            scale=std_dev_per_hand,
            size=(num_trajectories, chunk),
        )
        # Zero out outcomes for already-ruined paths.
        outcomes[ruined] = 0.0

        # Cumulative balance within this chunk.
        cum = np.cumsum(outcomes, axis=1)
        chunk_bal = running[:, None] + cum   # shape: (num_trajectories, chunk)

        # Detect newly ruined paths (any step where balance ≤ 0).
        min_in_chunk = chunk_bal.min(axis=1)
        newly_ruined = (~ruined) & (min_in_chunk <= 0)

        # For newly ruined paths, pin balance at 0 from the first ruin point.
        for p in np.where(newly_ruined)[0]:
            first = int(np.argmax(chunk_bal[p] <= 0))
            chunk_bal[p, first:] = 0.0

        ruined |= newly_ruined
        running = chunk_bal[:, -1].copy()
        running[ruined] = 0.0

        hands_done += chunk

        # Early exit if all paths ruined.
        if ruined.all():
            break

    # ── Analytical RoR ──────────────────────────────────────────────────────
    variance_per_hand = std_dev_per_hand ** 2
    analytical = _ror_analytical(ev_per_hand, variance_per_hand, bankroll)

    # ── Empirical stats ─────────────────────────────────────────────────────
    ruin_count     = int(ruined.sum())
    empirical_ror  = ruin_count / num_trajectories

    abs_err = abs(empirical_ror - analytical)
    rel_err = abs_err / analytical if analytical > 0 else float("inf")

    # Final balances (ruined = 0).
    final = running.copy()

    surviving = final[~ruined]
    median_final = float(np.median(surviving)) if len(surviving) > 0 else 0.0
    mean_final   = float(np.mean(final))

    pct_labels = [5, 25, 50, 75, 95]
    percentiles = {p: float(np.percentile(final, p)) for p in pct_labels}

    return RuinSimResult(
        num_trajectories=num_trajectories,
        max_hands=max_hands,
        ev_per_hand=ev_per_hand,
        std_dev_per_hand=std_dev_per_hand,
        bankroll=bankroll,
        empirical_ror=empirical_ror,
        analytical_ror=analytical,
        absolute_error=abs_err,
        relative_error=rel_err,
        ruin_trajectories=ruin_count,
        median_final_bankroll=median_final,
        mean_final_bankroll=mean_final,
        bankroll_percentiles=percentiles,
    )


# ---------------------------------------------------------------------------
# Convenience: compare_ror
# ---------------------------------------------------------------------------

def compare_ror(
    ev_per_hand: float,
    std_dev_per_hand: float,
    bankroll: float,
    num_trajectories: int = 10_000,
    max_hands: int = 1_000_000,
    seed: Optional[int] = None,
) -> RuinSimResult:
    """Shortcut: simulate ruin and return a fully-populated RuinSimResult.

    Identical to :func:`simulate_ruin` — provided for a more descriptive
    call site when the intent is purely to compare RoR estimates.

    Args:
        ev_per_hand:       Mean net payout per hand.
        std_dev_per_hand:  Per-hand standard deviation.
        bankroll:          Starting bankroll.
        num_trajectories:  Number of simulated paths.
        max_hands:         Max hands before declaring survival.
        seed:              Optional RNG seed.

    Returns:
        :class:`RuinSimResult`.
    """
    return simulate_ruin(
        ev_per_hand=ev_per_hand,
        std_dev_per_hand=std_dev_per_hand,
        bankroll=bankroll,
        num_trajectories=num_trajectories,
        max_hands=max_hands,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_ruin_report(result: RuinSimResult) -> str:
    """Render a RuinSimResult as a plain-text report.

    Args:
        result: Output of :func:`simulate_ruin` or :func:`compare_ror`.

    Returns:
        Multi-line string suitable for printing or logging.
    """
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("  RUIN PROBABILITY SIMULATION")
    lines.append("=" * 64)
    lines.append(f"  Bankroll           : ${result.bankroll:>12,.2f}")
    lines.append(f"  EV / hand          : ${result.ev_per_hand:>12.4f}")
    lines.append(f"  SD / hand          : ${result.std_dev_per_hand:>12.4f}")
    lines.append(f"  Trajectories       : {result.num_trajectories:>12,}")
    lines.append(f"  Max hands          : {result.max_hands:>12,}")
    lines.append("")
    lines.append(f"  Empirical RoR      : {result.empirical_ror:>11.4%}")
    lines.append(f"  Analytical RoR     : {result.analytical_ror:>11.4%}")
    lines.append(f"  Absolute error     : {result.absolute_error:>11.4%}")

    if math.isfinite(result.relative_error):
        lines.append(f"  Relative error     : {result.relative_error:>11.2%}")
    else:
        lines.append(f"  Relative error     : {'N/A (analytical=0)':>11}")

    lines.append("")
    lines.append(f"  Ruined paths       : {result.ruin_trajectories:>12,}")
    lines.append(f"  Mean final balance : ${result.mean_final_bankroll:>12,.2f}")
    lines.append(f"  Median final bal.  : ${result.median_final_bankroll:>12,.2f}")
    lines.append("")
    lines.append("  Final bankroll percentiles:")
    for p, val in result.bankroll_percentiles.items():
        lines.append(f"    P{p:<3} : ${val:>12,.2f}")
    lines.append("=" * 64)
    return "\n".join(lines)
