# Blackjack Optimizer

A Monte Carlo blackjack simulation engine that computes EV/hr, standard deviation,
risk of ruin, N-0, and SCORE for any rule-set and bet spread — inspired by CVCX and Pro Bang.

Built for MATH-4940 (Blackjack Optimization using RL and Risk Models), Spring 2026,
Rensselaer Polytechnic Institute.

---

## Features

- **Full shoe simulation** — 1/2/4/6/8-deck Hi-Lo counting with Illustrious 18 + Fab 4 deviations
- **Wong-out support** — bet = $0 at any true count to skip unfavorable rounds
- **All key metrics** — EV/hr, ±SD/hr, Risk of Ruin (Gambler's Ruin), N-0, SCORE
- **Variance Visualizer** — 1 000-hour bankroll chart at 5/25/50/75/95th percentile
- **Kelly criterion** — full and fractional Kelly bet sizing per true-count bucket
- **Strategy comparison** — flat bet vs. full Kelly vs. half Kelly, side-by-side
- **Q-learning agent** — learns basic strategy from scratch; diff against the textbook table
- **Ruin simulator** — 10 000-trajectory empirical RoR vs. analytical Gambler's Ruin formula
- **Dark-theme UI** — single-file React app, no build step required

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.11+** | Tested on 3.13.5. Required for modern `typing` and `dataclasses` behaviour. |
| pip | any recent | Bundled with Python. |
| A browser | any modern | Chrome / Firefox / Safari / Edge. **No Node.js required.** |

### Python packages

| Package | Minimum | Used for |
|---|---|---|
| `fastapi[standard]` | 0.135 | API server + OpenAPI docs + form parsing |
| `uvicorn[standard]` | 0.44 | ASGI server (includes h11, WebSocket support) |
| `numpy` | 1.26 | Vectorised shoe simulation and random walks |
| `pydantic` | 2.0 | Request/response validation, `field_validator` |
| `httpx` | 0.28 | `TestClient` for FastAPI integration tests |
| `pytest` | 9.0 | Test runner |

**No Node.js, no npm.** The frontend loads React 18, Recharts 2.12.7, and Babel
standalone 7.23.9 from [unpkg.com](https://unpkg.com) at runtime.

---

## Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd blackjack-optimizer        # or wherever you put it

# 2. Create and activate a virtual environment (strongly recommended)
python3 -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt
```

**No venv? Install directly:**

```bash
pip install "fastapi[standard]>=0.135" "uvicorn[standard]>=0.44" \
            "numpy>=1.26" "pydantic>=2" "httpx>=0.28" "pytest>=9"
```

---

## Running the backend

```bash
# From the repo root (not from inside backend/)
python -m uvicorn backend.api:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir backend
```

Or use the one-command script (installs deps, runs tests, then starts the server):

```bash
chmod +x run.sh
./run.sh              # first run  — installs deps, runs fast tests, starts server
./run.sh --no-install # skip pip install (deps already present)
./run.sh --no-test    # skip tests, start server immediately
```

| URL | Purpose |
|---|---|
| `http://localhost:8000` | API base |
| `http://localhost:8000/docs` | Interactive Swagger UI |
| `http://localhost:8000/redoc` | ReDoc reference |
| `http://localhost:8000/health` | Liveness check |

---

## Running the frontend

`frontend/app.jsx` is a **self-contained HTML file** — open it directly or serve it.

### Option A — open directly in a browser

```
File → Open File → .../frontend/app.jsx
```

> **Note:** Some browsers block `fetch()` from `file://` pages.
> If you see _"Failed to fetch"_, use Option B.

### Option B — serve with Python (recommended)

```bash
# In a second terminal, from the repo root:
python -m http.server 5500 --directory frontend

# Then open:
#   http://localhost:5500/app.jsx
```

The UI targets the API at `http://localhost:8000`.  If you run the server on a
different port, edit the `API_URL` constant near the top of `frontend/app.jsx`.

---

## Running tests

```bash
# Full suite — 614 tests (~5–6 minutes due to Monte Carlo sims)
python -m pytest backend/tests/ -v

# Fast subset — engine + strategy + API only (~30 seconds)
python -m pytest backend/tests/test_engine.py \
                  backend/tests/test_strategy.py \
                  backend/tests/test_api.py -v

# Single file
python -m pytest backend/tests/test_ruin_sim.py -v
```

Expected result: **614 passed**.

| Test file | Tests | What it covers |
|---|---|---|
| `test_engine.py` | 61 | Shoe, Hand, card values, play_round |
| `test_strategy.py` | 136 | Basic strategy tables, I18/Fab-4 deviations |
| `test_counting.py` | 60 | Hi-Lo Counter, true_count_frequencies |
| `test_simulator.py` | 44 | simulate_session, wong-out, aggregate_results |
| `test_ev.py` | 84 | RoR, N-0, SCORE, calculate_metrics |
| `test_api.py` | 68 | /simulate, /variance-visual, /health endpoints |
| `test_comparison.py` | 57 | Flat/Kelly strategy comparison |
| `test_rl_agent.py` | 54 | Q-learning agent, policy diff |
| `test_ruin_sim.py` | 50 | Empirical vs analytical RoR |

---

## Quick-start curl example

Start the server, then run:

```bash
curl -s -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "rules": {
      "decks": 6, "penetration": 0.75, "h17": true,
      "das": true, "rsa": true, "max_splits": 3,
      "surrender": true, "bj_payout": 1.5
    },
    "bet_spread": {
      "0": 0, "1": 25, "2": 50, "3": 100, "4": 150, "5": 200
    },
    "bankroll": 25000,
    "rounds_per_hour": 100,
    "num_shoes": 1000,
    "seed": 42
  }' | python3 -m json.tool
```

**Expected response** (values are approximate — Monte Carlo varies with `num_shoes`):

```json
{
  "ev_per_hour": 96.13,
  "std_dev_per_hour": 1002.22,
  "risk_of_ruin": 0.0084,
  "hours_to_n0": 109.0,
  "score": 0.0086,
  "total_hands": 24436,
  "total_wagered": 977530.0,
  "total_won": 23495.0,
  "ev_per_hand": 0.961,
  "std_dev_per_hand": 100.22,
  "edge_by_tc": {"1": 0.011, "2": 0.018, "3": 0.025}
}
```

**Same request in Python** (requires `httpx`):

```python
import httpx, json

payload = {
    "rules": {"decks": 6, "penetration": 0.75, "h17": True, "das": True,
               "rsa": True, "max_splits": 3, "surrender": True, "bj_payout": 1.5},
    "bet_spread": {"0": 0, "1": 25, "2": 50, "3": 100, "4": 150, "5": 200},
    "bankroll": 25000, "rounds_per_hour": 100, "num_shoes": 1000, "seed": 42,
}
r = httpx.post("http://localhost:8000/simulate", json=payload, timeout=120)
print(json.dumps(r.json(), indent=2))
```

---

## Project layout

```
blackjack-optimizer/
├── run.sh                      # install deps + (optionally) run tests + start server
├── requirements.txt            # pinned Python dependencies
├── CLAUDE.md                   # project spec and coding conventions
├── README.md
│
├── backend/
│   ├── engine.py               # Shoe, Hand, GameRules, play_round
│   ├── strategy.py             # Basic strategy tables + I18/Fab-4 deviations
│   ├── counting.py             # Hi-Lo Counter, true_count_frequencies
│   ├── simulator.py            # Monte Carlo session simulator
│   ├── ev_calculator.py        # EV/hr, RoR, N-0, SCORE
│   ├── kelly.py                # Kelly criterion bet sizing
│   ├── comparison.py           # Flat / full Kelly / half Kelly comparison
│   ├── rl_agent.py             # Q-learning blackjack agent
│   ├── ruin_sim.py             # Empirical ruin probability simulator
│   ├── api.py                  # FastAPI server (3 endpoints)
│   └── tests/
│       ├── test_engine.py      (61 tests)
│       ├── test_strategy.py    (136 tests)
│       ├── test_counting.py    (60 tests)
│       ├── test_simulator.py   (44 tests)
│       ├── test_ev.py          (84 tests)
│       ├── test_api.py         (68 tests)
│       ├── test_comparison.py  (57 tests)
│       ├── test_rl_agent.py    (54 tests)
│       └── test_ruin_sim.py    (50 tests)   ← 614 total
│
└── frontend/
    └── app.jsx                 # Standalone React UI (no build step)
```

---

## API reference

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.0.0"}
```

---

### `POST /simulate`

Run a Hi-Lo counting Monte Carlo simulation and return session metrics.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `rules.decks` | int | 6 | Decks in shoe — must be one of 1, 2, 4, 6, 8 |
| `rules.penetration` | float | 0.75 | Fraction dealt before reshuffle (exclusive: 0 < p < 1) |
| `rules.h17` | bool | true | Dealer hits soft 17 |
| `rules.das` | bool | true | Double after split allowed |
| `rules.rsa` | bool | true | Re-split aces allowed |
| `rules.max_splits` | int | 3 | Max splits per round (1–4) |
| `rules.surrender` | bool | true | Late surrender allowed |
| `rules.bj_payout` | float | 1.5 | BJ payout (1.5 = 3:2, 1.2 = 6:5) |
| `bet_spread` | dict | `{"1":25}` | TC (string key) → dollar bet. Bet = 0 means wong out. |
| `bankroll` | float | 25000 | Starting bankroll in dollars |
| `rounds_per_hour` | float | 100 | Hands per hour (see RPH reference below) |
| `num_shoes` | int | 10000 | Shoes to simulate (100–500 000) |
| `seed` | int\|null | null | RNG seed for reproducibility |

> **bet_spread keys must be integer strings** (`"1"`, `"-2"`) — JSON does not allow integer keys.

**Response**

```json
{
  "ev_per_hour": 96.13,
  "std_dev_per_hour": 1002.22,
  "risk_of_ruin": 0.0084,
  "hours_to_n0": 109.0,
  "score": 0.0086,
  "total_hands": 122183,
  "total_wagered": 4893650.0,
  "total_won": 117457.0,
  "ev_per_hand": 0.961,
  "std_dev_per_hand": 100.22,
  "edge_by_tc": {"1": 0.011, "2": 0.018, "3": 0.025}
}
```

`hours_to_n0` is `-1` when EV ≤ 0 (infinite N-0).

---

### `POST /variance-visual`

Same body as `/simulate`, plus three additional fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `hours` | float | 200 | Time horizon for the chart |
| `percentiles` | list | [5,25,50,75,95] | Percentile curves to return (values 0–100) |
| `num_paths` | int | 500 | Bankroll paths to simulate for the chart (50–5 000) |

**Response**

```json
{
  "hours": [0.0, 5.0, 10.0, "..."],
  "percentile_curves": {
    "5":  [25000, 22000, "..."],
    "50": [25000, 26000, "..."],
    "95": [25000, 31000, "..."]
  },
  "ruin_probability": 0.013,
  "ev_curve": [25000, 25481, "..."]
}
```

---

## Key formulas

```
EV/hr          = ev_per_hand × rounds_per_hour
SD/hr          = sd_per_hand × √(rounds_per_hour)
Risk of Ruin   = exp(−2 × ev_per_hand × bankroll / variance_per_hand)
N-0 (hands)    = (sd_per_hand / ev_per_hand)²
N-0 (hours)    = N-0_hands / rounds_per_hour
SCORE          = ev_per_hand² / variance_per_hand × rounds_per_hour
Kelly fraction = edge / variance
```

---

## Bet spread examples

### Conservative 1–8 (wong in at TC+1)

| True Count | Bet |
|---|---|
| ≤ 0 | $0 (wong out) |
| +1  | $25 |
| +2  | $50 |
| +3  | $100 |
| +4  | $150 |
| +5+ | $200 |

Expected: ~$96/hr EV, ~0.8% RoR with $25k bankroll, 100 rph.

### Aggressive 1–12 (S17 DAS RSA game)

| True Count | Bet |
|---|---|
| ≤ 0 | $0 (wong out) |
| +1  | $25 |
| +2  | $75 |
| +3  | $150 |
| +4  | $225 |
| +5+ | $300 |

Expected: ~$150/hr EV, ~5% RoR with $25k bankroll, 100 rph.

---

## Game rules reference

| Rule | Effect on house edge |
|---|---|
| Dealer hits soft 17 (H17) | +0.20% to house |
| No double after split | +0.14% to house |
| No late surrender | +0.08% to house |
| No re-split aces | +0.06% to house |
| 6:5 blackjack payout | +1.39% to house |
| Each additional deck | ~+0.03% to house |

## Rounds per hour reference

| Players at table | Rounds/hr |
|---|---|
| 1 (heads-up) | ~200 |
| 2 | ~130 |
| 3 | ~100 |
| 4 | ~70 |
| 5+ | ~55 |

---

## Research modules

These are not served via the API but can be imported from a script or notebook.

### Bet-sizing strategy comparison

```python
from backend.comparison import compare_strategies, format_comparison_table
from backend.engine import GameRules

rules = GameRules(decks=6, penetration=0.75, h17=True, das=True, rsa=True,
                  max_splits=3, surrender=True, bj_payout=1.5)

result = compare_strategies(rules, bankroll=25_000, rounds_per_hour=100,
                             flat_bet_amount=25, num_shoes=10_000, seed=42)
print(format_comparison_table(result))
```

Sample output:

```
========================================================================
  BET-SIZING STRATEGY COMPARISON
  Bankroll: $25,000   RPH: 100   Decks: 6   Pen: 75%
========================================================================
  Strategy          EV/hr      SD/hr      RoR   N-0 hrs      SCORE
------------------------------------------------------------------------
  Flat Bet         $12.34    $280.00   51.23%      636.3   0.000194
  Full Kelly      $124.56   $1430.00    0.43%       89.1   0.000760
  Half Kelly       $72.34    $715.00    0.20%      108.7   0.000720
========================================================================
```

### Q-learning agent

```python
from backend.rl_agent import train_agent, compare_to_basic_strategy, format_policy_diff
from backend.engine import GameRules

rules = GameRules(decks=6, penetration=0.75, h17=True, das=True)
agent = train_agent(rules, num_hands=2_000_000, seed=42)
diff  = compare_to_basic_strategy(agent)
print(format_policy_diff(diff))
# Agreement rate: 71.3%  (117 / 164 states agree with basic strategy)
```

### Ruin probability simulator

```python
from backend.ruin_sim import simulate_ruin, format_ruin_report

result = simulate_ruin(
    ev_per_hand=0.96,         # from /simulate: ev_per_hand
    std_dev_per_hand=105.0,   # from /simulate: std_dev_per_hand
    bankroll=25_000,
    num_trajectories=10_000,
    max_hands=1_000_000,      # ~10 000 hours at 100 rph
    seed=42,
)
print(format_ruin_report(result))
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'backend'`

Run from the **repo root**, not from inside `backend/`:

```bash
# Wrong
cd backend && python -m uvicorn api:app

# Correct — must be at the repo root so Python sees the 'backend' package
python -m uvicorn backend.api:app --reload
```

### `Address already in use` — port 8000 occupied

```bash
# Find what's using port 8000
lsof -i :8000          # macOS / Linux
netstat -ano | findstr :8000   # Windows

# Start the server on a different port
python -m uvicorn backend.api:app --port 8001

# Then update API_URL in frontend/app.jsx to match
```

### `Failed to fetch` in the browser

1. **API not running** — check `http://localhost:8000/health` returns `{"status":"ok"}`.
2. **`file://` origin blocked** — browsers restrict `fetch()` from local files.
   Serve the frontend with:
   ```bash
   python -m http.server 5500 --directory frontend
   # Open http://localhost:5500/app.jsx
   ```

### CORS errors

`CORSMiddleware` in `api.py` sends `Access-Control-Allow-Origin: *`, allowing any
origin.  If you still see CORS errors, verify the request URL matches the running
server host and port exactly (no trailing slash, no HTTP vs HTTPS mismatch).

### Tests hang or take too long

The slowest tests are in `test_comparison.py` and `test_ruin_sim.py` (Monte Carlo).
Run the fast subset for quick iteration:

```bash
python -m pytest backend/tests/test_engine.py \
                  backend/tests/test_strategy.py \
                  backend/tests/test_api.py -v
```

### `httpx.ReadTimeout` during tests

Tests use `TestClient` (synchronous transport — no network timeout).  If a test
hangs, the simulation itself is stalled.  Try reducing `num_shoes` in the
relevant test fixture or adding `-x` to stop at the first failure.

### Python 3.10 or earlier

The codebase uses `from __future__ import annotations` throughout and relies on
`pydantic v2` field validators.  Python 3.10 may work but is untested.
Python 3.11+ is the stated minimum.

### `pydantic` v1 installed

All validators use the Pydantic v2 API (`@field_validator`, `@model_validator`).
If you see `ImportError: cannot import name 'field_validator'`, upgrade:

```bash
pip install "pydantic>=2"
```

### Variance chart returns empty curves

`/variance-visual` requires `num_shoes ≥ 100` to produce meaningful per-hand
EV and SD estimates.  If both are near zero, the random walk produces flat lines.
Increase `num_shoes` or use the `/simulate` endpoint first to verify the bet spread
produces playable hands (non-zero `total_hands` in the response).
