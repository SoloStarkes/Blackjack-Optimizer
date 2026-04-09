# Kelly Criterion

`backend/kelly.py` implements the Kelly Criterion for blackjack bet sizing:
full Kelly, fractional Kelly, and an optimal bet spread computed from per-TC
edge estimates.

---

## What the Kelly Criterion Optimises

The Kelly Criterion answers: *given a known edge, what fraction of your bankroll
should you bet to maximise the long-run rate of wealth growth?*

It maximises the **expected logarithm** of wealth, `E[log(W)]`, which is
equivalent to maximising the geometric growth rate.  Unlike maximising expected
dollars, the log criterion automatically accounts for the fact that losing a
large fraction of your bankroll is disproportionately damaging to future growth.

### Simple coin-flip example

You are offered a biased coin: 60% chance of heads (you win your bet), 40% tails
(you lose).  Your bankroll is $100.

Full Kelly fraction: `f* = p - q = 0.60 - 0.40 = 0.20` → bet $20.

- Bet $10 (half-Kelly): slower growth, less volatility.
- Bet $20 (full Kelly): optimal growth rate.
- Bet $40 (2× Kelly): growth rate actually decreases — over-betting is destructive.
- Bet $100 (all-in): `E[log(W)] = 0.6 × log(200) + 0.4 × log(0) = -∞` → certain eventual ruin.

---

## The Formula for Blackjack

In blackjack, the Kelly fraction is:

```
f* = edge / variance
```

Where:
- `edge` = expected net payout per unit bet (e.g. 0.01 = 1% player advantage)
- `variance` = variance of payout per unit bet (≈ 1.32 for multi-deck blackjack)

```python
def kelly_fraction(edge: float, variance: float) -> float:
    if variance <= 0:
        return 0.0
    return edge / variance
```

If edge = 0.01 and variance = 1.32:

```
f* = 0.01 / 1.32 ≈ 0.0076
```

With a $25,000 bankroll: `bet = 25,000 × 0.0076 = $190`.

A negative edge returns a negative fraction — the Kelly criterion says don't bet.

### Why 1.32 for variance?

A simplified blackjack payout has outcomes like:
- Win (most hands): +1 unit
- Lose: −1 unit
- Blackjack (~4.8%): +1.5 units
- Double win (~9%): +2 units
- Split wins (~variable): varies

The sum of squared deviations from the expected value, weighted by probability,
works out to approximately 1.32 units² for a typical multi-deck game with
doubles and splits.  The actual variance is slightly different per rule set;
`variance_per_unit=1.32` is the standard practitioner default.

---

## Full Kelly vs Half Kelly vs Fixed Betting

### Full Kelly

```
bet = bankroll × (edge / variance)
```

- Maximises the geometric growth rate (long-run wealth)
- Requires exact knowledge of the edge (error in edge estimate leads to over-betting)
- Very high variance: in the short run, drawdowns of 30–50% are common
- **Absolute guarantee**: you cannot go bankrupt if you strictly follow full Kelly
  (you always bet a fraction of your remaining bankroll, never a fixed dollar amount)

### Half Kelly

```
bet = bankroll × 0.5 × (edge / variance)
```

Half-Kelly is the most widely recommended practical strategy:
- Growth rate ≈ **75% of full Kelly** (you sacrifice only 25% of maximum growth)
- Variance ≈ **50% of full Kelly** (drawdowns are dramatically reduced)
- More robust to edge estimation errors

The growth/variance tradeoff is asymmetric in Kelly's favour:

| Strategy | Growth rate (relative) | Variance (relative) |
|---|---|---|
| Full Kelly | 100% | 100% |
| Half Kelly | 75% | 50% |
| Quarter Kelly | ~44% | 25% |

### Fixed betting

A fixed bet (e.g. always $25 regardless of bankroll) is **not** Kelly sizing.
It has these characteristics:
- Simple to implement
- Appropriate for recreational players with no bankroll management goals
- Does not grow bet sizes as bankroll grows, so geometric growth rate is lower
- Can lead to ruin if the fixed bet is too large relative to bankroll

---

## `kelly_bet`: Dollar Amount

```python
def kelly_bet(bankroll, edge, variance, fraction=1.0,
              min_bet=0.0, max_bet=None) -> float:
    fk = fractional_kelly(edge, variance, fraction)
    if fk <= 0 or bankroll <= 0:
        return 0.0
    bet = bankroll * fk
    bet = max(bet, min_bet)
    if max_bet is not None:
        bet = min(bet, max_bet)
    return bet
```

`min_bet` enforces the table minimum; `max_bet` enforces the table maximum.
Both are applied after computing the Kelly amount.

---

## `optimal_bet_spread`: Bet Per True Count

`optimal_bet_spread` takes TC-edge estimates and TC frequencies and returns a
`List[BetSuggestion]` — one entry per true count:

```python
class BetSuggestion(NamedTuple):
    true_count: int
    edge: float
    kelly_bet: float         # full Kelly dollar bet at this TC
    half_kelly_bet: float    # half-Kelly dollar bet at this TC
    frequency: float         # fraction of hands at this TC
    ev_contribution: float   # EV per 100 hands from this bucket
```

### How it works

For each TC bucket where the player has an edge (edge > 0):

```python
fk_bet   = bankroll × (edge / variance)           # full Kelly
half_bet = bankroll × 0.5 × (edge / variance)     # half Kelly
ev_contribution = edge × half_bet × frequency × 100
```

Counts with a negative edge receive a bet of 0 (wong out is optimal).

### Example

Bankroll $25,000, 6-deck H17 game, TC edges from simulation:

| TC | Edge | Frequency | Full Kelly bet | Half Kelly bet | EV contrib/100 |
|---|---|---|---|---|---|
| +1 | +0.5% | 18% | $95 | $47 | $0.42 |
| +2 | +1.0% | 8% | $190 | $95 | $0.76 |
| +3 | +1.5% | 4% | $284 | $142 | $0.85 |
| +4 | +2.0% | 2% | $379 | $189 | $0.76 |
| +5 | +2.5% | 1% | $473 | $237 | $0.59 |

The EV contribution peaks around TC+3: it has a good edge *and* arises often enough
to matter.  Very high counts (+5 and above) are rare, so they contribute less
despite the large edge.

---

## Full Kelly vs Half Kelly: The Growth-Variance Tradeoff

Consider two players with the setup from [ev_and_risk.md]:
ev/hand = $0.96, SD/hand = $102.50, bankroll = $25,000.

**Full Kelly** (betting the Kelly-optimal fraction of bankroll each hand):
- Maximum geometric growth rate ≈ `ev² / (2 × variance)` per hand ≈ 0.0000439 per hand
- Very large short-run swings
- Average bet grows with bankroll → bet sizes in the hundreds or thousands at TC+5

**Half Kelly** (betting half that fraction):
- Growth rate ≈ `3/4 × (ev² / (2 × variance))` — **75% of full Kelly growth**
- Variance = 50% of full Kelly
- More realistic for casino play: bets stay within plausible table-spread ratios

**Fixed $25 bet** (never scales with bankroll):
- Linear growth only: bankroll grows by $96/hr regardless of bankroll size
- No compounding benefit
- Much lower RoR because bets are always small relative to a growing bankroll

The `compare_strategies` module in `backend/comparison.py` simulates all three
approaches under identical game conditions so you can compare EV, RoR, N-0, and
SCORE side by side.

---

## `approximate_edge_at_tc`: Rule-of-Thumb Edge

When simulation-derived edges are not available, a quick approximation is:

```python
def approximate_edge_at_tc(true_count: int, base_edge: float = -0.005) -> float:
    return base_edge + true_count * 0.005
```

Standard Hi-Lo rule of thumb: each +1 true count adds approximately +0.5% to
the player's edge over the base house edge.  For a 6-deck H17 game, the base
edge is roughly −0.5%.

| TC | Approx edge |
|---|---|
| −2 | −1.5% |
| −1 | −1.0% |
| 0 | −0.5% |
| +1 | 0.0% |
| +2 | +0.5% |
| +3 | +1.0% |
| +4 | +1.5% |
| +5 | +2.0% |

This rule-of-thumb is used as a fallback in `comparison.py` when the
simulation-derived edge table is empty.
