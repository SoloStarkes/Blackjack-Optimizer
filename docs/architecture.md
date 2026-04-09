# Architecture

## System Overview

The Blackjack Optimizer is a three-tier application: a browser-based UI, a Python
FastAPI server, and a pure-Python simulation engine.  There is no database — every
result is computed on demand.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser  (frontend/app.jsx)                                        │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   │
│  │  Game Rules  │   │  Bet Spread  │   │  Controls Bar        │   │
│  │  Panel       │   │  Panel       │   │  (bankroll, rph,     │   │
│  └──────┬───────┘   └──────┬───────┘   │   num_shoes)         │   │
│         └──────────────────┴──────┬────┘                        │   │
│                                   │ auto-debounce (750ms)        │   │
│                          POST /simulate                           │   │
│                          POST /variance-visual                    │   │
└───────────────────────────────────┼─────────────────────────────┘
                                    │ HTTP/JSON  (CORS: *)
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Server  (backend/api.py)  — port 8000                     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  POST /simulate        POST /variance-visual    GET /health  │  │
│  │                                                               │  │
│  │  Pydantic validation → GameRules → bet_spread               │  │
│  └──────────────┬────────────────────────┬────────────────────┘  │
│                 │                        │                          │
│        simulate_session()      simulate_session() +               │
│                 │              random-walk paths                   │
└─────────────────┼──────────────────────────────────────────────────┘
                  │
┌─────────────────▼──────────────────────────────────────────────────┐
│  Simulator  (backend/simulator.py)                                  │
│                                                                     │
│  for each shoe:                                                     │
│    for each round:                                                  │
│      ┌────────────────┐                                             │
│      │  Counter       │  ← counting.py (Hi-Lo running/true count)  │
│      └────────┬───────┘                                             │
│               │ true count                                          │
│      ┌────────▼───────┐                                             │
│      │  bet_spread    │  lookup bet for this TC                     │
│      │  lookup        │                                             │
│      └────────┬───────┘                                             │
│               │ bet > 0: play round   bet = 0: wong out            │
│      ┌────────▼───────┐  ┌──────────────────────────┐             │
│      │  play_round()  │  │  basic_strategy()        │             │
│      │  engine.py     │◄─┤  + deviation()           │             │
│      └────────┬───────┘  │  strategy.py             │             │
│               │          └──────────────────────────┘             │
│               │ RoundResult(true_count, bet, payout)               │
└───────────────┼─────────────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────────────┐
│  Aggregation + Metrics                                               │
│                                                                     │
│  aggregate_results()    →  SimulationResult                        │
│  (simulator.py)            (ev_per_hand, std_dev, edge_by_tc …)    │
│                                                                     │
│  calculate_metrics()    →  SessionMetrics                          │
│  (ev_calculator.py)        (ev/hr, SD/hr, RoR, N-0, SCORE)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

| Module | File | Responsibility |
|---|---|---|
| **Engine** | `backend/engine.py` | Pure game logic: shuffled shoe, hand totals, dealer play, round resolution. No I/O, no counting awareness. |
| **Strategy** | `backend/strategy.py` | Complete multi-deck basic strategy lookup tables for H17/S17/DAS/no-DAS, plus the 22 Illustrious 18 + Fab 4 counting deviations. |
| **Counting** | `backend/counting.py` | Hi-Lo running count and true count calculation; vectorised NumPy simulation of the true-count frequency distribution. |
| **Simulator** | `backend/simulator.py` | Wires engine + strategy + counting into a full multi-shoe Monte Carlo session; handles bet-spread lookup and wong-out logic. |
| **EV Calculator** | `backend/ev_calculator.py` | Post-simulation metrics: EV/hr, SD/hr, analytical and Monte Carlo RoR, N-0, SCORE. |
| **Kelly** | `backend/kelly.py` | Kelly Criterion bet sizing: full Kelly, fractional Kelly, optimal bet spread per true-count bucket. |
| **Comparison** | `backend/comparison.py` | Side-by-side comparison of flat-bet, full-Kelly, and half-Kelly strategies under identical game conditions. |
| **RL Agent** | `backend/rl_agent.py` | Q-learning agent that learns blackjack strategy from scratch; compares learned policy to basic strategy. |
| **Ruin Simulator** | `backend/ruin_sim.py` | Empirical ruin-probability estimator: runs 10 000 bankroll trajectories and compares to the analytical Gambler's Ruin formula. |
| **API** | `backend/api.py` | FastAPI server exposing `/simulate`, `/variance-visual`, and `/health`. Handles Pydantic validation, CORS, and chunked random-walk computation. |
| **Frontend** | `frontend/app.jsx` | Self-contained React + Recharts UI. Auto-simulates on parameter change (debounced 750 ms). Opens a Variance Visualizer modal for long-horizon bankroll charts. |

---

## Data Flow: One Simulation Request

Here is a complete trace from the user changing a game rule to the results appearing on screen.

### Step 1 — User interaction

The user toggles "Hits Soft 17" off (changing H17 → S17).  React's `setRule`
updates the `rules` state.  A `useEffect` watching `runSim` fires a 750 ms
debounce timer.  Any in-flight `/simulate` request is cancelled immediately via
its `AbortController`.

### Step 2 — Frontend builds the request

After 750 ms with no further changes, `runSim` is called:

```js
// buildBody() assembles the JSON payload
{
  rules: { decks: 6, penetration: 0.75, h17: false, das: true, … },
  bet_spread: { "0": 0, "1": 25, "2": 50, "3": 100, "4": 150, "5": 200 },
  bankroll: 25000,
  rounds_per_hour: 100,
  num_shoes: 3000,
  seed: null
}
```

`fetchWithTimeout` wraps `fetch()` in a 120-second `AbortController` timeout
and `POST`s to `http://localhost:8000/simulate`.

### Step 3 — API receives and validates the request

`FastAPI` deserialises the JSON body into a `SimulateRequest` (Pydantic model).
Validators fire:
- `decks` must be one of `{1, 2, 4, 6, 8}`
- `penetration` must be in `(0.0, 1.0)` exclusive
- `bj_payout` must be in `(1.0, 2.0]`
- All `bet_spread` keys must parse as integers
- At least one non-zero bet must exist

`_build_game_rules()` converts `RulesIn` → `GameRules` dataclass.
`_parse_bet_spread()` converts `{"0": 0, "1": 25, …}` → `{0: 0.0, 1: 25.0, …}`.

### Step 4 — Monte Carlo simulation

`simulate_session(rules, bet_spread, basic_strategy, num_shoes=3000)` runs:

```
for shoe 0..2999:
    shoe.reshuffle()
    counter.reset()

    while not cut_card_reached():
        decks_rem = cards_remaining / 52
        tc = floor(running_count / decks_rem)    ← counting.py
        bet = bet_spread[highest_key ≤ tc]

        if bet == 0:
            deal 4 cards (advance shoe + count)  ← wong out
            continue

        strategy_fn = basic_strategy + I18/Fab4 deviations at tc
        payout = play_round(shoe, bet, rules, strategy_fn)  ← engine.py
        rounds.append(RoundResult(tc, bet, payout))
```

Each call to `play_round` deals a complete hand: deal 4 cards, check for
natural blackjack, run the player through `_play_hand` (which may recurse for
splits), run the dealer via `_play_dealer`, then call `_settle` for each
completed hand.

### Step 5 — Aggregation

`aggregate_results(rounds)` computes:
- `total_hands`, `total_wagered`, `total_won`
- `ev_per_hand = total_won / total_hands`
- `std_dev_per_hand = statistics.stdev([r.payout for r in rounds])`
- `edge_by_true_count`: for each integer TC, `mean(payouts) / mean(bets)`

### Step 6 — Metrics

`calculate_metrics(sim_result, bankroll=25000, rounds_per_hour=100)` applies
the formulae from `ev_calculator.py`:

```
ev_hr  = ev_per_hand × 100
sd_hr  = sd_per_hand × √100
ror    = exp(-2 × ev_per_hand × 25000 / sd_per_hand²)
n0_hrs = (sd_per_hand / ev_per_hand)² / 100
score  = ev_per_hand² / sd_per_hand² × 100
```

### Step 7 — API serialises the response

```json
{
  "ev_per_hour": 96.13,
  "std_dev_per_hour": 1002.22,
  "risk_of_ruin": 0.0084,
  "hours_to_n0": 109.0,
  "score": 0.0086,
  ...
}
```

`hours_to_n0` is replaced with `-1.0` if `math.isinf(n0)` (negative EV).

### Step 8 — Frontend renders

React receives the JSON, updates `results` state.  Four metric cards re-render:
- **EV/hr** — green/red depending on sign
- **±SD/hr** — always blue ("info")
- **Risk of Ruin** — green (<5%), orange (5–15%), red (>15%)
- **Hours to N-0** — yellow; shows "∞" for -1 sentinel

The stats strip below updates with SCORE, total hands, wagered, and edge-by-TC.
The Variance Visualizer button becomes enabled once `results` is non-null.
