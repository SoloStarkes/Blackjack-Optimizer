# Game Engine

`backend/engine.py` is the core game-logic layer.  It is deliberately **pure** —
no I/O, no global state, no network access.  Randomness enters only through an
optional seed parameter.  Every other module calls into this one.

---

## Cards

Cards are represented as **integer ranks 1–13**:

| Rank | Meaning |
|---|---|
| 1 | Ace |
| 2–10 | Pip value |
| 11 | Jack |
| 12 | Queen |
| 13 | King |

The helper `card_value(rank)` converts a rank to its blackjack point value:
face cards (11, 12, 13) all return 10; ranks 1–9 return themselves.

```python
def card_value(card: int) -> int:
    if card >= 10:
        return 10
    return card   # 1 (Ace) or 2–9
```

---

## GameRules

`GameRules` is a plain dataclass that bundles all configurable rules for a
single game variant.  No methods — it is pure configuration.

```python
@dataclass
class GameRules:
    decks: int = 6           # 1, 2, 4, 6, or 8
    penetration: float = 0.75  # fraction of shoe dealt before reshuffle
    h17: bool = True         # dealer hits soft 17
    das: bool = True         # double after split allowed
    rsa: bool = True         # re-split aces allowed
    max_splits: int = 3      # maximum number of splits (giving max_splits+1 hands)
    surrender: bool = True   # late surrender allowed
    bj_payout: float = 1.5   # 1.5 = 3:2 payout; 1.2 = 6:5
```

The `GameRules` object is passed unchanged through every layer — the simulator,
strategy module, and engine all read from it.

---

## Shoe

`Shoe` models a shuffled multi-deck card shoe with a cut card.

### Initialisation

```python
class Shoe:
    def __init__(self, rules: GameRules, seed: Optional[int] = None) -> None:
        self.rules = rules
        self._seed = seed
        self._cards: List[int] = []
        self._position: int = 0
        self._cut_card: int = 0
        self._build_and_shuffle()
```

`_build_and_shuffle()`:
1. Builds `rules.decks × 52` cards as a list of ranks (each rank 1–13 appears
   4 × `rules.decks` times).
2. Shuffles with `random.Random(seed)` so results are reproducible.
3. Places the cut card at index `floor(total_cards × penetration)`.

### Dealing

`deal()` returns `self._cards[self._position]` and increments `_position`.
It raises `RuntimeError` if the shoe is exhausted (this should never happen
in normal play because the cut-card guard fires first).

### Cut card and reshuffling

`cut_card_reached()` returns `True` when `_position ≥ _cut_card`.  The
simulator checks this before every round.

`reshuffle(seed=None)` rebuilds and reshuffles the shoe.  If the shoe was
originally seeded, the seed is auto-incremented (shoe 0 uses seed 0, shoe 1
uses seed 1, etc.), ensuring each shoe is independently random but the overall
session is still reproducible.

```python
def reshuffle(self, seed: Optional[int] = None) -> None:
    if seed is not None:
        self._seed = seed
    elif self._seed is not None:
        self._seed += 1          # deterministic progression
    self._build_and_shuffle()
```

### The _CountingShoe subclass

`simulator.py` uses `_CountingShoe`, a thin subclass that overrides `deal()`
to call `counter.update(card)` on every dealt card.  The reshuffle also calls
`counter.reset()`.  This keeps the counter in sync automatically without the
simulator needing to track cards manually.

---

## Hand

`Hand` holds the cards for a single player or dealer hand.

```python
@dataclass
class Hand:
    cards: List[int] = field(default_factory=list)
    bet: float = 0.0
    doubled: bool = False      # True after a double-down
    surrendered: bool = False  # True after a surrender
    from_split: bool = False   # True for hands created by splitting
```

### `total()`

Blackjack hands can count an Ace as either 1 or 11.  `total()` returns the
**best possible total ≤ 21**.

```python
def total(self) -> int:
    hard_total = sum(card_value(c) for c in self.cards)
    aces = sum(1 for c in self.cards if c == 1)
    if aces > 0 and hard_total + 10 <= 21:
        return hard_total + 10   # count one Ace as 11
    return hard_total            # all Aces count as 1
```

Only **one** Ace can ever be counted as 11 — once the second Ace is added,
`hard_total` is already at least 12 (two aces = 12 hard), and `12 + 10 = 22`
would bust, so both must count as 1.

### `is_soft()`

Returns `True` when the hand contains a usable Ace (counted as 11).  Identical
logic to `total()` — the Ace is "usable" when counting it as 11 does not bust.

### `is_blackjack()`

```python
def is_blackjack(self) -> bool:
    return len(self.cards) == 2 and self.total() == 21
```

Requires **exactly 2 cards** totalling 21.  A 21 reached after hitting is not
a blackjack.

### `is_bust()`

`total() > 21`.

### `can_split()`

```python
def can_split(self) -> bool:
    if len(self.cards) != 2:
        return False
    return card_value(self.cards[0]) == card_value(self.cards[1])
```

A pair is defined by equal **point values** (not equal ranks): a Jack and a
Queen form a splittable pair because both have value 10.

---

## play_round

`play_round` is the top-level function that deals and resolves one complete
round.

```python
def play_round(
    shoe: Shoe,
    player_bet: float,
    rules: GameRules,
    strategy_fn: Callable[[Hand, int, GameRules], str],
) -> float:
```

### Deal order

Cards are dealt in standard US order:

1. Player card 1 (face up)
2. Dealer card 1 — **dealer_up** (face up)
3. Player card 2 (face up)
4. Dealer card 2 — **dealer_hole** (face down, peeked immediately)

### Dealer peek (US rules)

The dealer checks for blackjack before the player acts:

```python
dealer_bj = dealer_hand.is_blackjack()
player_bj = player_hand.is_blackjack()

if dealer_bj:
    return 0.0 if player_bj else -player_bet   # push or lose
if player_bj:
    return player_bet * rules.bj_payout         # 3:2 or 6:5
```

If neither has blackjack, play continues.

### Player actions via `_play_hand`

`_play_hand` is a recursive function that handles the full decision tree:

```python
def _play_hand(
    hand, shoe, dealer_up, rules, strategy_fn,
    split_count, is_split_aces
) -> List[Hand]:
```

On each iteration it calls `strategy_fn(hand, dealer_up, rules)` and dispatches
on the returned action string:

#### HIT
Append one card, continue the loop.

#### STAND
Return `[hand]` immediately.

#### DOUBLE
```python
if can_double:
    hand.bet *= 2.0
    hand.doubled = True
    hand.add_card(shoe.deal())
    return [hand]      # exactly one more card, then done
```
`can_double` requires exactly 2 cards and, for split hands, `rules.das = True`.
If doubling is not available, the fallback is HIT (or STAND for soft totals
where standing beats hitting).

#### SPLIT
```python
if can_split:
    h1 = Hand(cards=[c1], bet=hand.bet, from_split=True)
    h1.add_card(shoe.deal())   # one card each
    h2 = Hand(cards=[c2], bet=hand.bet, from_split=True)
    h2.add_card(shoe.deal())
    # recurse on both sub-hands
    return _play_hand(h1, …) + _play_hand(h2, …)
```

`can_split` is gated by:
- The pair condition (`can_split()` on the hand)
- `split_count < rules.max_splits` (maximum re-splits)
- Ace re-split: allowed only if `split_count == 0` (first split) or `rules.rsa`

**Split aces** (`splitting_aces = True`): each sub-hand receives exactly one
card and no further actions are permitted — `is_split_aces=True` causes
`_play_hand` to return immediately on the very first call.

If the split limit is exceeded, the action falls back to STAND.

#### SURRENDER
```python
if can_surrender:
    hand.surrendered = True
    return [hand]
```

`can_surrender` requires exactly 2 cards, `rules.surrender = True`, and the
hand must not be from a split (late surrender is not offered after splitting).
If surrender is not available, the engine treats it as STAND to avoid infinite
loops.

### Dealer play

Once the player is done, the dealer plays only if at least one player hand is
neither busted nor surrendered:

```python
all_resolved = all(h.is_bust() or h.surrendered for h in completed_hands)
if not all_resolved:
    _play_dealer(dealer_hand, shoe, rules)
```

`_play_dealer` hits until:
- `total > 17`
- `total == 17` and the hand is hard (always stand)
- `total == 17` and `rules.h17 = False` (S17: stand on soft 17 too)
- Under H17: dealer hits soft 17 and any total < 17

### Settlement via `_settle`

Each completed player hand is settled individually:

| Situation | Payout |
|---|---|
| Surrendered | `-bet / 2` |
| Busted | `-bet` |
| Natural BJ (non-split) | `+bet × bj_payout` |
| Dealer busted, player did not | `+bet` |
| Player total > dealer total | `+bet` |
| Player total < dealer total | `-bet` |
| Push | `0` |

`play_round` returns the **sum** of payouts across all split hands.

---

## Example: Split Hand Scenario

Suppose the player holds 8,8 against dealer 6, `rules.max_splits=3`, `rules.das=True`:

```
Round start: player=[8,8], dealer_up=6, dealer_hole=K (no peek blackjack)

_play_hand called with split_count=0:
  strategy returns SPLIT
  h1 = Hand([8]), deal → Hand([8, 5]) = 13
  h2 = Hand([8]), deal → Hand([8, J]) = 18

  _play_hand(h1=[8,5]=13, …, split_count=1):
    strategy returns STAND  →  return [Hand([8,5])]

  _play_hand(h2=[8,J]=18, …, split_count=1):
    strategy returns STAND  →  return [Hand([8,J])]

completed_hands = [Hand([8,5]), Hand([8,J])]
dealer plays: dealer=[6,K]=16 → hits → dealer=[6,K,7]=23 bust

_settle(Hand([8,5]), dealer) → +25  (dealer bust)
_settle(Hand([8,J]), dealer) → +25  (dealer bust)

return 50.0
```
