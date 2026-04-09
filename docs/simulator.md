# Simulator

`backend/simulator.py` wires together the engine, strategy, and counting modules
into a full multi-shoe Monte Carlo session.  It is the computational heart of the
project.

---

## Key Types

```python
class RoundResult(NamedTuple):
    true_count: int    # integer Hi-Lo true count at round start
    bet: float         # initial wager (before doubles/splits)
    payout: float      # net dollar result (positive = won, negative = lost)

@dataclass
class SimulationResult:
    total_hands: int                    # played rounds (wongs excluded)
    total_wagered: float                # sum of all initial bets
    total_won: float                    # sum of all net payouts
    ev_per_hand: float                  # mean net payout per hand
    std_dev_per_hand: float             # sample standard deviation of payouts
    edge_by_true_count: Dict[int, float]  # edge = mean(payout)/mean(bet) per TC
```

---

## The Monte Carlo Loop

`simulate_session(rules, bet_spread, strategy_fn, num_shoes, seed)` is the main
entry point.  It runs `num_shoes` complete shoes and returns a flat list of
`RoundResult` for every *played* round.

```python
def simulate_session(...) -> List[RoundResult]:
    counter = Counter()
    shoe = _CountingShoe(rules, counter, seed=seed)
    rounds = []

    for shoe_idx in range(num_shoes):
        if shoe_idx > 0:
            shoe.reshuffle()   # resets counter, rebuilds shoe

        while not shoe.cut_card_reached():
            if shoe.cards_remaining() < _MIN_CARDS_FOR_ROUND:
                break           # guard: too few cards for a safe deal

            # ── compute true count ──
            decks_rem = shoe.cards_remaining() / 52.0
            tc = counter.true_count(decks_rem)

            # ── look up bet ──
            bet = _bet_for_tc(bet_spread, tc)

            # ── wong out ──
            if bet == 0:
                for _ in range(_WONG_OUT_CARDS):   # simulate ~4 cards passing
                    if shoe.cards_remaining() == 0: break
                    shoe.deal()                    # counter updated automatically
                    if shoe.cut_card_reached(): break
                continue

            # ── play the round ──
            round_strategy = _make_round_strategy(strategy_fn, tc)
            payout = play_round(shoe, bet, rules, round_strategy)
            rounds.append(RoundResult(tc, bet, payout))

    return rounds
```

### Shoe management

`_CountingShoe` is a subclass of `Shoe` that overrides `deal()` to call
`counter.update(card)` automatically.  `reshuffle()` calls `counter.reset()`.
This means the counting logic is invisible to the rest of the loop — the counter
stays in sync through the shoe's own deal mechanism.

Each shoe uses seed = `initial_seed + shoe_index`, so the session is fully
reproducible given the same seed but each shoe is independently shuffled.

### The minimum-cards guard

`_MIN_CARDS_FOR_ROUND = 20`.  If fewer than 20 cards remain, the loop stops that
shoe early.  20 is generous enough to handle the worst case: 4 splits each
doubled (requiring up to 12 player cards + 4 dealer cards).

### Bet-spread lookup

`_bet_for_tc(bet_spread, tc)` implements a **step function**:

```python
def _bet_for_tc(bet_spread: Dict[int, float], tc: int) -> float:
    eligible = [k for k in bet_spread if k <= tc]
    if not eligible:
        return 0.0
    return float(bet_spread[max(eligible)])
```

The highest bet-spread key that is ≤ the current TC determines the bet.  This
means:

```python
bet_spread = {0: 0, 1: 25, 2: 50, 3: 100, 5: 200}
# TC = 4 → highest key ≤ 4 is 3 → bet = $100
# TC = 6 → highest key ≤ 6 is 5 → bet = $200
# TC = -3 → no key ≤ -3 → bet = $0 (wong out)
```

---

## Wong-Out Implementation

**Wonging** (named after Stanford Wong) means sitting out rounds when the true
count is unfavourable while continuing to count cards.  In the simulator,
bet = 0 at a true count means wong out:

```python
if bet == 0:
    for _ in range(_WONG_OUT_CARDS):   # _WONG_OUT_CARDS = 4
        if shoe.cards_remaining() == 0: break
        shoe.deal()
        if shoe.cut_card_reached(): break
    continue
```

This advances the shoe by approximately 4 cards (≈ 2 player + 2 dealer in a
heads-up hand), keeps the counter accurate via `_CountingShoe.deal()`, and
skips recording a `RoundResult`.

The 4-card approximation is a simplification — a real wong-out involves watching
an actual hand dealt to other players.  For a solo Monte Carlo simulation it is
a reasonable proxy.

**Effect on metrics**: Wonging removes negative-EV rounds from `total_hands`,
raising `ev_per_hand`.  The cost is fewer hands per hour in reality (though
the simulator does not model table time).

---

## Deviation-Aware Strategy

`_make_round_strategy` captures the current true count in a closure and wraps
the base strategy function:

```python
def _make_round_strategy(base_strategy_fn, tc):
    def strategy(hand, dealer_upcard, rules):
        key = _deviation_key(hand, dealer_upcard)   # e.g. "16v10"
        if key is not None:
            dev = deviation(key, tc)
            if dev is not None and dev is not Action.INSURANCE:
                return dev
        return base_strategy_fn(hand, dealer_upcard, rules)
    return strategy
```

A new closure is created for each round so the TC captured is always the
TC at the *start* of that round.  Intra-round TC changes (cards dealt during
splits) do not affect the strategy for that round.

### Deviation key mapping

| Hand type | Key returned |
|---|---|
| Pair of 10s | `"10,10v{upcard}"` |
| Non-10 pair (e.g. 8,8) | `None` — no I18 deviation defined |
| Soft total | `None` — no I18 deviation for soft hands |
| Hard total | `"{total}v{upcard}"` |

Non-10 pairs return `None` to prevent the simulation bug where a pair like 8,8
(hard total 16) would match `"16v10"` and be told to STAND instead of SPLIT.

---

## Aggregate Results

`aggregate_results(rounds)` collapses the flat list into `SimulationResult`:

```python
def aggregate_results(rounds: List[RoundResult]) -> SimulationResult:
    payouts = [r.payout for r in rounds]
    bets    = [r.bet    for r in rounds]

    total_hands   = len(rounds)
    total_wagered = sum(bets)
    total_won     = sum(payouts)
    ev_per_hand   = total_won / total_hands
    std_dev       = statistics.stdev(payouts) if total_hands > 1 else 0.0

    # edge per TC = mean(payout) / mean(bet) in that TC bucket
    tc_payouts = defaultdict(list)
    tc_bets    = defaultdict(list)
    for r in rounds:
        tc_payouts[r.true_count].append(r.payout)
        tc_bets[r.true_count].append(r.bet)

    edge_by_tc = {
        tc: statistics.mean(tc_payouts[tc]) / statistics.mean(tc_bets[tc])
        for tc in tc_payouts
        if statistics.mean(tc_bets[tc]) != 0
    }
    return SimulationResult(…)
```

Note: `ev_per_hand` is calculated from aggregate totals, not the mean of per-round
payouts.  For sessions with splits (where one initial bet creates multiple payouts),
this correctly accounts for the extra wagering.  `std_dev` uses
`statistics.stdev` (sample standard deviation, dividing by n−1).

### Edge by true count

`edge_by_true_count` is expressed as `mean(payout) / mean(bet)`:
- TC +1: edge ≈ +0.01 (player wins 1% of money wagered)
- TC +3: edge ≈ +0.02 (player wins 2% of money wagered)
- TC 0: edge ≈ −0.005 (house edge ~0.5%)

This is the primary input used by `kelly.py` to compute optimal bet sizes.

---

## Effect of `num_shoes` on Accuracy

`num_shoes` controls how many complete shoes are simulated.  More shoes gives a
more accurate estimate at the cost of longer runtime.

| `num_shoes` | ~Hands simulated (6D, 75% pen, TC+1+ wonging) | Runtime | Accuracy |
|---|---|---|---|
| 500 | ~12 500 | < 1 second | Rough (±20% on EV) |
| 3 000 | ~75 000 | 2–5 seconds | Good (±5% on EV) |
| 10 000 | ~250 000 | 15–30 seconds | Very good (±2% on EV) |
| 100 000 | ~2 500 000 | 3–5 minutes | Excellent (±0.5% on EV) |

The standard error of the mean scales as `σ / √N`, so quadrupling `num_shoes`
halves the uncertainty.  For production use, 10 000 shoes balances accuracy and
speed well.

### Why not simulate fewer shoes for the UI default?

The UI's "Standard (3k shoes)" setting is a deliberate balance: fast enough
to update within seconds after parameter changes (debounce fires every 750 ms),
but accurate enough that the EV/hr and RoR figures are reliable to within ±5%.
"Detailed (10k)" is recommended for a final decision on bet spread.
