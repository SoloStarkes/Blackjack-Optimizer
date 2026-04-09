"""
test_counting.py — Unit tests for backend/counting.py.

Covers:
- hilo_tag():        correct tag for every rank
- Counter.update():  running count with known card sequences
- Counter.true_count(): flooring behaviour (positive and negative)
- Counter.reset():   state cleared correctly
- true_count_frequencies(): output shape, normalisation, distributional properties
"""

from __future__ import annotations

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.counting import Counter, hilo_tag, true_count_frequencies


# ---------------------------------------------------------------------------
# hilo_tag
# ---------------------------------------------------------------------------

class TestHiloTag:
    def test_ace_is_minus_one(self):
        assert hilo_tag(1) == -1

    def test_low_cards_are_plus_one(self):
        for rank in [2, 3, 4, 5, 6]:
            assert hilo_tag(rank) == +1, f"rank {rank} should be +1"

    def test_neutral_cards_are_zero(self):
        for rank in [7, 8, 9]:
            assert hilo_tag(rank) == 0, f"rank {rank} should be 0"

    def test_ten_is_minus_one(self):
        assert hilo_tag(10) == -1

    def test_jack_is_minus_one(self):
        assert hilo_tag(11) == -1

    def test_queen_is_minus_one(self):
        assert hilo_tag(12) == -1

    def test_king_is_minus_one(self):
        assert hilo_tag(13) == -1

    def test_full_deck_sums_to_zero(self):
        """A balanced shoe: all 52 cards of one deck must sum to zero."""
        total = sum(hilo_tag(rank) for rank in range(1, 14) for _ in range(4))
        assert total == 0

    def test_invalid_rank_raises(self):
        with pytest.raises(KeyError):
            hilo_tag(0)
        with pytest.raises(KeyError):
            hilo_tag(14)


# ---------------------------------------------------------------------------
# Counter — running count
# ---------------------------------------------------------------------------

class TestCounterInitial:
    def test_running_count_starts_at_zero(self):
        assert Counter().running_count == 0


class TestCounterUpdate:
    def test_single_low_card_increments(self):
        c = Counter()
        c.update(5)
        assert c.running_count == 1

    def test_single_high_card_decrements(self):
        c = Counter()
        c.update(10)
        assert c.running_count == -1

    def test_single_neutral_card_no_change(self):
        c = Counter()
        c.update(8)
        assert c.running_count == 0

    def test_all_low_cards(self):
        c = Counter()
        for rank in [2, 3, 4, 5, 6]:
            c.update(rank)
        assert c.running_count == 5

    def test_all_neutral_cards(self):
        c = Counter()
        for rank in [7, 8, 9]:
            c.update(rank)
        assert c.running_count == 0

    def test_all_high_cards(self):
        c = Counter()
        for rank in [1, 10, 11, 12, 13]:   # A, 10, J, Q, K
            c.update(rank)
        assert c.running_count == -5

    def test_known_sequence_step_by_step(self):
        """
        Sequence: 2, 5, 6, 10, 1, 7, 8, 3
        Tags:    +1,+1,+1, -1,-1, 0, 0,+1
        Cumulative:  1, 2, 3,  2, 1, 1, 1, 2
        """
        c = Counter()
        expected = [1, 2, 3, 2, 1, 1, 1, 2]
        for card, exp in zip([2, 5, 6, 10, 1, 7, 8, 3], expected):
            c.update(card)
            assert c.running_count == exp, (
                f"after card {card}: expected RC={exp}, got {c.running_count}"
            )

    def test_face_cards_decrement(self):
        """Jack (11), Queen (12), King (13) all count as high cards."""
        c = Counter()
        c.update(11)
        assert c.running_count == -1
        c.update(12)
        assert c.running_count == -2
        c.update(13)
        assert c.running_count == -3

    def test_full_deck_running_count_zero(self):
        """Dealing every card in a deck returns the count to zero."""
        c = Counter()
        for rank in range(1, 14):
            for _ in range(4):       # four suits
                c.update(rank)
        assert c.running_count == 0

    def test_two_decks_running_count_zero(self):
        c = Counter()
        for rank in range(1, 14):
            for _ in range(8):       # 2 decks = 8 suits
                c.update(rank)
        assert c.running_count == 0

    def test_running_count_accumulates_across_calls(self):
        c = Counter()
        c.update(2)   # +1
        c.update(13)  # -1
        c.update(4)   # +1
        c.update(9)   #  0
        c.update(1)   # -1
        assert c.running_count == 0


# ---------------------------------------------------------------------------
# Counter — true count
# ---------------------------------------------------------------------------

class TestCounterTrueCount:
    def _counter_with_rc(self, rc: int) -> Counter:
        """Build a Counter with the given running count by dealing low cards."""
        c = Counter()
        if rc > 0:
            for _ in range(rc):
                c.update(2)    # each +1
        elif rc < 0:
            for _ in range(-rc):
                c.update(10)   # each -1
        return c

    def test_true_count_zero_when_rc_zero(self):
        c = Counter()
        assert c.true_count(3.0) == 0

    def test_true_count_exact_integer(self):
        """RC=6, decks=3 → floor(6/3) = 2."""
        c = self._counter_with_rc(6)
        assert c.true_count(3.0) == 2

    def test_true_count_floors_positive(self):
        """RC=5, decks=2.5 → floor(2.0) = 2."""
        c = self._counter_with_rc(5)
        assert c.true_count(2.5) == 2

    def test_true_count_floors_down_not_round(self):
        """RC=7, decks=4 → floor(1.75) = 1 (not 2)."""
        c = self._counter_with_rc(7)
        assert c.true_count(4.0) == 1

    def test_true_count_floors_negative(self):
        """RC=−3, decks=2 → floor(−1.5) = −2 (NOT −1)."""
        c = self._counter_with_rc(-3)
        assert c.true_count(2.0) == -2

    def test_true_count_negative_exact(self):
        """RC=−4, decks=2 → floor(−2) = −2."""
        c = self._counter_with_rc(-4)
        assert c.true_count(2.0) == -2

    def test_true_count_negative_floors_away_from_zero(self):
        """Confirm floor semantics: −0.1 → −1 (not 0)."""
        c = self._counter_with_rc(-1)
        # decks=20 → -1/20 = -0.05 → floor = -1
        assert c.true_count(20.0) == -1

    def test_true_count_half_deck(self):
        """RC=2, decks=0.5 → floor(4.0) = 4."""
        c = self._counter_with_rc(2)
        assert c.true_count(0.5) == 4

    def test_true_count_large_decks_rounds_toward_zero(self):
        """RC=1, decks=6 → floor(0.166…) = 0."""
        c = self._counter_with_rc(1)
        assert c.true_count(6.0) == 0

    def test_true_count_zero_decks_returns_zero(self):
        """Guard against division by zero."""
        c = self._counter_with_rc(10)
        assert c.true_count(0.0) == 0

    def test_true_count_negative_decks_returns_zero(self):
        c = self._counter_with_rc(5)
        assert c.true_count(-1.0) == 0

    def test_true_count_consistent_with_math_floor(self):
        """Spot-check against math.floor for several RC/decks pairs."""
        cases = [
            (5, 2.0),   # floor(2.5)  = 2
            (5, 3.0),   # floor(1.67) = 1
            (-5, 2.0),  # floor(-2.5) = -3
            (-5, 3.0),  # floor(-1.67)= -2
            (10, 1.0),  # floor(10)   = 10
        ]
        for rc, decks in cases:
            c = Counter()
            # manually set running_count via object attribute for precise control
            c.running_count = rc
            expected = math.floor(rc / decks)
            assert c.true_count(decks) == expected, (
                f"RC={rc}, decks={decks}: expected {expected}, "
                f"got {c.true_count(decks)}"
            )


# ---------------------------------------------------------------------------
# Counter — reset
# ---------------------------------------------------------------------------

class TestCounterReset:
    def test_reset_zeroes_running_count(self):
        c = Counter()
        for _ in range(10):
            c.update(2)
        c.reset()
        assert c.running_count == 0

    def test_reset_then_count_works(self):
        c = Counter()
        c.update(2)   # RC = 1
        c.reset()
        c.update(10)  # RC = -1
        assert c.running_count == -1

    def test_multiple_resets_idempotent(self):
        c = Counter()
        c.reset()
        c.reset()
        assert c.running_count == 0

    def test_true_count_zero_after_reset(self):
        c = Counter()
        c.update(3)   # RC = 1
        c.reset()
        assert c.true_count(3.0) == 0


# ---------------------------------------------------------------------------
# Counter integration: simulated shoe with known seed
# ---------------------------------------------------------------------------

class TestCounterShoeSimulation:
    """Simulate a deterministic shoe and verify running/true count at checkpoints."""

    def test_six_deck_shoe_finishes_at_zero(self):
        """Dealing every card of a 6-deck shoe returns the count to zero."""
        c = Counter()
        for rank in range(1, 14):
            for _ in range(6 * 4):   # 6 decks × 4 suits
                c.update(rank)
        assert c.running_count == 0

    def test_checkpoint_after_hot_sequence(self):
        """After 10 consecutive low cards: RC=+10, TC with 5 decks = floor(2)=2."""
        c = Counter()
        for _ in range(10):
            c.update(2)
        assert c.running_count == 10
        assert c.true_count(5.0) == 2

    def test_checkpoint_after_cold_sequence(self):
        """After 10 consecutive high cards: RC=−10, TC with 4 decks = floor(−2.5)=−3."""
        c = Counter()
        for _ in range(10):
            c.update(10)
        assert c.running_count == -10
        assert c.true_count(4.0) == -3

    def test_specific_hand_sequence(self):
        """
        Simulate a heads-up hand: player [6,5] dealer [K,9] + dealer hit [3].
        Cards seen in order: 6, K, 5, 9, 3
        Tags:               +1,-1,+1, 0,+1  → RC = 2
        """
        c = Counter()
        for card in [6, 13, 5, 9, 3]:   # 6, K, 5, 9, 3
            c.update(card)
        assert c.running_count == 2

    def test_counter_tracks_over_multiple_hands(self):
        """Running count accumulates correctly across a sequence of hands."""
        c = Counter()
        hands = [
            [2, 10, 5, 1],   # +1,-1,+1,-1 → net 0, cumulative RC = 0
            [3, 11, 6, 12],  # +1,-1,+1,-1 → net 0, cumulative RC = 0
            [4,  7, 8, 13],  # +1, 0, 0,-1 → net 0, cumulative RC = 0
        ]
        for hand in hands:
            for card in hand:
                c.update(card)
        assert c.running_count == 0

    def test_counter_resets_between_shoes(self):
        c = Counter()
        for _ in range(20):
            c.update(2)   # RC = 20
        c.reset()         # new shoe
        c.update(10)      # RC = -1
        assert c.running_count == -1
        assert c.true_count(5.0) == math.floor(-1 / 5.0)


# ---------------------------------------------------------------------------
# true_count_frequencies
# ---------------------------------------------------------------------------

class TestTrueCountFrequencies:
    """Statistical tests for the Monte Carlo TC distribution.

    Uses num_shoes=5000 for speed while remaining statistically sound.
    """

    SHOES = 5_000
    SEED  = 42

    def _freq(self, num_decks=6, pen=0.75, **kw):
        return true_count_frequencies(
            num_decks, pen, num_shoes=self.SHOES, seed=self.SEED, **kw
        )

    # --- structural properties ---

    def test_returns_dict(self):
        assert isinstance(self._freq(), dict)

    def test_keys_are_integers(self):
        freq = self._freq()
        for k in freq:
            assert isinstance(k, int)

    def test_values_are_floats(self):
        freq = self._freq()
        for v in freq.values():
            assert isinstance(v, float)

    def test_frequencies_sum_to_one(self):
        freq = self._freq()
        total = sum(freq.values())
        assert abs(total - 1.0) < 1e-6, f"sum = {total}"

    def test_all_frequencies_positive(self):
        for v in self._freq().values():
            assert v > 0

    # --- distributional properties ---

    def test_tc_zero_is_present(self):
        assert 0 in self._freq()

    def test_tc_zero_most_common(self):
        """TC=0 should be the most frequent true count in a balanced shoe."""
        freq = self._freq()
        assert freq[0] == max(freq.values())

    def test_distribution_covers_positive_and_negative(self):
        freq = self._freq()
        assert any(k > 0 for k in freq)
        assert any(k < 0 for k in freq)

    def test_distribution_skews_negative_due_to_floor(self):
        """floor(RC/decks) biases the distribution negative.

        Any RC < 0, no matter how small, gives TC ≤ −1; a comparably small
        positive RC gives TC = 0.  So P(TC < 0) > P(TC > 0) is expected and
        correct — this is a mathematical property of the floor function, not
        a bug.  We simply verify the bias direction.
        """
        freq = self._freq()
        pos = sum(v for k, v in freq.items() if k > 0)
        neg = sum(v for k, v in freq.items() if k < 0)
        assert neg > pos, f"floor bias: expected neg > pos, got pos={pos:.3f} neg={neg:.3f}"

    def test_extreme_counts_rare(self):
        """TCs beyond ±10 should collectively account for < 2% of rounds."""
        freq = self._freq()
        extreme = sum(v for k, v in freq.items() if abs(k) > 10)
        assert extreme < 0.02, f"extreme TC frequency = {extreme:.4f}"

    def test_core_range_covers_most_rounds(self):
        """TCs in [−5, +5] should cover > 90% of rounds for a 6-deck shoe."""
        freq = self._freq()
        core = sum(v for k, v in freq.items() if -5 <= k <= 5)
        assert core > 0.90, f"core [-5,+5] coverage = {core:.3f}"

    # --- reproducibility ---

    def test_seed_reproducibility(self):
        f1 = true_count_frequencies(6, 0.75, num_shoes=1_000, seed=7)
        f2 = true_count_frequencies(6, 0.75, num_shoes=1_000, seed=7)
        assert f1 == f2

    def test_different_seeds_differ(self):
        f1 = true_count_frequencies(6, 0.75, num_shoes=1_000, seed=1)
        f2 = true_count_frequencies(6, 0.75, num_shoes=1_000, seed=2)
        # At least one frequency value differs
        all_keys = set(f1) | set(f2)
        assert any(f1.get(k, 0) != f2.get(k, 0) for k in all_keys)

    # --- parameter sensitivity ---

    def test_higher_penetration_wider_distribution(self):
        """Deeper penetration → more true-count spread → lower P(TC=0)."""
        low_pen  = self._freq(pen=0.50)
        high_pen = self._freq(pen=0.90)
        assert high_pen[0] < low_pen[0], (
            "higher penetration should reduce P(TC=0) via wider distribution"
        )

    def test_more_decks_narrower_distribution(self):
        """More decks → count fluctuates less per card → narrower spread."""
        freq_1d = true_count_frequencies(1, 0.75, num_shoes=self.SHOES, seed=self.SEED)
        freq_6d = self._freq(num_decks=6)
        # P(TC=0) should be higher for 6 decks (less variance per card)
        assert freq_6d[0] > freq_1d[0], (
            "6-deck shoe should have more rounds at TC=0 than single-deck"
        )

    def test_degenerate_penetration_returns_zero(self):
        """Very low penetration → no full round fits → only TC=0."""
        freq = true_count_frequencies(6, 0.01, num_shoes=100, seed=0)
        assert freq == {0: 1.0}

    def test_cards_per_sample_affects_sample_count(self):
        """Finer sampling (smaller stride) should not change TC=0 dominance."""
        freq = true_count_frequencies(6, 0.75, num_shoes=self.SHOES, seed=self.SEED,
                                      cards_per_sample=2)
        assert 0 in freq
        assert freq[0] == max(freq.values())
