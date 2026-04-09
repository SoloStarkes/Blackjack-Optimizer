"""
api.py — FastAPI server for the Blackjack Optimization Simulator.

Endpoints:
    POST /simulate        — Run a Monte Carlo session, return EV/SD/RoR/N-0/edge.
    POST /variance-visual — Return bankroll percentile curves over hours.
    GET  /health          — Liveness check.

Run with:
    uvicorn backend.api:app --reload --port 8000
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.engine import GameRules
from backend.ev_calculator import calculate_metrics
from backend.simulator import aggregate_results, simulate_session
from backend.strategy import basic_strategy


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Blackjack Optimization Simulator",
    description=(
        "Monte Carlo blackjack simulator with Hi-Lo counting, "
        "EV/RoR/N-0 metrics, and variance visualisation."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared request schema
# ---------------------------------------------------------------------------

class RulesIn(BaseModel):
    """Blackjack rule-set parameters."""

    decks: int = Field(6, ge=1, le=8, description="Number of decks (1–8)")
    penetration: float = Field(
        0.75, gt=0.0, lt=1.0,
        description="Fraction of shoe dealt before reshuffle (0 < p < 1)",
    )
    h17: bool = Field(True, description="Dealer hits soft 17")
    das: bool = Field(True, description="Double after split allowed")
    rsa: bool = Field(True, description="Re-split aces allowed")
    max_splits: int = Field(3, ge=1, le=4, description="Maximum splits per hand")
    surrender: bool = Field(True, description="Late surrender allowed")
    bj_payout: float = Field(1.5, description="Blackjack payout (1.5 = 3:2, 1.2 = 6:5)")

    @field_validator("decks")
    @classmethod
    def decks_must_be_valid(cls, v: int) -> int:
        if v not in (1, 2, 4, 6, 8):
            raise ValueError("decks must be one of 1, 2, 4, 6, 8")
        return v

    @field_validator("bj_payout")
    @classmethod
    def bj_payout_must_be_valid(cls, v: float) -> float:
        if not (1.0 < v <= 2.0):
            raise ValueError("bj_payout must be in (1.0, 2.0] — use 1.5 for 3:2 or 1.2 for 6:5")
        return v


class SimulateRequest(BaseModel):
    """Request body for POST /simulate and POST /variance-visual."""

    rules: RulesIn = Field(default_factory=RulesIn)
    # Keys are string true-count thresholds (JSON doesn't allow int keys);
    # values are dollar bet amounts.  A bet of 0 means "wong out" at that TC.
    bet_spread: Dict[str, float] = Field(
        default={"1": 25.0},
        description=(
            "Mapping of true-count threshold (string) → bet in dollars. "
            "Step-function: highest key ≤ current TC determines the bet. "
            "Bet = 0 means wong out."
        ),
    )
    bankroll: float = Field(25_000.0, gt=0, description="Starting bankroll in dollars")
    rounds_per_hour: float = Field(
        100.0, gt=0,
        description=(
            "Hands dealt per hour (played rounds only). "
            "Reference: 200 heads-up, 130 for 2 players, 100 for 3, 70 for 4, 55 for 5+."
        ),
    )
    num_shoes: int = Field(
        10_000, ge=100, le=500_000,
        description="Number of shoes to simulate (more → more accurate, slower)",
    )
    seed: Optional[int] = Field(None, description="RNG seed for reproducibility")

    @field_validator("bet_spread")
    @classmethod
    def bet_spread_must_be_non_empty(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            raise ValueError("bet_spread must have at least one entry")
        for key, bet in v.items():
            try:
                int(key)
            except ValueError:
                raise ValueError(f"bet_spread key {key!r} must be an integer string")
            if bet < 0:
                raise ValueError(f"bet amounts must be ≥ 0, got {bet} at TC {key}")
        return v

    @model_validator(mode="after")
    def bet_spread_has_positive_bet(self) -> "SimulateRequest":
        if all(v == 0 for v in self.bet_spread.values()):
            raise ValueError("bet_spread must include at least one non-zero bet")
        return self


def _parse_bet_spread(raw: Dict[str, float]) -> Dict[int, float]:
    """Convert string-keyed JSON bet spread to int-keyed internal format."""
    return {int(k): v for k, v in raw.items()}


def _build_game_rules(r: RulesIn) -> GameRules:
    return GameRules(
        decks=r.decks,
        penetration=r.penetration,
        h17=r.h17,
        das=r.das,
        rsa=r.rsa,
        max_splits=r.max_splits,
        surrender=r.surrender,
        bj_payout=r.bj_payout,
    )


# ---------------------------------------------------------------------------
# POST /simulate
# ---------------------------------------------------------------------------

class SimulateResponse(BaseModel):
    """Aggregated session metrics."""

    ev_per_hour: float = Field(description="Expected net win per hour (dollars)")
    std_dev_per_hour: float = Field(description="Per-hour standard deviation (dollars)")
    risk_of_ruin: float = Field(description="Probability of losing the entire bankroll")
    hours_to_n0: float = Field(
        description=(
            "Hours until EV exceeds one standard deviation (N-0). "
            "Returns null when EV ≤ 0."
        ),
    )
    score: float = Field(description="SCORE desirability index (EV²/variance × rph)")
    total_hands: int = Field(description="Total hands simulated")
    total_wagered: float = Field(description="Total dollars wagered across all hands")
    total_won: float = Field(description="Total net dollars won")
    ev_per_hand: float = Field(description="Mean net payout per hand (dollars)")
    std_dev_per_hand: float = Field(description="Per-hand standard deviation (dollars)")
    edge_by_tc: Dict[int, float] = Field(
        description=(
            "Player edge (mean payout / mean bet) at each integer true count seen. "
            "Negative = house advantage at that count."
        ),
    )


@app.post("/simulate", response_model=SimulateResponse, summary="Run Monte Carlo session")
def simulate(req: SimulateRequest) -> SimulateResponse:
    """Run a Hi-Lo counting Monte Carlo simulation and return session metrics.

    The simulation:
    1. Deals ``num_shoes`` six-deck shoes (or the configured number).
    2. Applies the bet spread: wongs out when bet = 0, otherwise plays.
    3. Uses Illustrious-18 + Fab-4 counting deviations on top of basic strategy.
    4. Aggregates per-round results into EV, SD, RoR, N-0, and per-TC edge.
    """
    rules      = _build_game_rules(req.rules)
    bet_spread = _parse_bet_spread(req.bet_spread)

    try:
        rounds = simulate_session(
            rules, bet_spread, basic_strategy,
            num_shoes=req.num_shoes, seed=req.seed,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Simulation error: {exc}") from exc

    if not rounds:
        raise HTTPException(
            status_code=422,
            detail=(
                "Simulation produced no played rounds. "
                "Check that bet_spread includes at least one positive bet "
                "reachable with the given penetration."
            ),
        )

    sim     = aggregate_results(rounds)
    metrics = calculate_metrics(sim, req.bankroll, req.rounds_per_hour)

    hours_to_n0 = metrics.n0_hours
    if not math.isfinite(hours_to_n0):
        hours_to_n0 = -1.0   # sentinel: frontend treats -1 as "∞ / N/A"

    return SimulateResponse(
        ev_per_hour=metrics.ev_per_hour,
        std_dev_per_hour=metrics.std_dev_per_hour,
        risk_of_ruin=metrics.ror_analytical,
        hours_to_n0=hours_to_n0,
        score=metrics.score,
        total_hands=sim.total_hands,
        total_wagered=sim.total_wagered,
        total_won=sim.total_won,
        ev_per_hand=sim.ev_per_hand,
        std_dev_per_hand=sim.std_dev_per_hand,
        edge_by_tc=sim.edge_by_true_count,
    )


# ---------------------------------------------------------------------------
# POST /variance-visual
# ---------------------------------------------------------------------------

class VarianceVisualRequest(SimulateRequest):
    """Same as SimulateRequest plus chart-specific parameters."""

    hours: float = Field(
        200.0, gt=0,
        description="Time horizon for the variance chart (hours)",
    )
    percentiles: List[float] = Field(
        default=[5.0, 25.0, 50.0, 75.0, 95.0],
        description="Percentile curves to return (values in 0–100)",
    )
    num_paths: int = Field(
        500, ge=50, le=5_000,
        description="Number of independent bankroll paths to simulate for the chart",
    )

    @field_validator("percentiles")
    @classmethod
    def percentiles_valid(cls, v: List[float]) -> List[float]:
        for p in v:
            if not (0.0 <= p <= 100.0):
                raise ValueError(f"Each percentile must be in [0, 100], got {p}")
        return sorted(v)


class VarianceVisualResponse(BaseModel):
    """Percentile curves of bankroll over time."""

    hours: List[float] = Field(description="Hour tick marks for the x-axis")
    percentile_curves: Dict[str, List[float]] = Field(
        description=(
            "Mapping of percentile label (e.g. '50') → list of bankroll values "
            "at each hour tick.  A bankroll of 0 means the player was ruined."
        ),
    )
    ruin_probability: float = Field(
        description="Fraction of simulated paths that hit $0 within the time horizon",
    )
    ev_curve: List[float] = Field(
        description="Deterministic EV curve: bankroll + ev_per_hand × hands_at_hour",
    )


@app.post(
    "/variance-visual",
    response_model=VarianceVisualResponse,
    summary="Bankroll percentile curves for variance visualiser",
)
def variance_visual(req: VarianceVisualRequest) -> VarianceVisualResponse:
    """Simulate many independent bankroll paths and return percentile curves.

    Uses the per-hand EV and SD from a Monte Carlo simulation to model
    ``num_paths`` random walks over ``hours`` hours.  Each step represents
    one hand; bankroll is clamped at 0 on ruin.

    The random walk is computed in chunks of ``_WALK_CHUNK`` hands so that
    memory stays bounded regardless of the time horizon — a 1 000-hour
    simulation with 500 paths at 100 rph needs 50 M hands, but only
    ``num_paths × _WALK_CHUNK × 8`` bytes are live at once (≈ 4 MB).

    The response is designed to feed a line chart: x-axis = hours,
    y-axis = bankroll at each percentile.
    """
    # ── run base simulation to get EV/SD per hand ───────────────────────────
    rules      = _build_game_rules(req.rules)
    bet_spread = _parse_bet_spread(req.bet_spread)

    try:
        rounds = simulate_session(
            rules, bet_spread, basic_strategy,
            num_shoes=req.num_shoes, seed=req.seed,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Simulation error: {exc}") from exc

    if not rounds:
        raise HTTPException(
            status_code=422,
            detail="Simulation produced no played rounds — check bet_spread and penetration.",
        )

    sim          = aggregate_results(rounds)
    ev_per_hand  = sim.ev_per_hand
    sd_per_hand  = max(sim.std_dev_per_hand, 1e-9)   # avoid zero-SD degenerate case
    rph          = req.rounds_per_hour
    bankroll     = req.bankroll

    # ── chart resolution ────────────────────────────────────────────────────
    # At most 200 x-axis ticks regardless of horizon length.
    n_ticks    = min(200, int(req.hours) + 1)
    hour_ticks = np.linspace(0.0, req.hours, n_ticks)          # (n_ticks,)
    hands_at_tick = (hour_ticks * rph).astype(np.int64)         # (n_ticks,)
    max_hands     = int(hands_at_tick[-1])

    if max_hands == 0:
        raise HTTPException(status_code=422, detail="hours × rounds_per_hour must be ≥ 1")

    # ── chunked random-walk simulation ──────────────────────────────────────
    # Process _WALK_CHUNK hands at a time to keep peak RAM under ~4 MB even
    # for a 1 000-hour horizon (100 k hands) with 500 paths.
    _WALK_CHUNK = 1_000

    rng               = np.random.default_rng(req.seed)
    running           = np.full(req.num_paths, float(bankroll))   # current balance per path
    ruined            = np.zeros(req.num_paths, dtype=bool)        # permanently ruined flag
    tick_balances     = np.empty((req.num_paths, n_ticks))
    tick_balances[:, 0] = bankroll                                  # tick 0 = start
    next_tick_idx     = 1
    hand_cursor       = 0                                           # hands processed so far

    while hand_cursor < max_hands and next_tick_idx < n_ticks:
        chunk = min(_WALK_CHUNK, max_hands - hand_cursor)

        # Generate outcomes for this chunk; ruined paths produce no more PnL.
        raw = rng.normal(loc=ev_per_hand, scale=sd_per_hand, size=(req.num_paths, chunk))
        raw[ruined] = 0.0

        # Running balances within this chunk (shape: paths × chunk).
        cum = np.cumsum(raw, axis=1)
        chunk_bal = running[:, None] + cum                          # (paths, chunk)

        # Apply ruin: once balance ≤ 0, pin at 0 for the rest of this chunk.
        newly_ruined = (~ruined) & (chunk_bal[:, -1] <= 0)
        for p in np.where(chunk_bal.min(axis=1) <= 0)[0]:
            if ruined[p]:
                chunk_bal[p] = 0.0
                continue
            first = int(np.argmax(chunk_bal[p] <= 0))
            chunk_bal[p, first:] = 0.0
        ruined |= (chunk_bal[:, -1] <= 0)

        # Record any tick positions that fall inside this chunk.
        while next_tick_idx < n_ticks:
            tick_hand = int(hands_at_tick[next_tick_idx])
            if tick_hand > hand_cursor + chunk:
                break
            col = tick_hand - hand_cursor - 1           # 0-based within chunk
            col = max(0, min(col, chunk - 1))
            tick_balances[:, next_tick_idx] = chunk_bal[:, col]
            next_tick_idx += 1

        running = chunk_bal[:, -1].copy()
        hand_cursor += chunk

    # Fill any remaining ticks (can happen if max_hands was reached exactly).
    for i in range(next_tick_idx, n_ticks):
        tick_balances[:, i] = running

    # ── percentile curves ───────────────────────────────────────────────────
    percentile_curves: Dict[str, List[float]] = {}
    for p in req.percentiles:
        curve = np.percentile(tick_balances, p, axis=0)
        percentile_curves[str(int(p) if p == int(p) else p)] = curve.tolist()

    # ── EV curve ────────────────────────────────────────────────────────────
    ev_curve = (bankroll + ev_per_hand * hands_at_tick).tolist()

    # ── ruin probability ────────────────────────────────────────────────────
    ruin_probability = float(np.mean(ruined))

    return VarianceVisualResponse(
        hours=hour_ticks.tolist(),
        percentile_curves=percentile_curves,
        ruin_probability=ruin_probability,
        ev_curve=ev_curve,
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    """Return service status. Used by load balancers and frontend startup checks."""
    return HealthResponse(status="ok", version=app.version)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)
