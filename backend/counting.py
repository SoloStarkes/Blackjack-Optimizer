"""
counting.py — Hi-Lo card counting: running count, true count, and TC distribution.

Hi-Lo system tags:
  2–6  → +1  (low cards favour the player when gone)
  7–9  →  0  (neutral)
  10/J/Q/K/A → −1  (high cards favour the player when present)

Public surface:
    hilo_tag                 — tag for a single card rank
    Counter                  — stateful running/true-count tracker
    true_count_frequencies   — Monte Carlo TC distribution (vectorised NumPy)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Hi-Lo tag lookup
# ---------------------------------------------------------------------------

# Index by rank 1-13; rank 0 is unused (padding makes the array 1-based).
_HILO_TAGS: Dict[int, int] = {
    1:  -1,                               # Ace
    2:  +1, 3: +1, 4: +1, 5: +1, 6: +1,  # low cards
    7:   0, 8:  0, 9:  0,                 # neutral
    10: -1, 11: -1, 12: -1, 13: -1,       # ten-value cards (10, J, Q, K)
}


def hilo_tag(card: int) -> int:
    """Return the Hi-Lo count tag for a card rank.

    Args:
        card: Integer rank 1–13 (1=Ace, 11=Jack, 12=Queen, 13=King).

    Returns:
        +1 for low cards (2–6), 0 for neutral (7–9), −1 for high cards (10–A).

    Raises:
        KeyError: If ``card`` is outside the range 1–13.
    """
    return _HILO_TAGS[card]


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------

@dataclass
class Counter:
    """Stateful Hi-Lo running-count and true-count tracker.

    Typical usage::

        counter = Counter()
        for card in dealt_cards:
            counter.update(card)
        tc = counter.true_count(shoe.cards_remaining() / 52)

    Attributes:
        running_count: Cumulative Hi-Lo count since the last reset().
    """

    running_count: int = field(default=0, init=False)

    def update(self, card: int) -> None:
        """Apply the Hi-Lo tag for a newly seen card to the running count.

        Args:
            card: Integer rank 1–13 of the card just dealt.
        """
        self.running_count += _HILO_TAGS[card]

    def true_count(self, decks_remaining: float) -> int:
        """Return the true count: running count per deck remaining, floored.

        Flooring (toward −∞) matches standard Hi-Lo practice and ensures
        the player only claims a positive edge once a full integer-count
        advantage has been established.

        Args:
            decks_remaining: Decks still in the shoe (``cards_left / 52``).
                             Returns 0 if this is ≤ 0.

        Returns:
            ``math.floor(running_count / decks_remaining)`` as an ``int``.
        """
        if decks_remaining <= 0:
            return 0
        return math.floor(self.running_count / decks_remaining)

    def reset(self) -> None:
        """Reset the running count to zero for the start of a new shoe."""
        self.running_count = 0


# ---------------------------------------------------------------------------
# Vectorised TC frequency distribution
# ---------------------------------------------------------------------------

# NumPy Hi-Lo tags for ranks 1–13 (one entry per rank, each appearing ×4).
# Tiling this 4× gives one complete deck of 52 Hi-Lo tags.
_RANK_TAGS_NP: np.ndarray = np.array(
    [-1, 1, 1, 1, 1, 1, 0, 0, 0, -1, -1, -1, -1],   # ranks 1-13
    dtype=np.int8,
)
_ONE_DECK_TAGS: np.ndarray = np.repeat(_RANK_TAGS_NP, 4)  # 52 tags


def true_count_frequencies(
    num_decks: int,
    penetration: float,
    num_shoes: int = 100_000,
    seed: Optional[int] = None,
    cards_per_sample: int = 4,
) -> Dict[int, float]:
    """Simulate many shoes and return the empirical true-count distribution.

    At the start of each simulated round (every ``cards_per_sample`` cards
    into the shoe, up to the cut card) the integer true count is recorded.
    The resulting frequency table is the distribution of true counts a
    player encounters when a new hand begins — the essential input for
    EV, standard-deviation, and risk-of-ruin calculations.

    Uses a fully-vectorised NumPy implementation: 100 000 six-deck shoes
    complete in under two seconds on a modern laptop.

    Args:
        num_decks: Number of decks in the shoe (e.g., 6).
        penetration: Fraction of shoe dealt before reshuffling (0.0–1.0).
        num_shoes: Number of shoes to simulate (higher → more accurate).
        seed: Optional RNG seed for reproducibility.
        cards_per_sample: Cards between consecutive TC samples (approximates
                          the average number of cards consumed per hand).

    Returns:
        ``{true_count: frequency}`` where each frequency is in [0, 1] and
        all values sum to 1.0.  Keys are ``int`` (floored true counts).

    Note:
        Memory usage is approximately
        ``num_shoes × num_decks × 52 × 3`` bytes (int8 shoe + int16 cumsum).
        For 100 000 six-deck shoes this is roughly 90 MB.
    """
    rng = np.random.default_rng(seed)

    total_cards = 52 * num_decks
    cut_pos = int(total_cards * penetration)  # first un-dealt card index

    # ── build shoe matrix ──────────────────────────────────────────────────
    shoe_template = np.tile(_ONE_DECK_TAGS, num_decks)        # (total_cards,)

    # Shape (num_shoes, total_cards); each row is an independent shuffle.
    all_shoes = np.empty((num_shoes, total_cards), dtype=np.int8)
    all_shoes[:] = shoe_template
    all_shoes = rng.permuted(all_shoes, axis=1)               # shuffle rows

    # ── running counts ─────────────────────────────────────────────────────
    # running_counts[s, i] = Hi-Lo count for shoe s *after* card i is dealt.
    # int16 is sufficient: |RC| ≤ 4 × num_decks × 5 ≤ 160 for 8 decks.
    running_counts = np.cumsum(all_shoes, axis=1, dtype=np.int16)
    # shape: (num_shoes, total_cards)

    # ── sample positions ───────────────────────────────────────────────────
    # Before round 0: zero cards dealt, RC = 0, TC = 0 always → handle separately.
    # Before round k (k ≥ 1): k * cards_per_sample cards dealt.
    sample_positions = np.arange(cards_per_sample, cut_pos, cards_per_sample)
    # Each element p means "p cards have been dealt; the (p+1)-th card is next."

    if sample_positions.size == 0:
        # Penetration so shallow no full round fits before the cut card.
        return {0: 1.0}

    # ── vectorised true-count computation ─────────────────────────────────
    # RC at position p = running_counts[:, p-1]  (0-based indexing)
    rc_matrix = running_counts[:, sample_positions - 1].astype(np.float32)
    # shape: (num_shoes, n_samples)

    decks_rem = (total_cards - sample_positions) / 52.0   # (n_samples,)

    # floor(RC / decks_remaining): broadcast (num_shoes, n) / (n,)
    tc_matrix = np.floor(rc_matrix / decks_rem).astype(np.int32)
    # shape: (num_shoes, n_samples)

    # Prepend the round-0 column: TC = 0 for every shoe at start of shoe.
    tc_zero = np.zeros((num_shoes, 1), dtype=np.int32)
    tc_all = np.concatenate([tc_zero, tc_matrix], axis=1)
    # shape: (num_shoes, n_samples + 1)

    # ── frequency table ────────────────────────────────────────────────────
    tc_flat = tc_all.ravel()
    unique, counts = np.unique(tc_flat, return_counts=True)
    total = int(tc_flat.size)
    return {int(u): float(c) / total for u, c in zip(unique, counts)}
