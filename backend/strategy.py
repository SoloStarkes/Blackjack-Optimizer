"""
strategy.py — Basic strategy lookup tables and Hi-Lo counting deviations.

Implements complete multi-deck basic strategy for H17 and S17 games,
with DAS / no-DAS and late-surrender / no-surrender adaptations.

Also implements the Illustrious 18 index plays and Fab 4 surrender
deviations that override basic strategy at specific true counts.

Public surface:
    Action          — enum of possible player actions
    basic_strategy  — returns the correct basic-strategy action
    deviation       — returns a counting deviation action, or None
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, NamedTuple, Optional, Tuple

from backend.engine import GameRules, Hand, card_value


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------

class Action(str, Enum):
    """Player action.  Inherits str so instances compare equal to raw strings,
    making this enum transparently compatible with engine.py's string checks."""

    HIT       = "hit"
    STAND     = "stand"
    DOUBLE    = "double"
    SPLIT     = "split"
    SURRENDER = "surrender"
    INSURANCE = "insurance"   # side bet; returned by deviation() only


# Compact aliases used when building the tables below.
H = Action.HIT
S = Action.STAND
D = Action.DOUBLE
P = Action.SPLIT
R = Action.SURRENDER


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _norm(dealer_upcard: int) -> int:
    """Normalise a raw card rank to a strategy-table key.

    Args:
        dealer_upcard: Raw rank 1–13 (1=Ace, 11-13=face cards).

    Returns:
        1 for Ace, 2–9 for pip cards, 10 for 10/J/Q/K.
    """
    return card_value(dealer_upcard)


# ---------------------------------------------------------------------------
# Hard total tables
# ---------------------------------------------------------------------------
# Key:   (player_hard_total, normalised_dealer_upcard)
# Value: Action for multi-deck H17 with late surrender.
#
# Totals ≤ 8  → always HIT  (handled as default in _lookup_action)
# Totals ≥ 18 → always STAND (handled as default)
#
# R = SURRENDER; fallback when surrender unavailable is HIT except where
# noted in _SURRENDER_FALLBACK_STAND.

_HARD_H17: Dict[Tuple[int, int], Action] = {
    # Hard 9 — double vs dealer 3-6
    (9,  2): H, (9,  3): D, (9,  4): D, (9,  5): D, (9,  6): D,
    (9,  7): H, (9,  8): H, (9,  9): H, (9, 10): H, (9,  1): H,
    # Hard 10 — double vs 2-9
    (10, 2): D, (10, 3): D, (10, 4): D, (10, 5): D, (10, 6): D,
    (10, 7): D, (10, 8): D, (10, 9): D, (10,10): H, (10, 1): H,
    # Hard 11 — double vs 2-10 (H17); hit vs A in H17 only
    (11, 2): D, (11, 3): D, (11, 4): D, (11, 5): D, (11, 6): D,
    (11, 7): D, (11, 8): D, (11, 9): D, (11,10): D, (11, 1): H,
    # Hard 12 — stand vs 4-6
    (12, 2): H, (12, 3): H, (12, 4): S, (12, 5): S, (12, 6): S,
    (12, 7): H, (12, 8): H, (12, 9): H, (12,10): H, (12, 1): H,
    # Hard 13 — stand vs 2-6
    (13, 2): S, (13, 3): S, (13, 4): S, (13, 5): S, (13, 6): S,
    (13, 7): H, (13, 8): H, (13, 9): H, (13,10): H, (13, 1): H,
    # Hard 14 — stand vs 2-6
    (14, 2): S, (14, 3): S, (14, 4): S, (14, 5): S, (14, 6): S,
    (14, 7): H, (14, 8): H, (14, 9): H, (14,10): H, (14, 1): H,
    # Hard 15 — surrender vs 10, A; stand vs 2-6
    (15, 2): S, (15, 3): S, (15, 4): S, (15, 5): S, (15, 6): S,
    (15, 7): H, (15, 8): H, (15, 9): H, (15,10): R, (15, 1): R,
    # Hard 16 — surrender vs 9, 10, A; stand vs 2-6
    (16, 2): S, (16, 3): S, (16, 4): S, (16, 5): S, (16, 6): S,
    (16, 7): H, (16, 8): H, (16, 9): R, (16,10): R, (16, 1): R,
    # Hard 17 — surrender vs A in H17 only; stand everywhere else
    (17, 2): S, (17, 3): S, (17, 4): S, (17, 5): S, (17, 6): S,
    (17, 7): S, (17, 8): S, (17, 9): S, (17,10): S, (17, 1): R,
}

# Entries that differ under S17 (dealer stands on soft 17).
_HARD_S17_OVERRIDES: Dict[Tuple[int, int], Action] = {
    (11, 1): D,   # H17 = H  →  S17 = D
    (15, 1): H,   # H17 = R  →  S17 = H  (no surrender edge with S17)
    (17, 1): S,   # H17 = R  →  S17 = S  (no surrender edge with S17)
}

# Surrender positions whose no-surrender fallback is STAND (not HIT).
_SURRENDER_FALLBACK_STAND: frozenset = frozenset({
    (17, 1),   # hard 17 vs A (H17): stand is second-best if no surrender
})


# ---------------------------------------------------------------------------
# Soft total tables
# ---------------------------------------------------------------------------
# Key: (player_soft_total, normalised_dealer_upcard)
#
# soft_total counts the usable ace as 11
# (A+6 = soft 17, A+7 = soft 18, …)

_SOFT_H17: Dict[Tuple[int, int], Action] = {
    # Soft 13  (A,2)
    (13, 2): H, (13, 3): H, (13, 4): H, (13, 5): D, (13, 6): D,
    (13, 7): H, (13, 8): H, (13, 9): H, (13,10): H, (13, 1): H,
    # Soft 14  (A,3)
    (14, 2): H, (14, 3): H, (14, 4): H, (14, 5): D, (14, 6): D,
    (14, 7): H, (14, 8): H, (14, 9): H, (14,10): H, (14, 1): H,
    # Soft 15  (A,4)
    (15, 2): H, (15, 3): H, (15, 4): D, (15, 5): D, (15, 6): D,
    (15, 7): H, (15, 8): H, (15, 9): H, (15,10): H, (15, 1): H,
    # Soft 16  (A,5)
    (16, 2): H, (16, 3): H, (16, 4): D, (16, 5): D, (16, 6): D,
    (16, 7): H, (16, 8): H, (16, 9): H, (16,10): H, (16, 1): H,
    # Soft 17  (A,6) — H17: hit vs 2, double vs 3-6, hit vs 7-A
    (17, 2): H, (17, 3): D, (17, 4): D, (17, 5): D, (17, 6): D,
    (17, 7): H, (17, 8): H, (17, 9): H, (17,10): H, (17, 1): H,
    # Soft 18  (A,7) — stand vs 2, double vs 3-6, stand vs 7-8, hit vs 9/10/A
    (18, 2): S, (18, 3): D, (18, 4): D, (18, 5): D, (18, 6): D,
    (18, 7): S, (18, 8): S, (18, 9): H, (18,10): H, (18, 1): H,
    # Soft 19  (A,8) — always stand in multi-deck H17
    (19, 2): S, (19, 3): S, (19, 4): S, (19, 5): S, (19, 6): S,
    (19, 7): S, (19, 8): S, (19, 9): S, (19,10): S, (19, 1): S,
    # Soft 20  (A,9) — always stand
    (20, 2): S, (20, 3): S, (20, 4): S, (20, 5): S, (20, 6): S,
    (20, 7): S, (20, 8): S, (20, 9): S, (20,10): S, (20, 1): S,
}

# Soft total entries that change under S17.
_SOFT_S17_OVERRIDES: Dict[Tuple[int, int], Action] = {
    (17, 2): D,   # A,6 vs 2: H17 = H  →  S17 = D
    (18, 2): D,   # A,7 vs 2: H17 = S  →  S17 = D  (Ds — else stand)
    (19, 6): D,   # A,8 vs 6: H17 = S  →  S17 = D  (Ds — else stand)
}

# Soft totals where a blocked double falls back to STAND instead of HIT.
# (Standing on soft 18 beats hitting when you can't get the double EV bonus.)
_SOFT_DOUBLE_FALLBACK_STAND: frozenset = frozenset({18, 19})


# ---------------------------------------------------------------------------
# Pair tables
# ---------------------------------------------------------------------------
# Key: (pair_card_point_value, normalised_dealer_upcard)
#
# Pairs that are never split (5,5 and 10,10) carry the correct non-split
# action directly in the table so the lookup is complete.

_PAIR_DAS: Dict[Tuple[int, int], Action] = {
    # A,A — always split
    (1,  2): P, (1,  3): P, (1,  4): P, (1,  5): P, (1,  6): P,
    (1,  7): P, (1,  8): P, (1,  9): P, (1, 10): P, (1,  1): P,
    # 2,2 — split vs 2-7 (DAS allows vs 2 & 3)
    (2,  2): P, (2,  3): P, (2,  4): P, (2,  5): P, (2,  6): P,
    (2,  7): P, (2,  8): H, (2,  9): H, (2, 10): H, (2,  1): H,
    # 3,3 — split vs 2-7
    (3,  2): P, (3,  3): P, (3,  4): P, (3,  5): P, (3,  6): P,
    (3,  7): P, (3,  8): H, (3,  9): H, (3, 10): H, (3,  1): H,
    # 4,4 — split vs 5-6 only (needs DAS to be profitable)
    (4,  2): H, (4,  3): H, (4,  4): H, (4,  5): P, (4,  6): P,
    (4,  7): H, (4,  8): H, (4,  9): H, (4, 10): H, (4,  1): H,
    # 5,5 — never split; play as hard 10 (D vs 2-9, H vs 10/A)
    (5,  2): D, (5,  3): D, (5,  4): D, (5,  5): D, (5,  6): D,
    (5,  7): D, (5,  8): D, (5,  9): D, (5, 10): H, (5,  1): H,
    # 6,6 — split vs 2-6
    (6,  2): P, (6,  3): P, (6,  4): P, (6,  5): P, (6,  6): P,
    (6,  7): H, (6,  8): H, (6,  9): H, (6, 10): H, (6,  1): H,
    # 7,7 — split vs 2-7
    (7,  2): P, (7,  3): P, (7,  4): P, (7,  5): P, (7,  6): P,
    (7,  7): P, (7,  8): H, (7,  9): H, (7, 10): H, (7,  1): H,
    # 8,8 — always split (even vs A; 16 is unplayable)
    (8,  2): P, (8,  3): P, (8,  4): P, (8,  5): P, (8,  6): P,
    (8,  7): P, (8,  8): P, (8,  9): P, (8, 10): P, (8,  1): P,
    # 9,9 — split vs 2-9 except 7; stand vs 7, 10, A
    (9,  2): P, (9,  3): P, (9,  4): P, (9,  5): P, (9,  6): P,
    (9,  7): S, (9,  8): P, (9,  9): P, (9, 10): S, (9,  1): S,
    # 10,10 — never split
    (10, 2): S, (10, 3): S, (10, 4): S, (10, 5): S, (10, 6): S,
    (10, 7): S, (10, 8): S, (10, 9): S, (10,10): S, (10, 1): S,
}

# Entries that change when DAS is not offered.
# Without the bonus of doubling after a split, borderline splits become –EV.
_PAIR_NO_DAS_OVERRIDES: Dict[Tuple[int, int], Action] = {
    # 2,2: don't split vs 2 or 3 (only split vs 4-7)
    (2, 2): H,  (2, 3): H,
    # 3,3: don't split vs 2 or 3
    (3, 2): H,  (3, 3): H,
    # 4,4: never split without DAS
    (4, 5): H,  (4, 6): H,
    # 6,6: don't split vs 2 without DAS
    (6, 2): H,
}


# ---------------------------------------------------------------------------
# Core lookup (private)
# ---------------------------------------------------------------------------

def _lookup_action(player_hand: Hand, up: int, rules: GameRules) -> Action:
    """Return the raw table action before rule-based fallback processing.

    Args:
        player_hand: The player's current hand.
        up: Normalised dealer upcard (1, 2-9, or 10).
        rules: Active game rules.

    Returns:
        Action from the appropriate table, adjusted for H17/S17 and DAS.
    """
    # -- Pairs (must come first; can_split() enforces 2-card requirement) --
    if player_hand.can_split():
        pv = card_value(player_hand.cards[0])
        action = _PAIR_DAS[(pv, up)]
        if not rules.das:
            action = _PAIR_NO_DAS_OVERRIDES.get((pv, up), action)
        return action

    # -- Soft totals --
    if player_hand.is_soft():
        soft = player_hand.total()
        if soft >= 21:
            return Action.STAND
        key = (soft, up)
        action = _SOFT_H17.get(key, Action.STAND)
        if not rules.h17:
            action = _SOFT_S17_OVERRIDES.get(key, action)
        return action

    # -- Hard totals --
    hard = player_hand.total()
    if hard >= 18:
        return Action.STAND
    if hard <= 8:
        return Action.HIT
    key = (hard, up)
    action = _HARD_H17.get(key, Action.STAND)
    if not rules.h17:
        action = _HARD_S17_OVERRIDES.get(key, action)
    return action


# ---------------------------------------------------------------------------
# Public: basic_strategy
# ---------------------------------------------------------------------------

def basic_strategy(player_hand: Hand, dealer_upcard: int, rules: GameRules) -> Action:
    """Return the correct basic-strategy action for a given hand situation.

    Checks pairs, then soft totals, then hard totals — in that order.
    Adapts to the active game rules:

    * ``rules.h17``    — H17 vs S17 table differences
    * ``rules.das``    — DAS changes which pairs are worth splitting
    * ``rules.surrender`` — when False, SURRENDER falls back to HIT or STAND

    The returned ``Action`` is also a plain ``str``, so it works directly as
    the return value of a ``strategy_fn`` passed to ``play_round``.

    Args:
        player_hand: The player's current hand (any number of cards).
        dealer_upcard: Raw dealer upcard rank (1–13).
        rules: Active game rules.

    Returns:
        The optimal basic-strategy ``Action``.
    """
    up = _norm(dealer_upcard)
    action = _lookup_action(player_hand, up, rules)

    # -- Surrender fallback --
    if action is Action.SURRENDER and not rules.surrender:
        total = player_hand.total()
        if (total, up) in _SURRENDER_FALLBACK_STAND:
            return Action.STAND
        return Action.HIT

    # -- Double fallback (when doubling is unavailable on this hand) --
    if action is Action.DOUBLE:
        can_double = len(player_hand.cards) == 2 and (
            not player_hand.from_split or rules.das
        )
        if not can_double:
            if player_hand.is_soft():
                soft = player_hand.total()
                return Action.STAND if soft in _SOFT_DOUBLE_FALLBACK_STAND else Action.HIT
            return Action.HIT

    return action


# ---------------------------------------------------------------------------
# Counting deviations — Illustrious 18 + Fab 4
# ---------------------------------------------------------------------------

class _DevEntry(NamedTuple):
    """A single index-play entry in the deviation table."""
    index: float          # true-count threshold
    action: Action        # action to take when deviation fires
    direction: str        # "ge" → fire when TC ≥ index; "le" → TC ≤ index


# Format: play_key  →  _DevEntry(index, action, direction)
#
# Play key convention: "{hand_description}v{dealer_upcard}"
#   e.g. "16v10", "9v2", "insurance", "10,10v5"
#   Ace upcard is represented as "A".
#
# Illustrious 18 sources: Schlesinger, Blackjack Attack 3rd Ed.
# Fab 4 sources: Schlesinger; indices for 6-deck H17 DAS.

_DEVIATIONS: Dict[str, _DevEntry] = {
    # ── Illustrious 18 ──────────────────────────────────────────────────────
    # Insurance: take even-money protection when TC ≥ 3
    "insurance":   _DevEntry( 3,  Action.INSURANCE, "ge"),
    # 16 vs 10: stand (vs basic surrender/hit) when TC ≥ 0
    "16v10":       _DevEntry( 0,  Action.STAND,     "ge"),
    # 15 vs 10: stand (vs basic surrender/hit) when TC ≥ 4
    "15v10":       _DevEntry( 4,  Action.STAND,     "ge"),
    # 12 vs 3: stand (vs basic hit) when TC ≥ 2
    "12v3":        _DevEntry( 2,  Action.STAND,     "ge"),
    # 12 vs 2: stand (vs basic hit) when TC ≥ 3
    "12v2":        _DevEntry( 3,  Action.STAND,     "ge"),
    # 11 vs A: double (vs basic hit in H17) when TC ≥ 1
    "11vA":        _DevEntry( 1,  Action.DOUBLE,    "ge"),
    # 9 vs 2: double (vs basic hit) when TC ≥ 1
    "9v2":         _DevEntry( 1,  Action.DOUBLE,    "ge"),
    # 10 vs A: double (vs basic hit) when TC ≥ 4
    "10vA":        _DevEntry( 4,  Action.DOUBLE,    "ge"),
    # 9 vs 7: double (vs basic hit) when TC ≥ 3
    "9v7":         _DevEntry( 3,  Action.DOUBLE,    "ge"),
    # 16 vs 9: stand (vs basic surrender/hit) when TC ≥ 5
    "16v9":        _DevEntry( 5,  Action.STAND,     "ge"),
    # 13 vs 2: hit (vs basic stand) when TC ≤ −1
    "13v2":        _DevEntry(-1,  Action.HIT,       "le"),
    # 12 vs 4: hit (vs basic stand) when TC ≤ 0
    "12v4":        _DevEntry( 0,  Action.HIT,       "le"),
    # 13 vs 3: hit (vs basic stand) when TC ≤ −2
    "13v3":        _DevEntry(-2,  Action.HIT,       "le"),
    # 12 vs 5: hit (vs basic stand) when TC ≤ −2
    "12v5":        _DevEntry(-2,  Action.HIT,       "le"),
    # 12 vs 6: hit (vs basic stand) when TC ≤ −1
    "12v6":        _DevEntry(-1,  Action.HIT,       "le"),
    # 10,10 vs 6: split (vs basic stand) when TC ≥ 5
    "10,10v6":     _DevEntry( 5,  Action.SPLIT,     "ge"),
    # 10,10 vs 5: split (vs basic stand) when TC ≥ 5
    "10,10v5":     _DevEntry( 5,  Action.SPLIT,     "ge"),
    # 10,10 vs 4: split (vs basic stand) when TC ≥ 6
    "10,10v4":     _DevEntry( 6,  Action.SPLIT,     "ge"),
    # ── Fab 4 (surrender deviations) ────────────────────────────────────────
    # 14 vs 10: surrender (vs basic hit) when TC ≥ 3
    "14v10":       _DevEntry( 3,  Action.SURRENDER, "ge"),
    # 15 vs 9: surrender (vs basic hit) when TC ≥ 2
    "15v9":        _DevEntry( 2,  Action.SURRENDER, "ge"),
    # 15 vs A: surrender (reinforces H17 basic; deviation for S17) when TC ≥ 1
    "15vA":        _DevEntry( 1,  Action.SURRENDER, "ge"),
    # 16 vs 8: surrender (vs basic hit) when TC ≥ 4
    "16v8":        _DevEntry( 4,  Action.SURRENDER, "ge"),
}


def deviation(play: str, true_count: float) -> Optional[Action]:
    """Return the index-play action if the true count triggers a deviation.

    Covers the Illustrious 18 and Fab 4 for a Hi-Lo counting system in a
    typical 6-deck H17 game.  Returns ``None`` when basic strategy applies.

    Args:
        play: Play identifier string.  Format is ``"{hand}v{upcard}"`` for
              most plays (e.g. ``"16v10"``, ``"9v2"``, ``"10,10v5"``).
              Use ``"insurance"`` for the insurance side-bet deviation.
              Ace upcard is ``"A"`` (e.g. ``"11vA"``).
        true_count: Current Hi-Lo true count (running count / decks remaining).

    Returns:
        The deviated ``Action`` when the TC threshold is met, or ``None``
        if basic strategy should be used for this play at this count.

    Example::

        action = deviation("16v10", true_count) or basic_strategy(hand, up, rules)
    """
    entry = _DEVIATIONS.get(play)
    if entry is None:
        return None
    if entry.direction == "ge" and true_count >= entry.index:
        return entry.action
    if entry.direction == "le" and true_count <= entry.index:
        return entry.action
    return None
