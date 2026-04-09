# Blackjack Optimization Simulator

## Project Overview
A blackjack simulation application that calculates expected value, risk of ruin, standard deviation, and hours to N-0 given configurable game rules and bet spreads. Inspired by CVCX/Pro Bang software. Built for Solomon's independent study on Blackjack Optimization using RL and Risk Models (MATH-4940, Spring 2026).

## Architecture

```
blackjack-sim/
├── CLAUDE.md
├── backend/
│   ├── engine.py          # Core shoe, card, hand, and game logic
│   ├── strategy.py        # Basic strategy lookup tables
│   ├── counting.py        # Hi-Lo counting system, true count
│   ├── simulator.py       # Monte Carlo simulator (runs N shoes)
│   ├── ev_calculator.py   # EV/hr, std dev, risk of ruin, N-0
│   ├── kelly.py           # Kelly criterion bet sizing
│   ├── api.py             # FastAPI server exposing simulation endpoints
│   └── tests/
│       ├── test_engine.py
│       ├── test_strategy.py
│       ├── test_simulator.py
│       └── test_ev.py
└── frontend/
    └── app.jsx            # React UI (single artifact file)
```

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, NumPy
- **Frontend**: React (rendered as a Claude artifact or standalone HTML)
- **No database** — everything is computed on-the-fly

## Core Game Rules (Configurable)
- Number of decks: 1, 2, 4, 6, 8
- Penetration: percentage of shoe dealt before reshuffle (e.g., 75% = 78 cards in 6-deck)
- Dealer hits soft 17 (H17) or stands (S17): boolean
- Double after split (DAS): boolean
- Re-split aces (RSA): boolean
- Max splits: 1-4 hands
- Surrender allowed: boolean (late surrender)
- Blackjack pays: 3:2 or 6:5

## Counting System
- Hi-Lo: 2-6 = +1, 7-9 = 0, 10/J/Q/K/A = -1
- True count = running_count / decks_remaining
- Decks remaining = cards_remaining / 52

## Bet Spread Format
A dictionary mapping true count thresholds to bet amounts:
```python
{
    # true_count: bet_amount
    0: 0,      # sit out or wong out at TC 0 and below
    1: 25,     # minimum bet
    2: 50,
    3: 100,
    4: 150,
    5: 200,
}
```
Negative counts can map to 0 (wong out) or min bet (play through).

## Key Formulas

### Expected Value per hand
EV = Σ (frequency_of_TC × edge_at_TC × bet_at_TC)

### Hourly EV
EV/hr = EV_per_hand × rounds_per_hour

### Standard Deviation per hand
σ = bet_size × ~1.15 (base SD for blackjack is ~1.15 units)

### Risk of Ruin (approximation)
RoR = e^(-2 × EV_per_hand × bankroll / variance_per_hand)

### Hours to N-0 (break-even point of no return)
N0_hands = (σ / EV_per_hand)²
N0_hours = N0_hands / rounds_per_hour

### Kelly Criterion
f* = edge / variance = EV_per_hand / σ²

## Rounds Per Hour Reference
- 1 player (heads-up): ~200 rounds/hr
- 2 players: ~130 rounds/hr
- 3 players: ~90 rounds/hr
- 4 players: ~70 rounds/hr
- 5+ players: ~55 rounds/hr

## Coding Conventions
- Use type hints everywhere in Python
- Docstrings on all public functions
- Keep engine.py pure (no I/O, no randomness injection except via seed)
- Simulator should accept a `seed` parameter for reproducibility
- Use dataclasses for Hand, Shoe, GameRules, SimulationResult
- All monetary values in dollars as floats
- Test edge cases: splits, double downs, insurance, surrender, naturals

## API Endpoints
- `POST /simulate` — accepts rules, bet spread, num_simulations; returns EV, SD, RoR, N0
- `POST /variance-visual` — returns percentile curves over N hours for the variance visualizer
- `GET /health` — healthcheck
