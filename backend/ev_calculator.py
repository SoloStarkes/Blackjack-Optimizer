"""
ev_calculator.py — Post-simulation metrics: EV/hr, SD/hr, Risk of Ruin, N-0, SCORE.

Consumes a :class:`~backend.simulator.SimulationResult` (or raw round list) and
a few session parameters to produce all the key practitioner metrics.

Public surface:
    SessionMetrics        — dataclass of all computed metrics
    calculate_metrics     — main entry point; produces SessionMetrics
    ror_analytical        — standalone Risk of Ruin formula
    ror_monte_carlo       — Monte Carlo RoR estimator (optional, slower)
    n0_hands              — N-0 in hands
    n0_hours              — N-0 in hours
    score                 — Sim-SCORE / desirability index
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from backend.simulator import RoundResult, SimulationResult


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SessionMetrics:
    """All computed session metrics from a simulation result.

    Attributes:
        ev_per_hand:          Mean net payout per played hand (dollars).
        ev_per_hour:          Hourly EV = ev_per_hand × rounds_per_hour.
        std_dev_per_hand:     Per-hand standard deviation (dollars).
        std_dev_per_hour:     Hourly SD = std_dev_per_hand × sqrt(rounds_per_hour).
        variance_per_hand:    std_dev_per_hand².
        ror_analytical:       Risk of Ruin using the Gambler's Ruin formula.
        ror_monte_carlo:      Risk of Ruin from MC simulation, or None if not requested.
        n0_hands:             N-0 in hands (SD/EV)².
        n0_hours:             N-0 in hours = n0_hands / rounds_per_hour.
        score:                SCORE = EV²/variance × (hours in N-0); higher is better.
    """

    ev_per_hand: float
    ev_per_hour: float
    std_dev_per_hand: float
    std_dev_per_hour: float
    variance_per_hand: float
    ror_analytical: float
    ror_monte_carlo: Optional[float]
    n0_hands: float
    n0_hours: float
    score: float


# ---------------------------------------------------------------------------
# Standalone formula helpers
# ---------------------------------------------------------------------------

def ror_analytical(
    ev_per_hand: float,
    variance_per_hand: float,
    bankroll: float,
) -> float:
    """Compute Risk of Ruin using the Gambler's Ruin approximation.

    Formula:
        RoR = exp(−2 × ev_per_hand × bankroll / variance_per_hand)

    This is the closed-form solution for a random walk with a fixed positive
    drift (ev_per_hand) and variance (variance_per_hand).  It gives the
    probability that a player starting with ``bankroll`` dollars will be ruined
    (reach $0) before winning an infinite amount.

    A negative EV implies certain ruin; returns 1.0 in that case.
    EV of exactly 0 is also treated as certain ruin.

    Args:
        ev_per_hand:      Mean net payout per hand (dollars).  Must be > 0 for
                          a finite RoR.
        variance_per_hand: Variance of payout per hand (dollars²).
        bankroll:         Starting capital in dollars.

    Returns:
        Probability of ruin in [0, 1].
    """
    if ev_per_hand <= 0 or variance_per_hand <= 0 or bankroll <= 0:
        return 1.0
    exponent = -2.0 * ev_per_hand * bankroll / variance_per_hand
    return math.exp(exponent)


def ror_monte_carlo(
    ev_per_hand: float,
    std_dev_per_hand: float,
    bankroll: float,
    num_trials: int = 50_000,
    max_hands: int = 1_000_000,
    seed: Optional[int] = None,
) -> float:
    """Estimate Risk of Ruin via Monte Carlo random walk simulation.

    Simulates ``num_trials`` independent random walks, each modelled as
    normally distributed per-hand outcomes with mean ``ev_per_hand`` and
    standard deviation ``std_dev_per_hand``.  The bankroll is tracked; ruin
    occurs when it hits zero or below.

    This is slower than :func:`ror_analytical` but makes no closed-form
    assumptions and handles asymmetric or unusual payout distributions.

    Args:
        ev_per_hand:       Mean net payout per hand (dollars).
        std_dev_per_hand:  Per-hand standard deviation (dollars).
        bankroll:          Starting capital in dollars.
        num_trials:        Number of independent sessions to simulate.
        max_hands:         Maximum hands per trial before declaring survival.
        seed:              Optional RNG seed for reproducibility.

    Returns:
        Estimated probability of ruin in [0, 1].
    """
    if ev_per_hand <= 0:
        return 1.0
    if bankroll <= 0:
        return 1.0

    rng = np.random.default_rng(seed)
    ruined = 0

    # Simulate in chunks of 10 000 hands to avoid huge allocations.
    chunk = min(10_000, max_hands)
    for _ in range(num_trials):
        balance = bankroll
        hands_played = 0
        while hands_played < max_hands and balance > 0:
            n = min(chunk, max_hands - hands_played)
            outcomes = rng.normal(loc=ev_per_hand, scale=std_dev_per_hand, size=n)
            # Check for ruin hand-by-hand using cumulative sum.
            cumulative = np.cumsum(outcomes)
            running = balance + cumulative
            ruin_idx = np.argmax(running <= 0)
            if running[ruin_idx] <= 0:
                ruined += 1
                break
            balance = float(running[-1])
            hands_played += n

    return ruined / num_trials


def n0_hands(ev_per_hand: float, std_dev_per_hand: float) -> float:
    """Return N-0 expressed in hands played.

    N-0 (the "point of no return") is the number of hands after which the
    player's expected winnings exceed one standard deviation of results — i.e.,
    the point at which a losing session becomes statistically unlikely.

    Formula:  N0 = (σ / μ)²

    Args:
        ev_per_hand:      Mean net payout per hand (dollars).
        std_dev_per_hand: Per-hand standard deviation (dollars).

    Returns:
        N-0 in hands, or ``float('inf')`` if ev_per_hand ≤ 0.
    """
    if ev_per_hand <= 0:
        return float("inf")
    return (std_dev_per_hand / ev_per_hand) ** 2


def n0_hours(
    ev_per_hand: float,
    std_dev_per_hand: float,
    rounds_per_hour: float,
) -> float:
    """Return N-0 expressed in hours of play.

    Args:
        ev_per_hand:      Mean net payout per hand (dollars).
        std_dev_per_hand: Per-hand standard deviation (dollars).
        rounds_per_hour:  Hands dealt per hour (e.g., 100 heads-up).

    Returns:
        N-0 in hours, or ``float('inf')`` if ev_per_hand ≤ 0 or
        rounds_per_hour ≤ 0.
    """
    if ev_per_hand <= 0 or rounds_per_hour <= 0:
        return float("inf")
    return n0_hands(ev_per_hand, std_dev_per_hand) / rounds_per_hour


def score(
    ev_per_hand: float,
    variance_per_hand: float,
    rounds_per_hour: float,
) -> float:
    """Compute SCORE (Standardised Comparison Of Risk and Expectation).

    SCORE is the desirability index used by professional counters to compare
    different games and conditions.  It measures how quickly EV accumulates
    relative to variance risk:

        SCORE = EV² / variance_per_hand × rounds_per_hour

    Equivalently, it is the rate at which the player's edge "outpaces"
    the noise of the game.  Higher SCORE = better game conditions.

    Note: this is proportional to the reciprocal of N-0 scaled by hourly EV,
    so a game with twice the SCORE reaches N-0 in half the time for the same
    hourly EV.

    Args:
        ev_per_hand:      Mean net payout per hand (dollars).
        variance_per_hand: Variance of payout per hand (dollars²).
        rounds_per_hour:  Hands dealt per hour.

    Returns:
        SCORE in dollars²/hand × hands/hour = dollars²/hour.
        Returns 0.0 if variance or rounds_per_hour are non-positive.
    """
    if variance_per_hand <= 0 or rounds_per_hour <= 0:
        return 0.0
    return (ev_per_hand ** 2) / variance_per_hand * rounds_per_hour


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def calculate_metrics(
    sim_result: SimulationResult,
    bankroll: float,
    rounds_per_hour: float,
    run_monte_carlo: bool = False,
    mc_trials: int = 50_000,
    mc_seed: Optional[int] = None,
) -> SessionMetrics:
    """Compute all session metrics from an aggregated simulation result.

    Takes the output of :func:`~backend.simulator.aggregate_results` plus
    session parameters and returns a fully populated :class:`SessionMetrics`.

    Metric derivations:

    * **EV/hr**      = ev_per_hand × rounds_per_hour
    * **SD/hr**      = std_dev_per_hand × sqrt(rounds_per_hour)
                       (SD scales with √n, not n)
    * **RoR**        = exp(−2 × ev_per_hand × bankroll / variance_per_hand)
    * **N-0**        = (SD / EV)² hands, divided by rounds_per_hour for hours
    * **SCORE**      = EV² / variance × rounds_per_hour

    Args:
        sim_result:       Output of :func:`~backend.simulator.aggregate_results`.
        bankroll:         Starting bankroll in dollars.
        rounds_per_hour:  Expected hands per hour (use CLAUDE.md table for
                          heads-up vs. full table).
        run_monte_carlo:  If True, also estimate RoR via MC simulation
                          (slow — ~5 s for 50 000 trials).
        mc_trials:        Number of MC trials for RoR estimation.
        mc_seed:          Optional seed for MC reproducibility.

    Returns:
        Populated :class:`SessionMetrics`.

    Raises:
        ValueError: If ``rounds_per_hour`` ≤ 0 or ``bankroll`` ≤ 0.
    """
    if rounds_per_hour <= 0:
        raise ValueError(f"rounds_per_hour must be positive, got {rounds_per_hour}")
    if bankroll <= 0:
        raise ValueError(f"bankroll must be positive, got {bankroll}")

    ev   = sim_result.ev_per_hand
    sd   = sim_result.std_dev_per_hand
    var  = sd ** 2

    ev_hr   = ev * rounds_per_hour
    sd_hr   = sd * math.sqrt(rounds_per_hour)

    ror_a   = ror_analytical(ev, var, bankroll)

    ror_mc: Optional[float] = None
    if run_monte_carlo:
        ror_mc = ror_monte_carlo(ev, sd, bankroll, num_trials=mc_trials, seed=mc_seed)

    n0_h  = n0_hands(ev, sd)
    n0_hr = n0_hours(ev, sd, rounds_per_hour)
    sc    = score(ev, var, rounds_per_hour)

    return SessionMetrics(
        ev_per_hand=ev,
        ev_per_hour=ev_hr,
        std_dev_per_hand=sd,
        std_dev_per_hour=sd_hr,
        variance_per_hand=var,
        ror_analytical=ror_a,
        ror_monte_carlo=ror_mc,
        n0_hands=n0_h,
        n0_hours=n0_hr,
        score=sc,
    )


# ---------------------------------------------------------------------------
# Convenience: metrics from raw rounds
# ---------------------------------------------------------------------------

def calculate_metrics_from_rounds(
    rounds: List[RoundResult],
    bankroll: float,
    rounds_per_hour: float,
    run_monte_carlo: bool = False,
    mc_trials: int = 50_000,
    mc_seed: Optional[int] = None,
) -> SessionMetrics:
    """Compute metrics directly from a raw list of :class:`RoundResult`.

    Thin wrapper that calls :func:`~backend.simulator.aggregate_results` and
    then :func:`calculate_metrics`.  Useful when you have the raw round list
    in memory and don't want to aggregate separately.

    Args:
        rounds:           Raw output of :func:`~backend.simulator.simulate_session`.
        bankroll:         Starting bankroll in dollars.
        rounds_per_hour:  Expected hands per hour.
        run_monte_carlo:  Whether to run MC RoR estimation.
        mc_trials:        MC trial count.
        mc_seed:          MC seed.

    Returns:
        Populated :class:`SessionMetrics`.
    """
    from backend.simulator import aggregate_results  # local import avoids circularity
    sim_result = aggregate_results(rounds)
    return calculate_metrics(
        sim_result,
        bankroll,
        rounds_per_hour,
        run_monte_carlo=run_monte_carlo,
        mc_trials=mc_trials,
        mc_seed=mc_seed,
    )
