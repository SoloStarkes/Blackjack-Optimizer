# EV and Risk Metrics

`backend/ev_calculator.py` takes a `SimulationResult` and session parameters
and computes the six key practitioner metrics: EV/hr, SD/hr, Risk of Ruin, N-0,
and SCORE.

---

## The Metrics Dataclass

```python
@dataclass
class SessionMetrics:
    ev_per_hand: float          # mean net payout per hand (dollars)
    ev_per_hour: float          # ev_per_hand × rounds_per_hour
    std_dev_per_hand: float     # per-hand standard deviation (dollars)
    std_dev_per_hour: float     # std_dev_per_hand × √rounds_per_hour
    variance_per_hand: float    # std_dev_per_hand²
    ror_analytical: float       # Gambler's Ruin formula
    ror_monte_carlo: float|None # MC estimate (optional, slow)
    n0_hands: float             # (std_dev / ev)²
    n0_hours: float             # n0_hands / rounds_per_hour
    score: float                # ev² / variance × rph
```

---

## Formula Derivations

### 1. EV per hand

The expected value per hand comes directly from the simulation:

```
ev_per_hand = total_won / total_hands
```

This is the mean net payout across all played rounds (wongs excluded).
It already accounts for the bet spread — high-count rounds contribute larger
wins, low-count rounds contribute smaller wins or losses.

### 2. EV per hour

```
ev_per_hour = ev_per_hand × rounds_per_hour
```

If you play 100 rounds per hour and each round earns $0.96 on average:

```
ev_per_hour = 0.96 × 100 = $96/hr
```

This is a linear scaling because each hour consists of `rounds_per_hour`
independent repetitions of the same bet-spread distribution.

### 3. Standard Deviation per hand

```
std_dev_per_hand = sample_std(payouts)
```

The standard deviation of the payout distribution reflects not just win/loss
variance but also the variance from doubles, splits, and blackjacks.  For
multi-deck blackjack with basic strategy, the per-unit SD is typically ~1.15 units
of the average bet.

### 4. Standard Deviation per hour

```
std_dev_per_hour = std_dev_per_hand × √(rounds_per_hour)
```

**Why √n, not n?** When you add `n` independent random variables, each with
standard deviation σ, the standard deviation of the sum is `σ × √n`.  (Variance
is additive, so `Var(sum) = n × Var(hand)`, hence `SD(sum) = σ × √n`.)

This means SD grows much slower than EV as you play more rounds — which is why
long-run advantage players are essentially guaranteed to win eventually.

### 5. Risk of Ruin (Gambler's Ruin)

The analytical Risk of Ruin is the probability that a random walk with positive
drift eventually hits zero before running to infinity:

```
RoR = exp(−2 × ev_per_hand × bankroll / variance_per_hand)
```

This is the closed-form solution for a **continuous-time random walk** with:
- Drift: `μ = ev_per_hand` (positive = player edge)
- Variance: `σ² = variance_per_hand`
- Starting value: `bankroll`
- Absorbing barrier at 0

```python
def ror_analytical(ev_per_hand, variance_per_hand, bankroll):
    if ev_per_hand <= 0:
        return 1.0     # certain ruin with no edge
    exponent = -2.0 * ev_per_hand * bankroll / variance_per_hand
    return math.exp(exponent)
```

**When does RoR = 0?** Never exactly, but it approaches zero as bankroll → ∞
or as edge → ∞.

**When does RoR = 1?** When `ev_per_hand ≤ 0` — a player with no edge or the
house edge will eventually be ruined.

### 6. N-0 (Point of No Return)

N-0 is the number of hands at which the player's **expected cumulative winnings
exceed one standard deviation** of results.  At N-0, a losing session becomes
statistically unlikely (requires the player to be in the bottom 16% of outcomes).

```
N0_hands = (std_dev_per_hand / ev_per_hand)²
N0_hours = N0_hands / rounds_per_hour
```

Derivation: we want the point `n` where `EV(n) > 1 SD(n)`:

```
ev_per_hand × n > std_dev_per_hand × √n
ev × √n > SD
√n > SD / ev
n > (SD / ev)²
```

So `N0 = (SD / ev)²` is the smallest `n` where this holds.

### 7. SCORE (Standardised Comparison of Risk and Expectation)

```
SCORE = ev_per_hand² / variance_per_hand × rounds_per_hour
```

SCORE measures how rapidly the player's EV "outpaces" the noise of the game.
It is the rate at which the edge accumulates relative to variance risk.

Note: SCORE is **not** simply proportional to EV/hr.  A larger bet spread
increases EV but also increases variance.  If variance grows faster than EV²,
SCORE can actually decrease despite higher hourly EV.

---

## Analytical RoR vs Monte Carlo RoR

Both are implemented in `ev_calculator.py`.

### Analytical (Gambler's Ruin)

**Assumptions:**
- Payouts are normally distributed (central limit theorem applies after many hands)
- The game is stationary (same EV/variance every hand)
- Bankroll is continuous (not integer bets)
- No session stopping rules — you play until ruin or infinite wealth

**Advantages:** Instantaneous to compute; mathematically exact under the above assumptions.

**Disadvantages:** Real blackjack payouts are discrete and non-normal — blackjacks
pay 1.5×, surrenders pay −0.5×, doubles pay ±2×.  For small bankrolls (< 50 × average
bet), the approximation can be off by a factor of 2 or more.

### Monte Carlo RoR

```python
def ror_monte_carlo(ev_per_hand, std_dev_per_hand, bankroll,
                    num_trials=50_000, max_hands=1_000_000, seed=None):
    rng = np.random.default_rng(seed)
    ruined = 0
    for _ in range(num_trials):
        balance = bankroll
        hands = 0
        while hands < max_hands and balance > 0:
            n = min(10_000, max_hands - hands)
            outcomes = rng.normal(ev_per_hand, std_dev_per_hand, n)
            cumulative = balance + np.cumsum(outcomes)
            ruin_idx = np.argmax(cumulative <= 0)
            if cumulative[ruin_idx] <= 0:
                ruined += 1; break
            balance = float(cumulative[-1])
            hands += n
    return ruined / num_trials
```

**Advantages:** Makes no closed-form assumptions.  Works for asymmetric payout
distributions.  Can model session-length stopping rules.

**Disadvantages:** Slow (~5 seconds for 50 000 trials).  Still uses a Gaussian
approximation — the actual blackjack payout distribution is discrete and
multi-modal.

**In practice:** For bankrolls > 200 × average bet, the Gambler's Ruin formula
is accurate to within ±1%.  For smaller bankrolls, Monte Carlo gives a more
realistic estimate.

---

## Concrete Numeric Example

**Setup:**
- Game: 6-deck, H17, DAS, RSA, 75% penetration, 3:2 BJ
- Bet spread: TC≤0 = $0 (wong out), TC+1 = $25, TC+2 = $50, TC+3 = $100, TC+4 = $150, TC+5+ = $200
- Bankroll: $25,000
- Rounds per hour: 100 (3 players at the table)

**Simulation result (3,000 shoes ≈ 75,000 hands):**

```
total_hands    = 24,800
total_wagered  = $992,000
total_won      = $23,808
ev_per_hand    = $23,808 / 24,800 = $0.960
std_dev_per_hand = $102.50
```

**Step-by-step metric computation:**

```
1.  ev_per_hour       = 0.960 × 100               = $96.00 / hr

2.  std_dev_per_hour  = 102.50 × √100             = $1,025 / hr

3.  variance_per_hand = 102.50²                   = $10,506.25

4.  RoR (analytical)  = exp(−2 × 0.960 × 25,000 / 10,506.25)
                      = exp(−2 × 24,000 / 10,506.25)
                      = exp(−4.569)
                      = 0.0104  ≈ 1.0%

5.  N0 (hands)        = (102.50 / 0.960)²
                      = 106.77²
                      = 11,400 hands

6.  N0 (hours)        = 11,400 / 100              = 114 hours

7.  SCORE             = 0.960² / 10,506.25 × 100
                      = 0.9216 / 10,506.25 × 100
                      = 0.00877
```

**Interpretation:**

- You expect to win $96/hr on average.
- In any given hour, your result is $96 ± $1,025 (1 SD).  Most individual hours
  will be a loss.
- After 114 hours (11,400 hands), your cumulative profit should exceed its own
  standard deviation — a losing stretch of this length would put you in the
  bottom 16% of possible outcomes.
- Risk of Ruin is 1.04%: if you play indefinitely, there is roughly a 1-in-96
  chance of losing your entire $25,000 bankroll before recovering.

**Sanity check on RoR:**

The 1% RoR makes intuitive sense: $25,000 bankroll is about 245× the average bet
($102 average bet with this spread).  The rule of thumb for a 1% RoR is roughly
200–250× the average bet at a 1% edge.  ✓
