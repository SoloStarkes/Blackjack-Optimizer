# API Reference

The Blackjack Optimizer exposes a FastAPI server at **http://localhost:8000**
with three endpoints.

- Interactive Swagger docs: **http://localhost:8000/docs**
- ReDoc reference: **http://localhost:8000/redoc**
- OpenAPI JSON schema: **http://localhost:8000/openapi.json**

CORS is configured to allow all origins (`*`), methods, and headers.  Tighten
this in any public-facing deployment.

---

## GET /health

Liveness check.  Used by scripts to wait for the server to be ready.

### Request

```
GET http://localhost:8000/health
```

No body, no parameters.

### Response

```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

### Example

```bash
curl http://localhost:8000/health
```

```python
import httpx
r = httpx.get("http://localhost:8000/health")
assert r.json()["status"] == "ok"
```

---

## POST /simulate

Run a Hi-Lo counting Monte Carlo simulation and return session metrics.

### Request body schema

All fields are optional and have defaults.

#### `rules` object

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `decks` | int | `6` | must be one of `{1, 2, 4, 6, 8}` | Number of decks in the shoe |
| `penetration` | float | `0.75` | `(0.0, 1.0)` exclusive | Fraction of shoe dealt before reshuffle |
| `h17` | bool | `true` | — | Dealer hits soft 17 |
| `das` | bool | `true` | — | Double after split allowed |
| `rsa` | bool | `true` | — | Re-split aces allowed |
| `max_splits` | int | `3` | `[1, 4]` | Maximum splits per round |
| `surrender` | bool | `true` | — | Late surrender allowed |
| `bj_payout` | float | `1.5` | `(1.0, 2.0]` | BJ multiplier: 1.5 = 3:2, 1.2 = 6:5 |

#### Top-level fields

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `bet_spread` | dict[str, float] | `{"1": 25.0}` | keys parse as int; values ≥ 0; at least one > 0 | TC (string key) → dollar bet. Bet = 0 means wong out. |
| `bankroll` | float | `25000.0` | `> 0` | Starting bankroll in dollars |
| `rounds_per_hour` | float | `100.0` | `> 0` | Hands per hour (see RPH reference in README) |
| `num_shoes` | int | `10000` | `[100, 500000]` | Shoes to simulate |
| `seed` | int\|null | `null` | — | RNG seed for reproducibility |

> **JSON key requirement**: JSON objects cannot have integer keys.  All
> `bet_spread` keys must be quoted integers: `"1"`, `"-2"`, `"5"`.  The API
> converts them to `int` internally.

### Request example

```json
{
  "rules": {
    "decks": 6,
    "penetration": 0.75,
    "h17": true,
    "das": true,
    "rsa": true,
    "max_splits": 3,
    "surrender": true,
    "bj_payout": 1.5
  },
  "bet_spread": {
    "0": 0,
    "1": 25,
    "2": 50,
    "3": 100,
    "4": 150,
    "5": 200
  },
  "bankroll": 25000,
  "rounds_per_hour": 100,
  "num_shoes": 3000,
  "seed": 42
}
```

### Response schema

| Field | Type | Description |
|---|---|---|
| `ev_per_hour` | float | Expected net win per hour (dollars) |
| `std_dev_per_hour` | float | Per-hour standard deviation (dollars) |
| `risk_of_ruin` | float | Probability of losing entire bankroll (Gambler's Ruin formula) |
| `hours_to_n0` | float | Hours until EV exceeds 1 SD. Returns `-1.0` when EV ≤ 0 (infinite N-0). |
| `score` | float | SCORE = EV²/variance × RPH |
| `total_hands` | int | Total hands played (wongs excluded) |
| `total_wagered` | float | Sum of all initial bets across all hands |
| `total_won` | float | Net dollars won across all hands |
| `ev_per_hand` | float | Mean net payout per hand |
| `std_dev_per_hand` | float | Per-hand standard deviation |
| `edge_by_tc` | dict[int, float] | Player edge at each integer true count seen |

### Response example

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
  "std_dev_per_hand": 102.50,
  "edge_by_tc": {
    "1": 0.011,
    "2": 0.018,
    "3": 0.025,
    "4": 0.033
  }
}
```

### Error responses

| Status | When | Body |
|---|---|---|
| `422 Unprocessable Entity` | Validation failed | `{"detail": [{"loc": […], "msg": "…", "type": "…"}]}` |
| `422 Unprocessable Entity` | Simulation produced no played rounds | `{"detail": "Simulation produced no played rounds. Check that bet_spread…"}` |
| `500 Internal Server Error` | Unexpected simulation exception | `{"detail": "Simulation error: <message>"}` |

### Curl example

```bash
curl -s -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "rules": {"decks":6,"penetration":0.75,"h17":true,"das":true,
              "rsa":true,"max_splits":3,"surrender":true,"bj_payout":1.5},
    "bet_spread": {"0":0,"1":25,"2":50,"3":100,"4":150,"5":200},
    "bankroll": 25000,
    "rounds_per_hour": 100,
    "num_shoes": 500,
    "seed": 42
  }' | python3 -m json.tool
```

### Python example

```python
import httpx

resp = httpx.post(
    "http://localhost:8000/simulate",
    json={
        "rules": {"decks": 6, "penetration": 0.75, "h17": True,
                  "das": True, "rsa": True, "max_splits": 3,
                  "surrender": True, "bj_payout": 1.5},
        "bet_spread": {"0": 0, "1": 25, "2": 50, "3": 100, "4": 150, "5": 200},
        "bankroll": 25000,
        "rounds_per_hour": 100,
        "num_shoes": 500,
        "seed": 42,
    },
    timeout=120,
)
resp.raise_for_status()
data = resp.json()
print(f"EV/hr: ${data['ev_per_hour']:.2f}")
print(f"RoR:   {data['risk_of_ruin']:.2%}")
```

---

## POST /variance-visual

Simulate many independent bankroll paths and return percentile curves over a
specified time horizon.  Used to power the Variance Visualizer chart in the frontend.

### Request body schema

Inherits all fields from `/simulate`, plus three additional fields:

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `hours` | float | `200.0` | `> 0` | Time horizon for the chart (hours) |
| `percentiles` | list[float] | `[5, 25, 50, 75, 95]` | each in `[0, 100]` | Which percentile curves to return |
| `num_paths` | int | `500` | `[50, 5000]` | Number of independent bankroll paths to simulate |

### How it works

1. Runs a base Monte Carlo simulation (same as `/simulate`) to obtain
   `ev_per_hand` and `std_dev_per_hand`.
2. Simulates `num_paths` independent random walks, each modelled as normally
   distributed per-hand outcomes.
3. Processes in chunks of 1,000 hands to keep peak RAM under ~4 MB regardless
   of horizon length.
4. Samples bankroll values at up to 200 evenly-spaced hour ticks across the
   horizon.
5. Computes percentile curves with `numpy.percentile`.

### Request example

```json
{
  "rules": {
    "decks": 6, "penetration": 0.75, "h17": true,
    "das": true, "rsa": true, "max_splits": 3,
    "surrender": true, "bj_payout": 1.5
  },
  "bet_spread": {"0": 0, "1": 25, "2": 50, "3": 100, "4": 150, "5": 200},
  "bankroll": 25000,
  "rounds_per_hour": 100,
  "num_shoes": 10000,
  "seed": 42,
  "hours": 1000,
  "num_paths": 300,
  "percentiles": [5, 25, 50, 75, 95]
}
```

### Response schema

| Field | Type | Description |
|---|---|---|
| `hours` | list[float] | Hour tick marks for the x-axis (≤ 200 points) |
| `percentile_curves` | dict[str, list[float]] | Percentile label → bankroll at each tick. Bankroll = 0 means ruined. |
| `ruin_probability` | float | Fraction of paths that hit $0 within the horizon |
| `ev_curve` | list[float] | Deterministic EV: `bankroll + ev_per_hand × hands_at_tick` |

### Response example (abbreviated)

```json
{
  "hours": [0.0, 5.05, 10.1, "..."],
  "percentile_curves": {
    "5":  [25000, 22300, 19800, "..."],
    "25": [25000, 24200, 23500, "..."],
    "50": [25000, 25500, 26100, "..."],
    "75": [25000, 26900, 28700, "..."],
    "95": [25000, 29200, 33500, "..."]
  },
  "ruin_probability": 0.013,
  "ev_curve": [25000, 25481, 25963, "..."]
}
```

### Performance notes

| `hours` | `num_paths` | `rounds_per_hour` | Max hands | Peak RAM |
|---|---|---|---|---|
| 200 | 500 | 100 | 20,000 | < 1 MB |
| 1,000 | 300 | 100 | 100,000 | ~2 MB |
| 1,000 | 5,000 | 200 | 200,000 | ~12 MB |

The chunked walk (`_WALK_CHUNK=1_000`) processes 1,000 hands at a time,
keeping the live array size bounded at `num_paths × 1,000 × 8 bytes`.

### Error responses

Same as `/simulate`, plus:

| Status | When |
|---|---|
| `422` | `hours × rounds_per_hour < 1` (would produce zero hands) |

---

## Validation Rules Summary

| Condition | Error message |
|---|---|
| `decks` not in `{1, 2, 4, 6, 8}` | `"decks must be one of 1, 2, 4, 6, 8"` |
| `penetration` not in `(0, 1)` | standard Pydantic range error |
| `bj_payout` not in `(1.0, 2.0]` | `"bj_payout must be in (1.0, 2.0]"` |
| `bet_spread` key not an int string | `"bet_spread key '…' must be an integer string"` |
| any bet amount `< 0` | `"bet amounts must be ≥ 0"` |
| all bets = 0 | `"bet_spread must include at least one non-zero bet"` |
| `num_shoes < 100` | standard Pydantic range error |
| percentile outside `[0, 100]` | `"Each percentile must be in [0, 100]"` |

---

## Timeout Guidance

The frontend enforces:
- `/simulate`: 120-second timeout (`AbortController`)
- `/variance-visual`: 240-second timeout

For the server itself, there are no configured timeouts — uvicorn will serve
as long as the simulation runs.

### Expected runtimes

| Endpoint | `num_shoes` | Typical time |
|---|---|---|
| `/simulate` | 500 | < 2 s |
| `/simulate` | 3,000 | 5–10 s |
| `/simulate` | 10,000 | 20–40 s |
| `/variance-visual` | 10,000 shoes + 300 paths × 1,000 hrs | 60–120 s |
