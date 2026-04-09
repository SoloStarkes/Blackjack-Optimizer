# Card Counting

`backend/counting.py` implements the Hi-Lo counting system: a running count
maintained across the shoe, a true-count conversion, and a vectorised NumPy
simulator that measures how often each true count appears.

---

## Hi-Lo System

Hi-Lo is a **balanced, level-1** counting system.  Every card dealt is assigned
a tag, and the player keeps a running mental sum:

| Card ranks | Tag | Intuition |
|---|---|---|
| 2, 3, 4, 5, 6 | **+1** | Low cards help the dealer; their removal helps the player |
| 7, 8, 9 | **0** | Neutral — no meaningful effect on the count |
| 10, J, Q, K, A | **−1** | High cards help the player; their removal hurts |

The system is *balanced* because a complete, unshuffled deck sums to zero
(20 low cards × +1) + (12 neutral × 0) + (20 high cards × −1) = 0.

```python
_HILO_TAGS = {
    1: -1,                                # Ace
    2: +1, 3: +1, 4: +1, 5: +1, 6: +1,  # low cards
    7:  0, 8:  0, 9:  0,                 # neutral
    10:-1, 11:-1, 12:-1, 13:-1,          # ten-value cards
}
```

### Example

Shoe starts: running count = 0.

Cards dealt: 5, K, 3, 9, 2, Q, A, 7, 6

| Card | Tag | Running count |
|---|---|---|
| 5 | +1 | +1 |
| K | −1 | 0 |
| 3 | +1 | +1 |
| 9 | 0 | +1 |
| 2 | +1 | +2 |
| Q | −1 | +1 |
| A | −1 | 0 |
| 7 | 0 | 0 |
| 6 | +1 | +1 |

Running count = +1 after these 9 cards.

---

## The Counter Class

```python
@dataclass
class Counter:
    running_count: int = field(default=0, init=False)

    def update(self, card: int) -> None:
        self.running_count += _HILO_TAGS[card]

    def true_count(self, decks_remaining: float) -> int:
        if decks_remaining <= 0:
            return 0
        return math.floor(self.running_count / decks_remaining)

    def reset(self) -> None:
        self.running_count = 0
```

`Counter` is stateful and mutated card-by-card during a shoe.  The simulator
uses `_CountingShoe` (a `Shoe` subclass) so `update()` is called automatically
on every `deal()`.

---

## True Count

The **running count** measures how many net low cards remain relative to high
cards.  But its significance depends on how many cards are left — a +6 running
count with 6 decks remaining is very different from a +6 with half a deck left.

The **true count** normalises for the remaining deck size:

```
true_count = floor(running_count / decks_remaining)
```

`decks_remaining = cards_remaining / 52`

The `floor` (toward −∞) matches standard Hi-Lo practice: a player claims a
positive edge only once a full integer-count advantage has been established.

### Example

- Shoe: 6 decks = 312 cards total
- Cards dealt so far: 160
- Cards remaining: 152
- Running count: +12
- `decks_remaining = 152 / 52 ≈ 2.92`
- `true_count = floor(12 / 2.92) = floor(4.11) = 4`

A true count of +4 means roughly a **+2% player edge** using the rule of thumb
that each true-count unit adds ~0.5% to the base game edge.

---

## True Count Frequencies

`true_count_frequencies(num_decks, penetration, num_shoes, seed)` answers the
question: *if I sit down at this shoe and play until the cut card, what
fraction of hands will I encounter at each true count?*

This distribution is the foundation for EV calculation:

```
EV = Σ over all TC:  frequency(TC) × edge(TC) × bet(TC)
```

### How it works

The function is fully **vectorised with NumPy** — no Python loops over cards.

```python
# 1. Build a template of Hi-Lo tags for one shoe
shoe_template = np.tile(_ONE_DECK_TAGS, num_decks)   # shape (total_cards,)

# 2. Create a (num_shoes, total_cards) matrix; shuffle each row independently
all_shoes = np.empty((num_shoes, total_cards), dtype=np.int8)
all_shoes[:] = shoe_template
all_shoes = rng.permuted(all_shoes, axis=1)

# 3. Cumulative sum along axis=1 gives the running count at every position
running_counts = np.cumsum(all_shoes, axis=1, dtype=np.int16)

# 4. Sample at positions 0, cards_per_sample, 2*cps, … up to the cut card
sample_positions = np.arange(cards_per_sample, cut_pos, cards_per_sample)

# 5. Compute decks_remaining and vectorised true-count
rc_matrix  = running_counts[:, sample_positions - 1]   # (num_shoes, n_samples)
decks_rem  = (total_cards - sample_positions) / 52.0   # (n_samples,)
tc_matrix  = np.floor(rc_matrix / decks_rem)           # (num_shoes, n_samples)

# 6. Count frequencies
unique, counts = np.unique(tc_matrix.ravel(), return_counts=True)
```

`cards_per_sample=4` means "sample the true count every 4 cards", which
approximates the average number of cards consumed per hand in a heads-up game.

### Why the frequency distribution matters

Consider two bet spreads:

| True Count | Bet | Frequency (6-deck, 75% pen) |
|---|---|---|
| ≤ 0 | $0 (wong out) | ~67% |
| +1 | $25 | ~18% |
| +2 | $50 | ~8% |
| +3 | $100 | ~4% |
| +4 | $150 | ~2% |
| +5+ | $200 | ~1% |

Even though you only bet $200 at TC+5, that count only arises ~1% of the time.
The frequency-weighted average determines actual EV and risk.

The distribution is also roughly symmetric for a balanced system — negative
counts mirror positive counts — but wonging out removes the negative-count
hands, skewing the played-hands distribution toward positive counts.

### Practical accuracy

For 6-deck 75% penetration:

| `num_shoes` | Run time (approx.) | Accuracy |
|---|---|---|
| 10 000 | < 1 second | Sufficient for Kelly bets |
| 100 000 | ~2 seconds | Good for academic analysis |
| 1 000 000 | ~20 seconds | Very precise |

The function uses `int8` for tags and `int16` for cumulative sums, keeping
memory usage reasonable (~90 MB for 100 000 six-deck shoes).
