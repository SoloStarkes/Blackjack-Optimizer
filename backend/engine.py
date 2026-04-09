"""
engine.py — Core shoe, card, hand, and game logic for the blackjack simulator.

Design constraints:
- Pure module: no I/O, randomness injected only via seed.
- Dataclasses for GameRules and Hand.
- All monetary values are floats (dollars).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

def card_value(card: int) -> int:
    """Return blackjack point value of a card rank.

    Args:
        card: Integer rank 1–13 (1=Ace, 11=Jack, 12=Queen, 13=King).

    Returns:
        Point value: 10 for face cards, 1 for Ace, face value for 2–10.
    """
    if card >= 10:
        return 10
    return card  # 1 (Ace) through 9


# ---------------------------------------------------------------------------
# GameRules
# ---------------------------------------------------------------------------

@dataclass
class GameRules:
    """All configurable blackjack rules for a single game variant.

    Attributes:
        decks: Number of decks in the shoe (1, 2, 4, 6, or 8).
        penetration: Fraction of shoe dealt before reshuffling (0.0–1.0).
        h17: If True, dealer hits soft 17; if False, dealer stands on all 17s.
        das: Double after split allowed.
        rsa: Re-split aces allowed.
        max_splits: Maximum number of times a hand may be split (so max
            hands = max_splits + 1).
        surrender: Late surrender allowed.
        bj_payout: Blackjack payout multiplier (1.5 for 3:2, 1.2 for 6:5).
    """

    decks: int = 6
    penetration: float = 0.75
    h17: bool = True
    das: bool = True
    rsa: bool = True
    max_splits: int = 3
    surrender: bool = True
    bj_payout: float = 1.5


# ---------------------------------------------------------------------------
# Hand
# ---------------------------------------------------------------------------

@dataclass
class Hand:
    """Represents a single blackjack hand (player or dealer).

    Attributes:
        cards: Ordered list of card ranks dealt to this hand.
        bet: Current wager in dollars (may be doubled).
        doubled: Whether the hand has been doubled down.
        surrendered: Whether the player surrendered this hand.
        from_split: Whether this hand originated from a split.
    """

    cards: List[int] = field(default_factory=list)
    bet: float = 0.0
    doubled: bool = False
    surrendered: bool = False
    from_split: bool = False

    def add_card(self, card: int) -> None:
        """Append a card to this hand."""
        self.cards.append(card)

    def total(self) -> int:
        """Return the best possible hand total.

        Counts one Ace as 11 if it does not cause a bust; otherwise all
        Aces count as 1.  Returns the lowest bust value if all totals > 21.

        Returns:
            Best total ≤ 21 when possible; raw hard total otherwise.
        """
        hard_total = sum(card_value(c) for c in self.cards)
        aces = sum(1 for c in self.cards if c == 1)
        if aces > 0 and hard_total + 10 <= 21:
            return hard_total + 10
        return hard_total

    def is_soft(self) -> bool:
        """Return True if the hand contains a usable Ace (counted as 11)."""
        hard_total = sum(card_value(c) for c in self.cards)
        aces = sum(1 for c in self.cards if c == 1)
        return aces > 0 and hard_total + 10 <= 21

    def is_blackjack(self) -> bool:
        """Return True if the hand is a natural blackjack (2 cards totaling 21)."""
        return len(self.cards) == 2 and self.total() == 21

    def is_bust(self) -> bool:
        """Return True if the hand total exceeds 21."""
        return self.total() > 21

    def can_split(self) -> bool:
        """Return True if the hand is a splittable pair (same point value, 2 cards)."""
        if len(self.cards) != 2:
            return False
        return card_value(self.cards[0]) == card_value(self.cards[1])


# ---------------------------------------------------------------------------
# Shoe
# ---------------------------------------------------------------------------

class Shoe:
    """A shuffled multi-deck shoe of playing cards.

    Cards are represented as integer ranks 1–13 (four suits per rank per deck).
    The cut card is placed at ``penetration`` × total cards into the shoe.
    """

    def __init__(self, rules: GameRules, seed: Optional[int] = None) -> None:
        """Initialise and shuffle a new shoe.

        Args:
            rules: Game rules (uses ``rules.decks`` and ``rules.penetration``).
            seed: Optional RNG seed for reproducibility.
        """
        self.rules = rules
        self._seed = seed
        self._cards: List[int] = []
        self._position: int = 0
        self._cut_card: int = 0
        self._build_and_shuffle()

    def _build_and_shuffle(self) -> None:
        """Build N decks, shuffle, and place the cut card."""
        one_deck = list(range(1, 14)) * 4          # ranks 1-13, four suits each
        self._cards = one_deck * self.rules.decks
        rng = random.Random(self._seed)
        rng.shuffle(self._cards)
        self._position = 0
        total = len(self._cards)
        self._cut_card = int(total * self.rules.penetration)

    def deal(self) -> int:
        """Deal and return the next card from the shoe.

        Returns:
            Integer rank 1–13.

        Raises:
            RuntimeError: If the shoe is exhausted.
        """
        if self._position >= len(self._cards):
            raise RuntimeError("Shoe is exhausted — reshuffle before dealing.")
        card = self._cards[self._position]
        self._position += 1
        return card

    def cards_remaining(self) -> int:
        """Return the number of cards remaining in the shoe."""
        return len(self._cards) - self._position

    def cut_card_reached(self) -> bool:
        """Return True if dealing has passed the cut-card position."""
        return self._position >= self._cut_card

    def reshuffle(self, seed: Optional[int] = None) -> None:
        """Reshuffle the shoe (advance seed automatically if none provided).

        Args:
            seed: Explicit seed for the new shuffle.  If omitted and the shoe
                was originally seeded, the seed is incremented by 1.
        """
        if seed is not None:
            self._seed = seed
        elif self._seed is not None:
            self._seed += 1
        self._build_and_shuffle()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _play_hand(
    hand: Hand,
    shoe: Shoe,
    dealer_up: int,
    rules: GameRules,
    strategy_fn: Callable[[Hand, int, GameRules], str],
    split_count: int,
    is_split_aces: bool,
) -> List[Hand]:
    """Recursively play out a single hand, handling splits.

    Args:
        hand: The hand to play (already has its initial 2 cards).
        shoe: Active shoe to deal from.
        dealer_up: Dealer's visible upcard rank.
        rules: Active game rules.
        strategy_fn: Callable ``(hand, dealer_upcard, rules) -> action`` where
            action is one of ``"hit"``, ``"stand"``, ``"double"``,
            ``"split"``, ``"surrender"``.
        split_count: Number of splits already performed this round.
        is_split_aces: True if this hand is the result of splitting aces
            (receives exactly one additional card, no further action).

    Returns:
        List of completed Hand objects (may be >1 after splits).
    """
    # Aces from a split get exactly one additional card, which was already dealt
    # during the split setup before this call — no further action permitted.
    if is_split_aces:
        return [hand]

    while not hand.is_bust():
        can_surrender = (
            rules.surrender
            and len(hand.cards) == 2
            and not hand.from_split   # late surrender not offered on split hands
        )
        can_double = len(hand.cards) == 2 and (not hand.from_split or rules.das)
        # RSA governs *re*-splitting aces only; the initial ace split is always
        # permitted.  split_count == 0 means this is the first split this round.
        can_split = (
            hand.can_split()
            and split_count < rules.max_splits
            and (card_value(hand.cards[0]) != 1 or split_count == 0 or rules.rsa)
        )

        action = strategy_fn(hand, dealer_up, rules)

        if action == "surrender":
            if can_surrender:
                hand.surrendered = True
                return [hand]
            # Surrender not available — fall through to re-ask implicitly:
            # treat as stand to avoid infinite loops.
            return [hand]

        if action == "split":
            if can_split:
                c1, c2 = hand.cards[0], hand.cards[1]
                new_split_count = split_count + 1
                splitting_aces = card_value(c1) == 1

                h1 = Hand(cards=[c1], bet=hand.bet, from_split=True)
                h1.add_card(shoe.deal())
                h2 = Hand(cards=[c2], bet=hand.bet, from_split=True)
                h2.add_card(shoe.deal())

                completed: List[Hand] = []
                completed.extend(
                    _play_hand(h1, shoe, dealer_up, rules, strategy_fn,
                               new_split_count, splitting_aces)
                )
                completed.extend(
                    _play_hand(h2, shoe, dealer_up, rules, strategy_fn,
                               new_split_count, splitting_aces)
                )
                return completed
            # Split not available — fall back to stand.
            return [hand]

        if action == "double":
            if can_double:
                hand.bet *= 2.0
                hand.doubled = True
                hand.add_card(shoe.deal())
                return [hand]   # exactly one card on a double
            # Double not available — fall back to hit.
            hand.add_card(shoe.deal())
            continue

        if action == "hit":
            hand.add_card(shoe.deal())
            continue

        # "stand" (or any unrecognised action)
        return [hand]

    return [hand]  # busted


def _play_dealer(dealer_hand: Hand, shoe: Shoe, rules: GameRules) -> None:
    """Play out the dealer's hand in-place according to H17/S17 rules.

    Args:
        dealer_hand: Dealer's hand (already has 2 cards).
        shoe: Active shoe.
        rules: Active game rules (uses ``rules.h17``).
    """
    while True:
        total = dealer_hand.total()
        soft = dealer_hand.is_soft()

        if total > 17:
            break
        if total == 17:
            if not soft:
                break                       # always stand on hard 17
            if not rules.h17:
                break                       # S17: stand on soft 17
            # H17: hit soft 17 — fall through to deal

        dealer_hand.add_card(shoe.deal())


def _settle(player_hand: Hand, dealer_hand: Hand, rules: GameRules) -> float:
    """Calculate the net payout for one completed player hand.

    Args:
        player_hand: A completed player hand (possibly busted, surrendered, etc.).
        dealer_hand: The fully-played dealer hand.
        rules: Active game rules (uses ``rules.bj_payout``).

    Returns:
        Net dollar amount: positive for a win, negative for a loss, 0 for push.
    """
    if player_hand.surrendered:
        return -player_hand.bet / 2.0

    if player_hand.is_bust():
        return -player_hand.bet

    # Natural blackjack — only valid on the original (non-split) hand.
    if player_hand.is_blackjack() and not player_hand.from_split:
        # Dealer BJ is already handled in play_round before this point.
        return player_hand.bet * rules.bj_payout

    player_total = player_hand.total()
    dealer_total = dealer_hand.total()

    if dealer_hand.is_bust():
        return player_hand.bet

    if player_total > dealer_total:
        return player_hand.bet
    if player_total < dealer_total:
        return -player_hand.bet
    return 0.0   # push


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def play_round(
    shoe: Shoe,
    player_bet: float,
    rules: GameRules,
    strategy_fn: Callable[[Hand, int, GameRules], str],
) -> float:
    """Deal and resolve a complete round of blackjack.

    Follows standard US rules: dealer peeks for blackjack before player acts.
    Resolves all splits, doubles, and surrender according to ``rules``.

    Args:
        shoe: The active shoe (cards are consumed in place).
        player_bet: Initial wager in dollars.
        rules: Active game rules.
        strategy_fn: Callable ``(hand, dealer_upcard, rules) -> action``.
            Must return one of ``"hit"``, ``"stand"``, ``"double"``,
            ``"split"``, ``"surrender"``.

    Returns:
        Net dollar payout across all hands (positive = profit, negative = loss).
    """
    # --- Deal initial cards (US order: P, D_up, P, D_hole) ---
    player_hand = Hand(bet=player_bet)
    dealer_hand = Hand()

    player_hand.add_card(shoe.deal())
    dealer_up = shoe.deal()
    player_hand.add_card(shoe.deal())
    dealer_hole = shoe.deal()
    dealer_hand.add_card(dealer_up)
    dealer_hand.add_card(dealer_hole)

    # --- Dealer peek (US rules) ---
    dealer_bj = dealer_hand.is_blackjack()
    player_bj = player_hand.is_blackjack()

    if dealer_bj:
        return 0.0 if player_bj else -player_bet

    if player_bj:
        return player_bet * rules.bj_payout

    # --- Player acts ---
    completed_hands = _play_hand(
        player_hand, shoe, dealer_up, rules, strategy_fn,
        split_count=0, is_split_aces=False,
    )

    # --- Dealer acts only if at least one non-busted, non-surrendered hand remains ---
    all_resolved = all(h.is_bust() or h.surrendered for h in completed_hands)
    if not all_resolved:
        _play_dealer(dealer_hand, shoe, rules)

    # --- Settle all hands ---
    return sum(_settle(h, dealer_hand, rules) for h in completed_hands)
