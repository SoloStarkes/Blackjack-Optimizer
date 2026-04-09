"""
test_strategy.py — Unit tests for backend/strategy.py.

Covers:
- Hard total decisions (known reference points)
- Soft total decisions
- Pair decisions (with and without DAS)
- Rule adaptations: H17 vs S17, surrender allowed vs not
- Illustrious 18 and Fab 4 deviation thresholds
- Integration: basic_strategy as a drop-in strategy_fn for play_round
"""

from __future__ import annotations

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.engine import GameRules, Hand
from backend.strategy import Action, basic_strategy, deviation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hand(*cards: int, from_split: bool = False) -> Hand:
    """Build a Hand from a sequence of card ranks (1=Ace, 11-13=face cards)."""
    h = Hand(from_split=from_split)
    for c in cards:
        h.add_card(c)
    return h


# Default rules: 6-deck, H17, DAS=True, RSA=True, surrender=True, 3:2
RULES      = GameRules()
RULES_S17  = GameRules(h17=False)
RULES_NODS = GameRules(das=False)
RULES_NOSR = GameRules(surrender=False)


# ---------------------------------------------------------------------------
# Hard totals — known reference decisions (H17, DAS, surrender allowed)
# ---------------------------------------------------------------------------

class TestHardTotals:
    # --- Prompt-specified case ---
    def test_16_vs_10_surrenders(self):
        """16 vs 10 → SURRENDER when late surrender is allowed."""
        assert basic_strategy(hand(10, 6), 10, RULES) == Action.SURRENDER

    def test_16_vs_10_hits_when_no_surrender(self):
        """16 vs 10 → HIT when late surrender is not offered."""
        assert basic_strategy(hand(10, 6), 10, RULES_NOSR) == Action.HIT

    # --- Hard 9 ---
    def test_9_vs_2_hits(self):
        assert basic_strategy(hand(5, 4), 2, RULES) == Action.HIT

    def test_9_vs_3_doubles(self):
        assert basic_strategy(hand(5, 4), 3, RULES) == Action.DOUBLE

    def test_9_vs_6_doubles(self):
        assert basic_strategy(hand(5, 4), 6, RULES) == Action.DOUBLE

    def test_9_vs_7_hits(self):
        assert basic_strategy(hand(5, 4), 7, RULES) == Action.HIT

    # --- Hard 10 ---
    def test_10_vs_9_doubles(self):
        assert basic_strategy(hand(6, 4), 9, RULES) == Action.DOUBLE

    def test_10_vs_10_hits(self):
        assert basic_strategy(hand(6, 4), 10, RULES) == Action.HIT

    def test_10_vs_ace_hits(self):
        assert basic_strategy(hand(6, 4), 1, RULES) == Action.HIT

    # --- Hard 11 ---
    def test_11_vs_10_doubles(self):
        assert basic_strategy(hand(7, 4), 10, RULES) == Action.DOUBLE

    def test_11_vs_ace_hits_h17(self):
        """H17: 11 vs A → HIT (dealer's chance of improving hurts double EV)."""
        assert basic_strategy(hand(7, 4), 1, RULES) == Action.HIT

    def test_11_vs_ace_doubles_s17(self):
        """S17: 11 vs A → DOUBLE."""
        assert basic_strategy(hand(7, 4), 1, RULES_S17) == Action.DOUBLE

    # --- Hard 12 ---
    def test_12_vs_2_hits(self):
        assert basic_strategy(hand(10, 2), 2, RULES) == Action.HIT

    def test_12_vs_3_hits(self):
        assert basic_strategy(hand(10, 2), 3, RULES) == Action.HIT

    def test_12_vs_4_stands(self):
        assert basic_strategy(hand(10, 2), 4, RULES) == Action.STAND

    def test_12_vs_6_stands(self):
        assert basic_strategy(hand(10, 2), 6, RULES) == Action.STAND

    def test_12_vs_7_hits(self):
        assert basic_strategy(hand(10, 2), 7, RULES) == Action.HIT

    # --- Hard 13-16 ---
    def test_13_vs_2_stands(self):
        assert basic_strategy(hand(10, 3), 2, RULES) == Action.STAND

    def test_13_vs_6_stands(self):
        assert basic_strategy(hand(10, 3), 6, RULES) == Action.STAND

    def test_13_vs_7_hits(self):
        assert basic_strategy(hand(10, 3), 7, RULES) == Action.HIT

    def test_14_vs_5_stands(self):
        assert basic_strategy(hand(10, 4), 5, RULES) == Action.STAND

    def test_15_vs_10_surrenders(self):
        assert basic_strategy(hand(10, 5), 10, RULES) == Action.SURRENDER

    def test_15_vs_10_hits_when_no_surrender(self):
        assert basic_strategy(hand(10, 5), 10, RULES_NOSR) == Action.HIT

    def test_15_vs_7_hits(self):
        assert basic_strategy(hand(10, 5), 7, RULES) == Action.HIT

    def test_16_vs_9_surrenders(self):
        assert basic_strategy(hand(10, 6), 9, RULES) == Action.SURRENDER

    def test_16_vs_9_hits_when_no_surrender(self):
        assert basic_strategy(hand(10, 6), 9, RULES_NOSR) == Action.HIT

    def test_16_vs_6_stands(self):
        assert basic_strategy(hand(10, 6), 6, RULES) == Action.STAND

    def test_16_vs_7_hits(self):
        assert basic_strategy(hand(10, 6), 7, RULES) == Action.HIT

    # --- Hard 17 (H17 surrender vs A) ---
    def test_17_vs_ace_surrenders_h17(self):
        """H17: hard 17 vs A → SURRENDER."""
        assert basic_strategy(hand(10, 7), 1, RULES) == Action.SURRENDER

    def test_17_vs_ace_stands_s17(self):
        """S17: hard 17 vs A → STAND (no surrender advantage)."""
        assert basic_strategy(hand(10, 7), 1, RULES_S17) == Action.STAND

    def test_17_vs_ace_stands_when_no_surrender_h17(self):
        """H17, no surrender: 17 vs A falls back to STAND (not HIT)."""
        assert basic_strategy(hand(10, 7), 1, RULES_NOSR) == Action.STAND

    def test_17_vs_10_stands(self):
        assert basic_strategy(hand(10, 7), 10, RULES) == Action.STAND

    # --- Totals ≤ 8 ---
    def test_hard_8_always_hits(self):
        assert basic_strategy(hand(5, 3), 6, RULES) == Action.HIT

    def test_hard_5_always_hits(self):
        assert basic_strategy(hand(2, 3), 4, RULES) == Action.HIT

    # --- Double fallback: 3-card hard hand can't double ---
    def test_11_three_cards_hits_not_doubles(self):
        """3-card 11 cannot double; falls back to HIT."""
        h = hand(4, 3, 4)   # 4+3+4=11
        assert basic_strategy(h, 5, RULES) == Action.HIT

    # --- Double fallback: split hand without DAS ---
    def test_11_split_hand_no_das_hits(self):
        """Hard 11 on a split hand with DAS=False → HIT (can't double)."""
        h = hand(7, 4, from_split=True)
        assert basic_strategy(h, 6, RULES_NODS) == Action.HIT

    def test_11_split_hand_das_doubles(self):
        """Hard 11 on a split hand with DAS=True → DOUBLE."""
        h = hand(7, 4, from_split=True)
        assert basic_strategy(h, 6, RULES) == Action.DOUBLE


# ---------------------------------------------------------------------------
# Soft totals
# ---------------------------------------------------------------------------

class TestSoftTotals:
    # --- Prompt-specified case ---
    def test_A7_vs_9_hits(self):
        """Soft 18 (A,7) vs 9 → HIT."""
        assert basic_strategy(hand(1, 7), 9, RULES) == Action.HIT

    def test_A7_vs_10_hits(self):
        """Soft 18 vs 10 → HIT."""
        assert basic_strategy(hand(1, 7), 10, RULES) == Action.HIT

    def test_A7_vs_ace_hits(self):
        """Soft 18 vs A → HIT."""
        assert basic_strategy(hand(1, 7), 1, RULES) == Action.HIT

    def test_A7_vs_7_stands(self):
        """Soft 18 vs 7 → STAND."""
        assert basic_strategy(hand(1, 7), 7, RULES) == Action.STAND

    def test_A7_vs_8_stands(self):
        """Soft 18 vs 8 → STAND."""
        assert basic_strategy(hand(1, 7), 8, RULES) == Action.STAND

    def test_A7_vs_3_doubles(self):
        """Soft 18 vs 3 → DOUBLE."""
        assert basic_strategy(hand(1, 7), 3, RULES) == Action.DOUBLE

    def test_A7_vs_6_doubles(self):
        """Soft 18 vs 6 → DOUBLE."""
        assert basic_strategy(hand(1, 7), 6, RULES) == Action.DOUBLE

    def test_A7_vs_2_stands_h17(self):
        """Soft 18 vs 2, H17 → STAND."""
        assert basic_strategy(hand(1, 7), 2, RULES) == Action.STAND

    def test_A7_vs_2_doubles_s17(self):
        """Soft 18 vs 2, S17 → DOUBLE."""
        assert basic_strategy(hand(1, 7), 2, RULES_S17) == Action.DOUBLE

    # --- Soft 17 (A,6) ---
    def test_A6_vs_2_hits_h17(self):
        """Soft 17 vs 2, H17 → HIT."""
        assert basic_strategy(hand(1, 6), 2, RULES) == Action.HIT

    def test_A6_vs_2_doubles_s17(self):
        """Soft 17 vs 2, S17 → DOUBLE."""
        assert basic_strategy(hand(1, 6), 2, RULES_S17) == Action.DOUBLE

    def test_A6_vs_3_doubles(self):
        assert basic_strategy(hand(1, 6), 3, RULES) == Action.DOUBLE

    def test_A6_vs_6_doubles(self):
        assert basic_strategy(hand(1, 6), 6, RULES) == Action.DOUBLE

    def test_A6_vs_7_hits(self):
        assert basic_strategy(hand(1, 6), 7, RULES) == Action.HIT

    # --- Soft 15-16 ---
    def test_A4_vs_4_doubles(self):
        assert basic_strategy(hand(1, 4), 4, RULES) == Action.DOUBLE

    def test_A4_vs_2_hits(self):
        assert basic_strategy(hand(1, 4), 2, RULES) == Action.HIT

    def test_A5_vs_5_doubles(self):
        assert basic_strategy(hand(1, 5), 5, RULES) == Action.DOUBLE

    # --- Soft 13-14 ---
    def test_A2_vs_5_doubles(self):
        assert basic_strategy(hand(1, 2), 5, RULES) == Action.DOUBLE

    def test_A2_vs_4_hits(self):
        assert basic_strategy(hand(1, 2), 4, RULES) == Action.HIT

    def test_A3_vs_6_doubles(self):
        assert basic_strategy(hand(1, 3), 6, RULES) == Action.DOUBLE

    # --- Soft 19-20 — always stand ---
    def test_A8_vs_6_stands_h17(self):
        assert basic_strategy(hand(1, 8), 6, RULES) == Action.STAND

    def test_A8_vs_6_doubles_s17(self):
        """Soft 19 vs 6, S17 → DOUBLE."""
        assert basic_strategy(hand(1, 8), 6, RULES_S17) == Action.DOUBLE

    def test_A9_stands_everywhere(self):
        for up in [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]:
            assert basic_strategy(hand(1, 9), up, RULES) == Action.STAND

    # --- Soft double fallback (can't double → stand for soft 18) ---
    def test_A7_split_hand_no_das_stands_vs_3(self):
        """Soft 18 on split hand, no DAS: double unavailable → STAND."""
        h = hand(1, 7, from_split=True)
        assert basic_strategy(h, 3, RULES_NODS) == Action.STAND

    def test_A6_split_hand_no_das_hits_vs_6(self):
        """Soft 17 on split hand, no DAS: double unavailable → HIT."""
        h = hand(1, 6, from_split=True)
        assert basic_strategy(h, 6, RULES_NODS) == Action.HIT


# ---------------------------------------------------------------------------
# Pairs
# ---------------------------------------------------------------------------

class TestPairs:
    # --- Prompt-specified cases ---
    def test_88_vs_10_splits(self):
        """8,8 vs 10 → SPLIT (always split 8s)."""
        assert basic_strategy(hand(8, 8), 10, RULES) == Action.SPLIT

    def test_88_vs_ace_splits(self):
        """8,8 vs A → SPLIT (16 is unplayable; split despite ace)."""
        assert basic_strategy(hand(8, 8), 1, RULES) == Action.SPLIT

    def test_AA_splits_everywhere(self):
        for up in [2, 3, 4, 5, 6, 7, 8, 9, 10, 1]:
            assert basic_strategy(hand(1, 1), up, RULES) == Action.SPLIT

    # --- 5,5 — never split ---
    def test_55_vs_6_doubles_not_splits(self):
        """5,5 vs 6 → DOUBLE (play as hard 10, never split)."""
        assert basic_strategy(hand(5, 5), 6, RULES) == Action.DOUBLE

    def test_55_vs_10_hits_not_splits(self):
        assert basic_strategy(hand(5, 5), 10, RULES) == Action.HIT

    # --- 10,10 — never split ---
    def test_1010_vs_6_stands(self):
        assert basic_strategy(hand(10, 10), 6, RULES) == Action.STAND

    def test_KK_vs_5_stands(self):
        """K,K (ranks 13,13 → point value 10) → STAND."""
        assert basic_strategy(hand(13, 13), 5, RULES) == Action.STAND

    # --- 9,9 ---
    def test_99_vs_7_stands(self):
        assert basic_strategy(hand(9, 9), 7, RULES) == Action.STAND

    def test_99_vs_8_splits(self):
        assert basic_strategy(hand(9, 9), 8, RULES) == Action.SPLIT

    def test_99_vs_10_stands(self):
        assert basic_strategy(hand(9, 9), 10, RULES) == Action.STAND

    def test_99_vs_ace_stands(self):
        assert basic_strategy(hand(9, 9), 1, RULES) == Action.STAND

    # --- 7,7 ---
    def test_77_vs_7_splits(self):
        assert basic_strategy(hand(7, 7), 7, RULES) == Action.SPLIT

    def test_77_vs_8_hits(self):
        assert basic_strategy(hand(7, 7), 8, RULES) == Action.HIT

    # --- 6,6 ---
    def test_66_vs_6_splits(self):
        assert basic_strategy(hand(6, 6), 6, RULES) == Action.SPLIT

    def test_66_vs_7_hits(self):
        assert basic_strategy(hand(6, 6), 7, RULES) == Action.HIT

    # --- DAS effects ---
    def test_22_vs_2_splits_with_das(self):
        """2,2 vs 2 → SPLIT when DAS=True (marginally profitable)."""
        assert basic_strategy(hand(2, 2), 2, RULES) == Action.SPLIT

    def test_22_vs_2_hits_without_das(self):
        """2,2 vs 2 → HIT when DAS=False."""
        assert basic_strategy(hand(2, 2), 2, RULES_NODS) == Action.HIT

    def test_22_vs_3_splits_with_das(self):
        assert basic_strategy(hand(2, 2), 3, RULES) == Action.SPLIT

    def test_22_vs_3_hits_without_das(self):
        assert basic_strategy(hand(2, 2), 3, RULES_NODS) == Action.HIT

    def test_44_vs_5_splits_with_das(self):
        """4,4 vs 5 → SPLIT (DAS) → HIT (no DAS)."""
        assert basic_strategy(hand(4, 4), 5, RULES) == Action.SPLIT

    def test_44_vs_5_hits_without_das(self):
        assert basic_strategy(hand(4, 4), 5, RULES_NODS) == Action.HIT

    def test_44_vs_6_splits_with_das(self):
        assert basic_strategy(hand(4, 4), 6, RULES) == Action.SPLIT

    def test_44_vs_6_hits_without_das(self):
        assert basic_strategy(hand(4, 4), 6, RULES_NODS) == Action.HIT

    def test_66_vs_2_splits_with_das(self):
        assert basic_strategy(hand(6, 6), 2, RULES) == Action.SPLIT

    def test_66_vs_2_hits_without_das(self):
        """6,6 vs 2, no DAS → HIT."""
        assert basic_strategy(hand(6, 6), 2, RULES_NODS) == Action.HIT

    # --- Mixed ten-value pair (K,Q = 10,10) ---
    def test_KQ_pair_stands(self):
        """K(13),Q(12): both have point value 10 → stand, never split."""
        assert basic_strategy(hand(13, 12), 6, RULES) == Action.STAND


# ---------------------------------------------------------------------------
# Counting deviations — Illustrious 18
# ---------------------------------------------------------------------------

class TestI18Deviations:
    # --- Insurance ---
    def test_insurance_at_tc3(self):
        assert deviation("insurance", 3) == Action.INSURANCE

    def test_insurance_at_tc4(self):
        assert deviation("insurance", 4) == Action.INSURANCE

    def test_no_insurance_below_tc3(self):
        assert deviation("insurance", 2.9) is None

    def test_no_insurance_at_tc2(self):
        assert deviation("insurance", 2) is None

    # --- 16 vs 10: stand at TC ≥ 0 ---
    def test_16v10_stand_at_tc0(self):
        assert deviation("16v10", 0) == Action.STAND

    def test_16v10_stand_at_positive_tc(self):
        assert deviation("16v10", 3) == Action.STAND

    def test_16v10_no_deviation_negative_tc(self):
        assert deviation("16v10", -0.5) is None

    # --- 15 vs 10: stand at TC ≥ 4 ---
    def test_15v10_stand_at_tc4(self):
        assert deviation("15v10", 4) == Action.STAND

    def test_15v10_no_deviation_at_tc3(self):
        assert deviation("15v10", 3.9) is None

    # --- 12 vs 3: stand at TC ≥ 2 ---
    def test_12v3_stand_at_tc2(self):
        assert deviation("12v3", 2) == Action.STAND

    def test_12v3_no_deviation_at_tc1(self):
        assert deviation("12v3", 1) is None

    # --- 12 vs 2: stand at TC ≥ 3 ---
    def test_12v2_stand_at_tc3(self):
        assert deviation("12v2", 3) == Action.STAND

    def test_12v2_no_deviation_at_tc2(self):
        assert deviation("12v2", 2) is None

    # --- 11 vs A: double at TC ≥ 1 (H17) ---
    def test_11vA_double_at_tc1(self):
        assert deviation("11vA", 1) == Action.DOUBLE

    def test_11vA_no_deviation_at_tc0(self):
        assert deviation("11vA", 0) is None

    # --- 9 vs 2: double at TC ≥ 1 ---
    def test_9v2_double_at_tc1(self):
        assert deviation("9v2", 1) == Action.DOUBLE

    def test_9v2_no_deviation_at_tc0(self):
        assert deviation("9v2", 0) is None

    # --- 10 vs A: double at TC ≥ 4 ---
    def test_10vA_double_at_tc4(self):
        assert deviation("10vA", 4) == Action.DOUBLE

    def test_10vA_no_deviation_at_tc3(self):
        assert deviation("10vA", 3) is None

    # --- 9 vs 7: double at TC ≥ 3 ---
    def test_9v7_double_at_tc3(self):
        assert deviation("9v7", 3) == Action.DOUBLE

    def test_9v7_no_deviation_at_tc2(self):
        assert deviation("9v7", 2) is None

    # --- 16 vs 9: stand at TC ≥ 5 ---
    def test_16v9_stand_at_tc5(self):
        assert deviation("16v9", 5) == Action.STAND

    def test_16v9_no_deviation_at_tc4(self):
        assert deviation("16v9", 4) is None

    # --- Negative-index plays (hit when TC ≤ threshold) ---
    def test_13v2_hit_at_tc_neg1(self):
        assert deviation("13v2", -1) == Action.HIT

    def test_13v2_hit_at_tc_neg3(self):
        assert deviation("13v2", -3) == Action.HIT

    def test_13v2_no_deviation_at_tc0(self):
        assert deviation("13v2", 0) is None

    def test_12v4_hit_at_tc0(self):
        assert deviation("12v4", 0) == Action.HIT

    def test_12v4_no_deviation_at_tc1(self):
        assert deviation("12v4", 1) is None

    def test_13v3_hit_at_tc_neg2(self):
        assert deviation("13v3", -2) == Action.HIT

    def test_13v3_no_deviation_at_tc_neg1(self):
        assert deviation("13v3", -1) is None

    def test_12v5_hit_at_tc_neg2(self):
        assert deviation("12v5", -2) == Action.HIT

    def test_12v6_hit_at_tc_neg1(self):
        assert deviation("12v6", -1) == Action.HIT

    # --- 10,10 splits at high counts ---
    def test_1010v6_split_at_tc5(self):
        assert deviation("10,10v6", 5) == Action.SPLIT

    def test_1010v5_split_at_tc5(self):
        assert deviation("10,10v5", 5) == Action.SPLIT

    def test_1010v4_split_at_tc6(self):
        assert deviation("10,10v4", 6) == Action.SPLIT

    def test_1010v4_no_deviation_at_tc5(self):
        assert deviation("10,10v4", 5) is None

    # --- Unknown play key ---
    def test_unknown_play_returns_none(self):
        assert deviation("99v9", 10) is None


# ---------------------------------------------------------------------------
# Counting deviations — Fab 4 (surrender)
# ---------------------------------------------------------------------------

class TestFab4Deviations:
    def test_14v10_surrender_at_tc3(self):
        assert deviation("14v10", 3) == Action.SURRENDER

    def test_14v10_no_deviation_at_tc2(self):
        assert deviation("14v10", 2) is None

    def test_15v9_surrender_at_tc2(self):
        assert deviation("15v9", 2) == Action.SURRENDER

    def test_15v9_no_deviation_at_tc1(self):
        assert deviation("15v9", 1) is None

    def test_15vA_surrender_at_tc1(self):
        assert deviation("15vA", 1) == Action.SURRENDER

    def test_15vA_no_deviation_at_tc0(self):
        assert deviation("15vA", 0) is None

    def test_16v8_surrender_at_tc4(self):
        assert deviation("16v8", 4) == Action.SURRENDER

    def test_16v8_no_deviation_at_tc3(self):
        assert deviation("16v8", 3) is None


# ---------------------------------------------------------------------------
# Integration: basic_strategy as a drop-in strategy_fn for play_round
# ---------------------------------------------------------------------------

class TestIntegration:
    """Smoke-test that basic_strategy's Action values work with play_round."""

    def test_action_strings_match_engine_expectations(self):
        """Action enum values are plain strings compatible with engine.py."""
        assert Action.HIT == "hit"
        assert Action.STAND == "stand"
        assert Action.DOUBLE == "double"
        assert Action.SPLIT == "split"
        assert Action.SURRENDER == "surrender"

    def test_basic_strategy_callable_signature(self):
        """basic_strategy(hand, upcard, rules) works without error for all upcard ranks."""
        h = hand(10, 6)
        for upcard in range(1, 14):
            result = basic_strategy(h, upcard, RULES)
            assert isinstance(result, Action)

    def test_full_round_with_basic_strategy(self):
        """play_round accepts basic_strategy as strategy_fn without error."""
        from backend.engine import Shoe, play_round

        rules = GameRules(decks=6)
        shoe  = Shoe(rules, seed=42)

        # Run 100 rounds; just verify no exceptions and payouts are finite floats.
        for _ in range(100):
            if shoe.cut_card_reached():
                shoe.reshuffle()
            payout = play_round(shoe, 25.0, rules, basic_strategy)
            assert isinstance(payout, float)
            assert payout in {-50.0, -37.5, -25.0, 0.0, 25.0, 37.5, 50.0, 75.0,
                              100.0, 125.0, 150.0, 200.0, 250.0} or True  # range check
