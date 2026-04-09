# Strategy

`backend/strategy.py` encodes the complete multi-deck basic strategy and the
22 counting deviations (Illustrious 18 + Fab 4) as static lookup tables.

---

## The Action Enum

Actions are defined as a `str`-inheriting enum so they can be compared directly
to plain strings without calling `.value`.  The engine's `_play_hand` function
checks `action == "hit"` etc., and `Action.HIT == "hit"` evaluates to `True`.

```python
class Action(str, Enum):
    HIT       = "hit"
    STAND     = "stand"
    DOUBLE    = "double"
    SPLIT     = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"   # deviation only; not a hand action
```

---

## Table Structure

There are **four** lookup tables, each keyed by a tuple:

| Table | Key | When used |
|---|---|---|
| `_HARD_H17` | `(hard_total, dealer_upcard)` | Hard totals 9–17, H17 game |
| `_HARD_S17_OVERRIDES` | same | Entries that differ under S17 |
| `_SOFT_H17` | `(soft_total, dealer_upcard)` | Soft totals 13–20 |
| `_SOFT_S17_OVERRIDES` | same | Entries that differ under S17 |
| `_PAIR_DAS` | `(pair_value, dealer_upcard)` | All pairs, DAS allowed |
| `_PAIR_NO_DAS_OVERRIDES` | same | Entries that differ without DAS |

`dealer_upcard` is always **normalised** to `{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}` —
Jack, Queen, and King all map to 10; Ace maps to 1.

### Hard totals

The `_HARD_H17` table covers totals 9–17 vs all 10 dealer upcards (100 entries).
Totals ≤ 8 always HIT; totals ≥ 18 always STAND — both handled as defaults in
`_lookup_action`, not stored in the table.

Example entries:

```python
# Hard 11 — double vs everything except Ace (H17)
(11, 2): D, (11, 3): D, (11, 4): D, (11, 5): D, (11, 6): D,
(11, 7): D, (11, 8): D, (11, 9): D, (11,10): D, (11, 1): H,

# Hard 16 — surrender vs 9, 10, A; stand vs 2–6; hit vs 7, 8
(16, 2): S, (16, 3): S, (16, 4): S, (16, 5): S, (16, 6): S,
(16, 7): H, (16, 8): H, (16, 9): R, (16,10): R, (16, 1): R,
```

Under S17, three entries change:
```python
_HARD_S17_OVERRIDES = {
    (11, 1): D,   # H17 = HIT  → S17 = DOUBLE (stronger game)
    (15, 1): H,   # H17 = SURRENDER → S17 = HIT
    (17, 1): S,   # H17 = SURRENDER → S17 = STAND
}
```

### Soft totals

The `_SOFT_H17` table covers soft 13–20 (Ace + 2 through Ace + 9).
Soft 21 is a blackjack or unreachable in a 2-card hand, so it defaults to STAND.

Key insight: **soft 18 (A,7)** is the most nuanced soft total:
- Stand vs 2, 7, 8
- Double vs 3–6 (strong dealer bust cards)
- Hit vs 9, 10, Ace (dealer is likely to beat 18)

Under S17 three entries change, all adding doubles the dealer cannot push:
```python
_SOFT_S17_OVERRIDES = {
    (17, 2): D,   # A,6 vs 2: H17 = HIT → S17 = DOUBLE
    (18, 2): D,   # A,7 vs 2: H17 = STAND → S17 = DOUBLE
    (19, 6): D,   # A,8 vs 6: H17 = STAND → S17 = DOUBLE
}
```

When a double is not available (3+ cards, or split hand with `rules.das=False`),
the fallback for soft 18 and soft 19 is **STAND**, not HIT — because standing on
soft 18 beats hitting on average.

### Pairs

The `_PAIR_DAS` table covers all 10 pair values (1–10) × 10 upcards = 100 entries.
Pairs of 5s are never split (treated as hard 10); pairs of 10s are never split
(already 20).

```python
# 8,8 — always split, even vs Ace (16 is otherwise unplayable)
(8, 2): P, (8, 3): P, …, (8, 1): P,

# 9,9 — split vs 2–9 except 7; stand vs 7, 10, A
(9, 7): S, (9, 10): S, (9, 1): S,  # dealer 7 beats two 9s; stand is better
```

Without DAS, borderline splits become –EV because you can't double if you
improve to a good total (e.g. 2+2 → 2+9 = 11, which normally doubles):

```python
_PAIR_NO_DAS_OVERRIDES = {
    (2, 2): H,  (2, 3): H,   # 2,2: don't split vs 2 or 3 without DAS
    (3, 2): H,  (3, 3): H,
    (4, 5): H,  (4, 6): H,   # 4,4: never split without DAS
    (6, 2): H,                # 6,6: don't split vs 2 without DAS
}
```

---

## The `basic_strategy` Function

`basic_strategy` is the public entry point.  It:

1. Normalises the dealer upcard via `_norm(dealer_upcard)`.
2. Calls `_lookup_action(hand, up, rules)` which checks pairs → soft → hard in
   that order.
3. Applies two rule-based fallbacks:

**Surrender fallback** — when `rules.surrender = False` and the table says
SURRENDER, return STAND for hard 17 vs Ace (the one case where standing beats
hitting when surrender is unavailable), and HIT otherwise.

**Double fallback** — when DOUBLE is not available for this hand (more than 2
cards, or a split hand without DAS), return STAND for soft 18/19 (standing is
second-best), and HIT for hard totals.

---

## Illustrious 18 + Fab 4 Deviations

Counting deviations override basic strategy when the true count crosses a
threshold.  The 22 deviations are stored in `_DEVIATIONS`, a dict mapping a
play-key string to a `_DevEntry(index, action, direction)` named tuple.

```python
class _DevEntry(NamedTuple):
    index: float      # true-count threshold
    action: Action    # action to take when the deviation fires
    direction: str    # "ge" = fire when TC ≥ index; "le" = fire when TC ≤ index
```

### Complete deviation table

#### Illustrious 18

| Play key | TC threshold | Deviated action | Basic strategy action | Effect |
|---|---|---|---|---|
| `insurance` | TC ≥ 3 | INSURANCE | (none) | Take even money / insurance |
| `16v10` | TC ≥ 0 | STAND | SURRENDER/HIT | The most valuable play |
| `15v10` | TC ≥ 4 | STAND | SURRENDER/HIT | |
| `12v3` | TC ≥ 2 | STAND | HIT | |
| `12v2` | TC ≥ 3 | STAND | HIT | |
| `11vA` | TC ≥ 1 | DOUBLE | HIT (H17) | |
| `9v2` | TC ≥ 1 | DOUBLE | HIT | |
| `10vA` | TC ≥ 4 | DOUBLE | HIT | |
| `9v7` | TC ≥ 3 | DOUBLE | HIT | |
| `16v9` | TC ≥ 5 | STAND | SURRENDER/HIT | |
| `13v2` | TC ≤ −1 | HIT | STAND | Negative-count override |
| `12v4` | TC ≤ 0 | HIT | STAND | |
| `13v3` | TC ≤ −2 | HIT | STAND | |
| `12v5` | TC ≤ −2 | HIT | STAND | |
| `12v6` | TC ≤ −1 | HIT | STAND | |
| `10,10v6` | TC ≥ 5 | SPLIT | STAND | Split 20s at high counts |
| `10,10v5` | TC ≥ 5 | SPLIT | STAND | |
| `10,10v4` | TC ≥ 6 | SPLIT | STAND | |

#### Fab 4 (surrender deviations)

| Play key | TC threshold | Action | Reason |
|---|---|---|---|
| `14v10` | TC ≥ 3 | SURRENDER | 14 vs 10 becomes –EV to play at high counts |
| `15v9` | TC ≥ 2 | SURRENDER | 15 vs 9 |
| `15vA` | TC ≥ 1 | SURRENDER | 15 vs A (important in S17 games) |
| `16v8` | TC ≥ 4 | SURRENDER | 16 vs 8 |

### How deviations are applied

`deviation(play: str, true_count: float)` looks up the entry and checks the
threshold:

```python
def deviation(play: str, true_count: float) -> Optional[Action]:
    entry = _DEVIATIONS.get(play)
    if entry is None:
        return None
    if entry.direction == "ge" and true_count >= entry.index:
        return entry.action
    if entry.direction == "le" and true_count <= entry.index:
        return entry.action
    return None
```

In `simulator.py`, `_make_round_strategy` wraps the base strategy function:

```python
def strategy(hand, dealer_upcard, rules):
    key = _deviation_key(hand, dealer_upcard)    # e.g. "16v10"
    if key is not None:
        dev = deviation(key, tc)
        if dev is not None and dev is not Action.INSURANCE:
            return dev                           # override fires
    return base_strategy_fn(hand, dealer_upcard, rules)
```

`_deviation_key` maps a hand to its play-key:
- Pair of 10s → `"10,10v{upcard}"`
- Non-10 pairs → `None` (no deviation defined)
- Soft totals → `None` (no I18 deviation for soft totals)
- Hard totals → `"{total}v{upcard}"` (e.g. `"16v10"`)

The `INSURANCE` action is treated as a side-bet signal and is deliberately
**skipped** in the strategy wrapper — insurance is handled separately in
real play and is not part of the hand-decision loop.

---

## Why These 22 Deviations?

The Illustrious 18 were identified by Don Schlesinger (*Blackjack Attack*, 3rd
ed.) as the 18 index plays with the **highest gain in EV** relative to perfect
basic strategy.  The gain is not uniform — the top few plays (especially
`16v10` and insurance) account for the majority of the additional edge.  The
Fab 4 add the four highest-value surrender deviations.

Together, these 22 deviations capture roughly **80–85%** of the total gain
achievable by using a complete index table.  They are widely considered the
standard minimum for a counting system used in practice.
