"""
simulator.py — Monte Carlo blackjack session simulator.

Wires together engine, strategy, and counting into a full session simulation:
  * Tracks the Hi-Lo running count through every dealt card.
  * Looks up the bet from the spread at the start of each round.
  * Applies Illustrious-18 / Fab-4 counting deviations on top of any base strategy.
  * Supports wonging out (bet = 0 → skip round, advance shoe, keep counting).
  * Returns per-round raw results and an aggregated SimulationResult.

Public surface:
    RoundResult       — NamedTuple (true_count, bet, payout)
    SimulationResult  — dataclass of aggregated session statistics
    simulate_session  — run N shoes, return List[RoundResult]
    aggregate_results — collapse a round list into a SimulationResult
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, NamedTuple, Optional

from backend.counting import Counter
from backend.engine import GameRules, Hand, Shoe, card_value, play_round
from backend.strategy import Action, basic_strategy, deviation


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class RoundResult(NamedTuple):
    """Outcome of a single played round.

    Attributes:
        true_count: Integer Hi-Lo true count at the start of the round.
        bet:        Initial wager in dollars (before any doubles / splits).
        payout:     Net dollar result — positive = won, negative = lost.
    """
    true_count: int
    bet: float
    payout: float


@dataclass
class SimulationResult:
    """Aggregated statistics for a complete simulated session.

    Attributes:
        total_hands:        Number of rounds actually played (wongs excluded).
        total_wagered:      Sum of all initial bets in dollars.
        total_won:          Sum of all net payouts in dollars.
        ev_per_hand:        Mean net payout per played hand (dollars).
        std_dev_per_hand:   Sample standard deviation of per-hand payouts.
        edge_by_true_count: For each integer true count seen, the player edge
                            expressed as mean(payout) / mean(bet).  Negative
                            means the house has the advantage at that count.
    """
    total_hands: int
    total_wagered: float
    total_won: float
    ev_per_hand: float
    std_dev_per_hand: float
    edge_by_true_count: Dict[int, float]


# ---------------------------------------------------------------------------
# Counting-aware shoe
# ---------------------------------------------------------------------------

class _CountingShoe(Shoe):
    """Shoe subclass that automatically updates a Counter on every deal().

    Reshuffle resets the counter so the new shoe starts at RC = 0.
    """

    def __init__(
        self, rules: GameRules, counter: Counter, seed: Optional[int] = None
    ) -> None:
        self._counter = counter
        super().__init__(rules, seed)

    def deal(self) -> int:  # type: ignore[override]
        card = super().deal()
        self._counter.update(card)
        return card

    def reshuffle(self, seed: Optional[int] = None) -> None:
        super().reshuffle(seed)
        self._counter.reset()


# ---------------------------------------------------------------------------
# Bet-spread lookup
# ---------------------------------------------------------------------------

def _bet_for_tc(bet_spread: Dict[int, float], tc: int) -> float:
    """Return the bet for a given true count using a step-function spread.

    Finds the highest key in ``bet_spread`` that is ≤ ``tc`` and returns its
    associated bet.  Returns 0.0 (wong out) if no key qualifies.

    Args:
        bet_spread: Mapping of true-count threshold → bet amount in dollars.
                    A bet of 0 signals "wong out" at that count.
        tc:         Current integer true count.

    Returns:
        Bet in dollars, or 0.0 if the count is below all thresholds.
    """
    eligible = [k for k in bet_spread if k <= tc]
    if not eligible:
        return 0.0
    return float(bet_spread[max(eligible)])


# ---------------------------------------------------------------------------
# Deviation-key helper
# ---------------------------------------------------------------------------

def _deviation_key(hand: Hand, dealer_upcard: int) -> Optional[str]:
    """Map a hand + upcard to its I18 / Fab-4 deviation lookup key.

    Returns ``None`` for hand types that have no counting deviation defined
    (e.g. soft totals other than pairs).

    Key format mirrors the keys in ``strategy._DEVIATIONS``:
    * ``"{total}v{upcard}"``   for hard totals (e.g. ``"16v10"``, ``"11vA"``)
    * ``"10,10v{upcard}"``     for a pair of tens (count-dependent split play)
    * Upcard ``"A"`` for Ace, ``"10"`` for ten-value, ``"2"``–``"9"`` literally.
    """
    up = card_value(dealer_upcard)                   # 1=Ace, 2-9, 10 for face
    up_str = "A" if up == 1 else str(up)

    # Pair of tens: deviation may override basic stand with a split
    if hand.can_split():
        pv = card_value(hand.cards[0])
        if pv == 10:
            return f"10,10v{up_str}"
        return None  # non-10 pairs: no deviation defined; use pair table

    # Soft totals: no I18 deviation keys; skip
    if hand.is_soft():
        return None

    # Hard total
    return f"{hand.total()}v{up_str}"


# ---------------------------------------------------------------------------
# Counting-strategy factory
# ---------------------------------------------------------------------------

def _make_round_strategy(
    base_strategy_fn: Callable[[Hand, int, GameRules], str],
    tc: int,
) -> Callable[[Hand, int, GameRules], str]:
    """Return a strategy function that layers I18/Fab-4 deviations over a base.

    The true count is captured as a closure variable so the returned callable
    matches the ``(hand, dealer_upcard, rules) -> action`` signature expected
    by ``play_round``.

    Args:
        base_strategy_fn: Base strategy (e.g. ``basic_strategy``).
        tc:               Integer true count at the start of this round.

    Returns:
        Strategy callable with deviation overrides baked in.
    """
    def strategy(hand: Hand, dealer_upcard: int, rules: GameRules) -> str:
        key = _deviation_key(hand, dealer_upcard)
        if key is not None:
            dev = deviation(key, tc)
            # INSURANCE is a side-bet signal, not a hand action — skip it.
            if dev is not None and dev is not Action.INSURANCE:
                return dev
        return base_strategy_fn(hand, dealer_upcard, rules)

    return strategy


# ---------------------------------------------------------------------------
# Minimum-cards guard
# ---------------------------------------------------------------------------

# Minimum cards that must remain in the shoe before we start a new round.
# Generous enough to cover a hand with 3 splits + doubles in each sub-hand.
_MIN_CARDS_FOR_ROUND = 20

# Cards consumed per wonged-out round (approximate heads-up hand: 2P + 2D).
_WONG_OUT_CARDS = 4


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

def simulate_session(
    rules: GameRules,
    bet_spread: Dict[int, float],
    strategy_fn: Callable[[Hand, int, GameRules], str],
    num_shoes: int,
    seed: Optional[int] = None,
) -> List[RoundResult]:
    """Simulate a full counting session across many shoes.

    For each round before the cut card:

    1. Compute the true count from the running count and cards remaining.
    2. Look up the bet from ``bet_spread``; if bet = 0, wong out (skip the
       round but still advance the shoe and update the count).
    3. Build a deviation-aware strategy wrapping ``strategy_fn``.
    4. Call ``play_round`` and record ``(true_count, bet, payout)``.
    5. Repeat until the cut card is reached, then reshuffle and continue
       for the next shoe.

    Args:
        rules:       Game rules (decks, penetration, H17, DAS, etc.).
        bet_spread:  Dict mapping true-count threshold → bet in dollars.
                     The step function uses the highest key ≤ current TC.
                     A bet of 0 means wong out at that count level.
        strategy_fn: Base strategy callable ``(hand, upcard, rules) → action``.
                     Counting deviations (I18 + Fab 4) are layered on top.
        num_shoes:   Number of shoes to simulate.
        seed:        Optional RNG seed for reproducibility.  Subsequent shoes
                     use seed + 1, seed + 2, … automatically.

    Returns:
        List of :class:`RoundResult` for every *played* round (wonged rounds
        are excluded from the list but still advance the shoe position and
        running count).
    """
    counter = Counter()
    shoe = _CountingShoe(rules, counter, seed=seed)
    rounds: List[RoundResult] = []

    for shoe_idx in range(num_shoes):
        if shoe_idx > 0:
            shoe.reshuffle()        # resets counter + rebuilds shuffled shoe

        while not shoe.cut_card_reached():
            # Guard: stop if too few cards remain to safely complete a round
            if shoe.cards_remaining() < _MIN_CARDS_FOR_ROUND:
                break

            # ── pre-round decision ──────────────────────────────────────────
            decks_rem = shoe.cards_remaining() / 52.0
            tc = counter.true_count(decks_rem)
            bet = _bet_for_tc(bet_spread, tc)

            # ── wong out ────────────────────────────────────────────────────
            if bet == 0:
                # Simulate one dealer-hand worth of cards passing.
                # _CountingShoe.deal() keeps the counter in sync.
                for _ in range(_WONG_OUT_CARDS):
                    if shoe.cards_remaining() == 0:
                        break
                    shoe.deal()
                    if shoe.cut_card_reached():
                        break
                continue

            # ── play the round ──────────────────────────────────────────────
            round_strategy = _make_round_strategy(strategy_fn, tc)
            payout = play_round(shoe, bet, rules, round_strategy)
            rounds.append(RoundResult(true_count=tc, bet=bet, payout=payout))

    return rounds


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_results(rounds: List[RoundResult]) -> SimulationResult:
    """Collapse a list of round results into summary statistics.

    Args:
        rounds: Raw output of :func:`simulate_session`.

    Returns:
        :class:`SimulationResult` with totals, EV, standard deviation, and
        per-TC edge.  All fields are 0.0 / empty when ``rounds`` is empty.
    """
    if not rounds:
        return SimulationResult(
            total_hands=0,
            total_wagered=0.0,
            total_won=0.0,
            ev_per_hand=0.0,
            std_dev_per_hand=0.0,
            edge_by_true_count={},
        )

    payouts = [r.payout for r in rounds]
    bets    = [r.bet    for r in rounds]

    total_hands   = len(rounds)
    total_wagered = sum(bets)
    total_won     = sum(payouts)
    ev_per_hand   = total_won / total_hands
    std_dev       = statistics.stdev(payouts) if total_hands > 1 else 0.0

    # ── edge by true count ──────────────────────────────────────────────────
    # Group payouts and initial bets by TC bucket.
    tc_payouts: Dict[int, List[float]] = defaultdict(list)
    tc_bets:    Dict[int, List[float]] = defaultdict(list)
    for r in rounds:
        tc_payouts[r.true_count].append(r.payout)
        tc_bets[r.true_count].append(r.bet)

    # Edge = mean(payout) / mean(bet) at each TC.
    # A negative edge means the house wins at that count; positive = player wins.
    edge_by_tc: Dict[int, float] = {}
    for tc, plist in tc_payouts.items():
        mean_bet = statistics.mean(tc_bets[tc])
        if mean_bet != 0:
            edge_by_tc[tc] = statistics.mean(plist) / mean_bet

    return SimulationResult(
        total_hands=total_hands,
        total_wagered=total_wagered,
        total_won=total_won,
        ev_per_hand=ev_per_hand,
        std_dev_per_hand=std_dev,
        edge_by_true_count=edge_by_tc,
    )
