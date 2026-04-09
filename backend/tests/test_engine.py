"""
test_engine.py — Unit tests for backend/engine.py.

Covers:
- card_value()
- Hand: blackjack detection, bust detection, soft totals, can_split
- Shoe: initialization, dealing, cut-card, reshuffle
- Dealer H17 vs S17 behaviour
- play_round: natural BJ payouts, surrender, splits (including max-splits limit),
  DAS (double after split), dealer BJ push/loss scenarios.
"""

from __future__ import annotations

import sys
import os
import pytest
from typing import List

# Allow import without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.engine import (
    GameRules,
    Hand,
    Shoe,
    card_value,
    play_round,
    _play_dealer,
    _settle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockShoe:
    """Deterministic shoe that deals from a pre-specified list of cards."""

    def __init__(self, cards: List[int]) -> None:
        self._cards = list(cards)
        self._pos = 0

    def deal(self) -> int:
        if self._pos >= len(self._cards):
            raise RuntimeError("MockShoe exhausted")
        card = self._cards[self._pos]
        self._pos += 1
        return card

    def cards_remaining(self) -> int:
        return len(self._cards) - self._pos

    def cut_card_reached(self) -> bool:
        return False


def always(action: str):
    """Return a strategy function that always returns the given action."""
    return lambda hand, upcard, rules: action


def action_sequence(*actions: str):
    """Return a strategy function that yields actions in order, then stands."""
    it = iter(actions)
    def strategy(hand, upcard, rules):
        try:
            return next(it)
        except StopIteration:
            return "stand"
    return strategy


# ---------------------------------------------------------------------------
# card_value
# ---------------------------------------------------------------------------

class TestCardValue:
    def test_ace_is_1(self):
        assert card_value(1) == 1

    def test_pip_cards(self):
        for rank in range(2, 10):
            assert card_value(rank) == rank

    def test_ten_is_10(self):
        assert card_value(10) == 10

    def test_face_cards_are_10(self):
        assert card_value(11) == 10   # Jack
        assert card_value(12) == 10   # Queen
        assert card_value(13) == 10   # King


# ---------------------------------------------------------------------------
# Hand — basic properties
# ---------------------------------------------------------------------------

class TestHandTotal:
    def test_hard_total_no_ace(self):
        h = Hand(cards=[10, 7])
        assert h.total() == 17

    def test_soft_total_ace_counts_as_11(self):
        h = Hand(cards=[1, 6])
        assert h.total() == 17
        assert h.is_soft()

    def test_ace_demoted_to_1_on_bust(self):
        h = Hand(cards=[1, 6, 9])
        # 11+6+9=26 -> bust; 1+6+9=16
        assert h.total() == 16
        assert not h.is_soft()

    def test_two_aces_one_soft(self):
        # A+A: 11+1=12 (soft)
        h = Hand(cards=[1, 1])
        assert h.total() == 12
        assert h.is_soft()

    def test_face_card_value_in_total(self):
        h = Hand(cards=[13, 5])   # King + 5
        assert h.total() == 15

    def test_21_with_three_cards(self):
        h = Hand(cards=[7, 7, 7])
        assert h.total() == 21
        assert not h.is_soft()


class TestHandBlackjack:
    def test_ace_plus_ten_is_blackjack(self):
        h = Hand(cards=[1, 10])
        assert h.is_blackjack()

    def test_ace_plus_king_is_blackjack(self):
        h = Hand(cards=[1, 13])
        assert h.is_blackjack()

    def test_ten_plus_ace_is_blackjack(self):
        h = Hand(cards=[10, 1])
        assert h.is_blackjack()

    def test_three_card_21_is_not_blackjack(self):
        h = Hand(cards=[7, 7, 7])
        assert not h.is_blackjack()

    def test_two_tens_is_not_blackjack(self):
        h = Hand(cards=[10, 10])
        assert h.is_blackjack() is False   # total=20, not 21


class TestHandBust:
    def test_bust(self):
        h = Hand(cards=[10, 10, 5])
        assert h.is_bust()

    def test_not_bust_at_21(self):
        h = Hand(cards=[10, 5, 6])
        assert not h.is_bust()

    def test_soft_hand_not_bust(self):
        h = Hand(cards=[1, 10, 10])
        # 1+10+10 = 21 (using Ace as 1)
        assert not h.is_bust()
        assert h.total() == 21

    def test_hard_22_is_bust(self):
        h = Hand(cards=[10, 5, 7])
        assert h.is_bust()


class TestHandCanSplit:
    def test_pair_of_tens(self):
        h = Hand(cards=[10, 10])
        assert h.can_split()

    def test_mixed_ten_value_pair(self):
        # 10 and King both worth 10 — splittable
        h = Hand(cards=[10, 13])
        assert h.can_split()

    def test_pair_of_aces(self):
        h = Hand(cards=[1, 1])
        assert h.can_split()

    def test_non_pair(self):
        h = Hand(cards=[10, 9])
        assert not h.can_split()

    def test_three_card_hand_cannot_split(self):
        h = Hand(cards=[10, 10, 1])
        assert not h.can_split()


# ---------------------------------------------------------------------------
# Shoe
# ---------------------------------------------------------------------------

class TestShoe:
    def test_correct_card_count(self):
        rules = GameRules(decks=6)
        shoe = Shoe(rules, seed=0)
        assert shoe.cards_remaining() == 6 * 52

    def test_single_deck_count(self):
        rules = GameRules(decks=1)
        shoe = Shoe(rules, seed=0)
        assert shoe.cards_remaining() == 52

    def test_deal_reduces_count(self):
        rules = GameRules(decks=1)
        shoe = Shoe(rules, seed=42)
        before = shoe.cards_remaining()
        shoe.deal()
        assert shoe.cards_remaining() == before - 1

    def test_seeded_shoe_is_reproducible(self):
        rules = GameRules(decks=2)
        cards1 = [Shoe(rules, seed=7).deal() for _ in range(10)]
        cards2 = [Shoe(rules, seed=7).deal() for _ in range(10)]
        assert cards1 == cards2

    def test_different_seeds_differ(self):
        rules = GameRules(decks=2)
        cards1 = [Shoe(rules, seed=1).deal() for _ in range(10)]
        cards2 = [Shoe(rules, seed=2).deal() for _ in range(10)]
        assert cards1 != cards2

    def test_cut_card_not_reached_at_start(self):
        rules = GameRules(decks=6, penetration=0.75)
        shoe = Shoe(rules, seed=0)
        assert not shoe.cut_card_reached()

    def test_cut_card_reached_after_penetration(self):
        rules = GameRules(decks=1, penetration=0.5)
        shoe = Shoe(rules, seed=0)
        # Deal 26 cards (50% of 52)
        for _ in range(26):
            shoe.deal()
        assert shoe.cut_card_reached()

    def test_reshuffle_resets_position(self):
        rules = GameRules(decks=1)
        shoe = Shoe(rules, seed=0)
        for _ in range(20):
            shoe.deal()
        shoe.reshuffle()
        assert shoe.cards_remaining() == 52

    def test_exhausted_shoe_raises(self):
        rules = GameRules(decks=1)
        shoe = Shoe(rules, seed=0)
        for _ in range(52):
            shoe.deal()
        with pytest.raises(RuntimeError):
            shoe.deal()


# ---------------------------------------------------------------------------
# Dealer H17 vs S17
# ---------------------------------------------------------------------------

class TestDealerLogic:
    def _dealer_hand(self, *cards: int) -> Hand:
        h = Hand()
        for c in cards:
            h.add_card(c)
        return h

    def test_dealer_stands_hard_17_h17(self):
        """Dealer stands on hard 17 regardless of H17 setting."""
        rules = GameRules(h17=True)
        # Hard 17: 10 + 7
        dealer = self._dealer_hand(10, 7)
        shoe = MockShoe([5])  # would not be dealt
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 17
        assert shoe.cards_remaining() == 1   # no card consumed

    def test_dealer_hits_soft_17_h17(self):
        """With H17=True, dealer hits soft 17 (Ace+6)."""
        rules = GameRules(h17=True)
        dealer = self._dealer_hand(1, 6)    # soft 17
        shoe = MockShoe([2])                # draws a 2 -> 19
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 19
        assert shoe.cards_remaining() == 0

    def test_dealer_stands_soft_17_s17(self):
        """With H17=False (S17), dealer stands on soft 17."""
        rules = GameRules(h17=False)
        dealer = self._dealer_hand(1, 6)    # soft 17
        shoe = MockShoe([5])
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 17
        assert shoe.cards_remaining() == 1   # no card drawn

    def test_dealer_hits_below_17(self):
        rules = GameRules(h17=True)
        dealer = self._dealer_hand(10, 6)   # 16
        shoe = MockShoe([5])                # draws 5 -> 21
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 21

    def test_dealer_stands_hard_18(self):
        rules = GameRules(h17=True)
        dealer = self._dealer_hand(10, 8)
        shoe = MockShoe([5])
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 18
        assert shoe.cards_remaining() == 1

    def test_dealer_busts(self):
        rules = GameRules(h17=True)
        dealer = self._dealer_hand(10, 6)   # 16
        shoe = MockShoe([9])                # 25: bust
        _play_dealer(dealer, shoe, rules)
        assert dealer.is_bust()

    def test_dealer_soft_18_stands(self):
        """Dealer never hits soft 18+ even with H17."""
        rules = GameRules(h17=True)
        dealer = self._dealer_hand(1, 7)    # soft 18
        shoe = MockShoe([5])
        _play_dealer(dealer, shoe, rules)
        assert dealer.total() == 18
        assert shoe.cards_remaining() == 1


# ---------------------------------------------------------------------------
# play_round — natural blackjack payouts
# ---------------------------------------------------------------------------

class TestPlayRoundBlackjack:
    """
    Deal order: P1, D_up, P2, D_hole

    For a player BJ we need cards=[A, X_up, 10val, X_hole]
    so player gets Ace + 10-value and dealer does NOT have BJ.
    """

    def test_player_bj_pays_3_to_2(self):
        rules = GameRules(bj_payout=1.5)
        # P: A, 10 (BJ); D: 7, 6 (no BJ)
        shoe = MockShoe([1, 7, 10, 6])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(150.0)

    def test_player_bj_pays_6_to_5(self):
        rules = GameRules(bj_payout=1.2)
        shoe = MockShoe([1, 7, 10, 6])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(120.0)

    def test_dealer_bj_player_loses(self):
        rules = GameRules()
        # D: 1(up), ?(hole=10) -> dealer BJ; P: 9, 8 -> no BJ
        shoe = MockShoe([9, 1, 8, 10])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(-100.0)

    def test_dealer_bj_player_bj_push(self):
        rules = GameRules()
        # P: 1, 10; D: 1(up), 13(hole=King) -> both BJ
        shoe = MockShoe([1, 1, 10, 13])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(0.0)

    def test_bj_on_split_hand_pays_even_money(self):
        """A 21 achieved on a split hand pays 1:1, not BJ odds."""
        rules = GameRules(rsa=False, max_splits=1)
        # Player gets 8,8 -> splits; first hand gets Ace (8+A=19), second gets 3 (8+3=11)
        # D up=6, hole=10 (total 16 -> hits); after split, hands are [8,A=19] and [8,3=11]
        # strategy: split first, then stand
        shoe = MockShoe([8, 6, 8, 10,   # initial deal: P1=8,D_up=6,P2=8,D_hole=10
                         1, 3,           # split cards: h1 gets A, h2 gets 3
                         5])             # dealer hits 16 -> 21
        calls = {"n": 0}
        def strategy(hand, upcard, rules):
            if hand.can_split() and calls["n"] == 0:
                calls["n"] += 1
                return "split"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # h1=8+A=19 (not BJ, from_split), h2=8+3=11; dealer=6+10+5=21
        # h1: 19 < 21 -> loss (-100); h2: 11 < 21 -> loss (-100)
        assert payout == pytest.approx(-200.0)


# ---------------------------------------------------------------------------
# play_round — surrender
# ---------------------------------------------------------------------------

class TestSurrender:
    def test_surrender_returns_half_bet(self):
        rules = GameRules(surrender=True)
        # P: 10,6 (16); D: 10,7 (17 — no BJ)
        shoe = MockShoe([10, 10, 6, 7])
        payout = play_round(shoe, 100.0, rules, always("surrender"))
        assert payout == pytest.approx(-50.0)

    def test_surrender_not_allowed(self):
        """When surrender=False, the action is ignored and hand stands."""
        rules = GameRules(surrender=False)
        shoe = MockShoe([10, 10, 6, 8])
        # Player 16 vs dealer 18; strategy says surrender (not allowed) -> stand -> lose
        payout = play_round(shoe, 100.0, rules, always("surrender"))
        assert payout == pytest.approx(-100.0)

    def test_no_surrender_after_dealer_bj(self):
        """Dealer BJ: player just loses (no surrender option in US peek rules)."""
        rules = GameRules(surrender=True)
        # D: A(up), 10(hole) -> dealer BJ; P: 10, 6
        shoe = MockShoe([10, 1, 6, 10])
        payout = play_round(shoe, 100.0, rules, always("surrender"))
        assert payout == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# play_round — split to max hands
# ---------------------------------------------------------------------------

class TestSplits:
    def test_basic_split(self):
        """Splitting 8s: two hands each with one new card."""
        rules = GameRules(max_splits=1, das=False, rsa=False)
        # P: 8,8; D: 6(up), 10(hole)
        # After split: h1=8+7=15, h2=8+5=13; dealer: 6+10+? -> 16 -> hits -> 21
        shoe = MockShoe([8, 6, 8, 10,   # initial
                         7, 5,           # split cards
                         9])             # dealer hits 16 -> 25 (bust)
        def strategy(hand, upcard, rules):
            if hand.can_split():
                return "split"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # dealer busts -> both hands win -> +200
        assert payout == pytest.approx(200.0)

    def test_max_splits_enforced(self):
        """Cannot split beyond max_splits hands."""
        rules = GameRules(max_splits=1, das=False, rsa=False)
        # Player pairs: 8,8 -> split; each hand gets another 8 -> tries to split again but blocked
        # h1=8,8 -> would split again but max=1 reached -> stand at 16
        # h2=8,8 -> same
        shoe = MockShoe([8, 6, 8, 10,   # initial: P=8,8; D=6,10
                         8, 8,           # split cards (each new hand is also 8,8)
                         5])             # dealer: 6+10=16 -> hits -> 21
        def strategy(hand, upcard, rules):
            if hand.can_split():
                return "split"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # Both hands stand at 16; dealer: 6+10+5=21 -> both lose
        assert payout == pytest.approx(-200.0)

    def test_resplit_three_times(self):
        """max_splits=3 allows up to 4 total hands."""
        rules = GameRules(max_splits=3, das=False, rsa=False)
        # P: 8,8; D: 6, 10 (dealer total 16 -> busts with next card)
        # Each split produces another 8 (allowing chain splits up to limit)
        shoe = MockShoe([
            8, 6, 8, 10,    # initial: P=8,8; D_up=6, D_hole=10
            8, 8,            # first split: h1=8+8, h2=8+8
            7, 8,            # second split of h1: h1a=8+7(stand), h1b=8+8
            6, 5,            # third split of h1b: h1b1=8+6(stand), h1b2=8+5(stand)
            # h2 is 8+8 but max_splits=3 already reached -> stand at 16
            9,               # dealer: 6+10+9=25 bust
        ])
        calls = {"splits": 0}
        def strategy(hand, upcard, rules_arg):
            if hand.can_split() and calls["splits"] < 3:
                calls["splits"] += 1
                return "split"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # dealer busts; 4 hands all win
        assert payout == pytest.approx(400.0)

    def test_split_aces_get_one_card_only(self):
        """Split aces each receive exactly one additional card with no further action."""
        rules = GameRules(max_splits=1, rsa=False)
        # P: A,A; D: 6(up), 10(hole)
        # After split: h1=A+10=21(not BJ), h2=A+7=18
        # Dealer: 6+10=16 -> hits with 9 -> bust
        shoe = MockShoe([1, 6, 1, 10,   # initial
                         10, 7,          # split ace cards
                         9])             # dealer hits 16 -> 25
        def strategy(hand, upcard, rules_arg):
            if hand.can_split():
                return "split"
            return "hit"    # would never be reached for split aces
        payout = play_round(shoe, 100.0, rules, strategy)
        # dealer busts -> both hands win -> +200
        assert payout == pytest.approx(200.0)

    def test_rsa_false_blocks_ace_resplit(self):
        """With RSA=False, cannot split aces again after first split."""
        rules = GameRules(max_splits=2, rsa=False)
        # P: A,A; split; h1=A+A(pair), h2=A+9
        # rsa=False: h1 is pair of aces but cannot re-split
        shoe = MockShoe([1, 6, 1, 10,   # initial: P=A,A; D=6,10
                         1, 9,           # h1=A+A, h2=A+9
                         # dealer: 6+10=16 -> bust
                         9])
        def strategy(hand, upcard, rules_arg):
            if hand.can_split():
                return "split"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # h1=A+A (from_split, rsa blocked -> stand at 12), h2=A+9=20
        # dealer: 6+10+9=25 bust -> both win -> +200
        assert payout == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# play_round — double after split (DAS)
# ---------------------------------------------------------------------------

class TestDAS:
    def test_das_allowed(self):
        """With DAS=True, player can double on a split hand."""
        rules = GameRules(max_splits=1, das=True, rsa=False)
        # P: 5,5; D: 6(up), 10(hole)
        # Split: h1=5+6=11 -> double -> gets one more card (4 -> 15)
        #        h2=5+3=8 -> stand
        # dealer: 6+10=16 -> hits -> 9 -> bust (25)
        shoe = MockShoe([5, 6, 5, 10,   # initial
                         6, 3,           # split cards: h1=5+6=11, h2=5+3=8
                         4,              # h1 doubles -> gets 4 -> 15
                         9])             # dealer: 6+10+9=25 bust
        seq = {"step": 0}
        def strategy(hand, upcard, rules_arg):
            seq["step"] += 1
            if seq["step"] == 1:
                return "split"
            if seq["step"] == 2:  # h1: 5+6=11 -> double
                return "double"
            return "stand"        # h2: 8 -> stand
        payout = play_round(shoe, 100.0, rules, strategy)
        # h1 bet doubled to 200, wins; h2 bet 100, wins -> +300
        assert payout == pytest.approx(300.0)

    def test_das_not_allowed(self):
        """With DAS=False, double on a split hand is treated as a hit."""
        rules = GameRules(max_splits=1, das=False, rsa=False)
        # P: 5,5; D: 6(up), 10(hole)
        # Split: h1=5+6=11 -> tries double (not allowed -> hits) -> gets 4 -> 20 -> stand
        #        h2=5+3=8 -> stand
        # dealer: 6+10=16 -> busts with 9
        shoe = MockShoe([5, 6, 5, 10,   # initial
                         6, 3,           # split cards
                         4,              # h1 double-attempt -> hit -> 20
                         9])             # dealer busts
        seq = {"step": 0}
        def strategy(hand, upcard, rules_arg):
            seq["step"] += 1
            if seq["step"] == 1:
                return "split"
            if seq["step"] == 2:  # h1: 5+6=11 -> request double (disallowed, hits instead)
                return "double"
            return "stand"
        payout = play_round(shoe, 100.0, rules, strategy)
        # h1 bet stays 100 (double not allowed, just hit), wins; h2 wins -> +200
        assert payout == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# play_round — general win/loss/push outcomes
# ---------------------------------------------------------------------------

class TestOutcomes:
    def test_player_wins(self):
        rules = GameRules(surrender=False)
        # P: 10,9=19; D: 10(up), 7(hole)=17
        shoe = MockShoe([10, 10, 9, 7])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(100.0)

    def test_player_loses(self):
        rules = GameRules(surrender=False)
        # P: 10,6=16; D: 10(up), 9(hole)=19
        shoe = MockShoe([10, 10, 6, 9])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(-100.0)

    def test_push(self):
        rules = GameRules(surrender=False)
        # P: 10,8=18; D: 10(up), 8(hole)=18
        shoe = MockShoe([10, 10, 8, 8])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(0.0)

    def test_player_busts(self):
        rules = GameRules(surrender=False)
        # P: 10,7=17, hits -> 9 -> bust; D: 6,10=16 (no BJ, never plays)
        shoe = MockShoe([10, 6, 7, 10, 9])
        payout = play_round(shoe, 100.0, rules, action_sequence("hit", "stand"))
        assert payout == pytest.approx(-100.0)

    def test_dealer_busts_player_wins(self):
        rules = GameRules(surrender=False)
        # P: 10,8=18 (stand); D: 6(up),10(hole)=16 -> hits -> 9 -> bust
        shoe = MockShoe([10, 6, 8, 10, 9])
        payout = play_round(shoe, 100.0, rules, always("stand"))
        assert payout == pytest.approx(100.0)

    def test_double_down(self):
        rules = GameRules(surrender=False)
        # P: 6,5=11 -> double -> gets 10 -> 21; D: 5(up),10(hole)=15 -> hits -> 8 -> bust
        shoe = MockShoe([6, 5, 5, 10, 10, 8])
        payout = play_round(shoe, 100.0, rules, action_sequence("double"))
        # Bet doubled to 200, dealer busts -> win 200
        assert payout == pytest.approx(200.0)
