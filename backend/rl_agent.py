"""
rl_agent.py — Q-learning blackjack agent.

Learns a blackjack playing strategy from scratch by interacting with the
simulator's game engine over millions of hands.  Uses Monte Carlo (every-visit)
Q-learning with epsilon-greedy exploration.

After training, the agent's learned policy can be:
  * Extracted as a dict mapping state → best Action
  * Compared against standard basic strategy to show agreements / disagreements

Public surface:
    State            — NamedTuple (player_total, dealer_upcard, is_soft, can_split)
    PolicyDiff       — dataclass holding the agreement/disagreement analysis
    QLearningAgent   — main agent class
    train_agent      — convenience function: create + train agent
    compare_to_basic_strategy — compare learned policy to basic_strategy
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

from backend.engine import GameRules, Hand, Shoe, card_value, play_round
from backend.strategy import Action, basic_strategy


# ---------------------------------------------------------------------------
# State representation
# ---------------------------------------------------------------------------

class State(NamedTuple):
    """Compact representation of a blackjack decision point.

    Attributes:
        player_total:  Best hand total (11 for soft ace counted as 11).
        dealer_upcard: Dealer's visible card value (1=Ace, 2-9, 10=face).
        is_soft:       True if the hand contains a usable Ace.
        can_split:     True if the hand is a splittable pair.
    """
    player_total: int
    dealer_upcard: int
    is_soft: bool
    can_split: bool


def _hand_to_state(hand: Hand, dealer_upcard: int) -> State:
    """Convert a Hand + dealer upcard to a State tuple.

    Args:
        hand:         Player's current hand.
        dealer_upcard: Raw rank of dealer's face-up card.

    Returns:
        State NamedTuple.
    """
    return State(
        player_total=hand.total(),
        dealer_upcard=card_value(dealer_upcard),
        is_soft=hand.is_soft(),
        can_split=hand.can_split(),
    )


# ---------------------------------------------------------------------------
# Policy diff
# ---------------------------------------------------------------------------

@dataclass
class PolicyDiff:
    """Comparison of the learned Q-policy against basic strategy.

    Attributes:
        total_states:    Number of distinct states evaluated.
        agreements:      States where learned and basic strategy agree.
        disagreements:   States where they differ.
        agreement_rate:  Fraction of states in agreement.
        diff_table:      List of (state, learned_action, basic_action) for disagreements.
        coverage:        Fraction of the canonical state space covered by the Q-table.
    """
    total_states: int
    agreements: int
    disagreements: int
    agreement_rate: float
    diff_table: List[Tuple[State, Action, Action]]
    coverage: float


# ---------------------------------------------------------------------------
# Q-learning agent
# ---------------------------------------------------------------------------

# Actions available to the agent (INSURANCE excluded — side-bet, not in scope).
_ACTIONS: List[Action] = [Action.HIT, Action.STAND, Action.DOUBLE, Action.SURRENDER]
_ACTION_IDX: Dict[Action, int] = {a: i for i, a in enumerate(_ACTIONS)}


class QLearningAgent:
    """Monte Carlo Q-learning agent for blackjack.

    Uses an epsilon-greedy policy with decaying epsilon.  Q-values are updated
    using every-visit Monte Carlo returns (no bootstrapping), which is
    well-suited to episodic blackjack hands.

    The Q-table maps ``State → {Action: Q-value}``.  On each hand, the agent
    records (state, action, reward) tuples and updates Q-values after the hand
    resolves.

    Args:
        rules:         Game rules for training.
        alpha:         Learning rate (default 0.1).
        gamma:         Discount factor (default 1.0 — episodic game, no discount).
        epsilon_start: Initial exploration rate (default 1.0).
        epsilon_end:   Minimum exploration rate (default 0.05).
        epsilon_decay: Multiplicative decay per hand (default 0.999995).
        seed:          Optional RNG seed for reproducibility.
    """

    def __init__(
        self,
        rules: GameRules,
        alpha: float = 0.1,
        gamma: float = 1.0,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: float = 0.999995,
        seed: Optional[int] = None,
    ) -> None:
        self.rules   = rules
        self.alpha   = alpha
        self.gamma   = gamma
        self.epsilon = epsilon_start
        self.epsilon_end   = epsilon_end
        self.epsilon_decay = epsilon_decay
        self._rng    = random.Random(seed)
        self._np_seed = seed

        # Q-table: state → action → value
        self._q: Dict[State, Dict[Action, float]] = {}
        self.hands_trained: int = 0

    # ── Q-table accessors ────────────────────────────────────────────────────

    def _q_values(self, state: State) -> Dict[Action, float]:
        """Return (initialise if absent) Q-values for a state."""
        if state not in self._q:
            self._q[state] = {a: 0.0 for a in _ACTIONS}
        return self._q[state]

    def _best_action(self, state: State) -> Action:
        """Return the greedy action with the highest Q-value for a state."""
        qv = self._q_values(state)
        return max(qv, key=lambda a: qv[a])

    # ── Strategy callable (for play_round integration) ────────────────────────

    def _make_strategy(self, episode: List[Tuple[State, Action]]) -> Callable:
        """Return a strategy callable that uses epsilon-greedy and records transitions.

        The ``episode`` list is populated in-place so the caller can update
        Q-values after the hand resolves.

        Args:
            episode: Mutable list to append (state, action) pairs to.

        Returns:
            Callable ``(hand, dealer_upcard, rules) → action`` string.
        """
        agent = self  # capture for closure

        def strategy(hand: Hand, dealer_upcard: int, rules: GameRules) -> str:
            state = _hand_to_state(hand, dealer_upcard)
            qv    = agent._q_values(state)

            # Epsilon-greedy selection.
            if agent._rng.random() < agent.epsilon:
                action = agent._rng.choice(_ACTIONS)
            else:
                action = agent._best_action(state)

            episode.append((state, action))
            return action   # Action(str, Enum) — engine accepts it directly

        return strategy

    # ── Training ─────────────────────────────────────────────────────────────

    def train(self, num_hands: int, bet: float = 10.0) -> None:
        """Train the agent by playing ``num_hands`` blackjack hands.

        Each hand is a fresh deal from a freshly shuffled single-deck shoe
        (avoids counting effects — we want to learn pure strategy).

        Q-values are updated at the end of each hand using the actual reward:

            Q(s, a) ← Q(s, a) + α × (G - Q(s, a))

        where G is the terminal reward (net payout) for the hand.  For a
        single-decision hand this is equivalent to TD(0).

        Args:
            num_hands: Number of hands to train on.
            bet:       Fixed bet amount per hand (irrelevant for strategy
                       learning but required by play_round).
        """
        seed_base = self._np_seed if self._np_seed is not None else 0

        for hand_idx in range(num_hands):
            # Fresh shoe for each hand to avoid deck composition effects.
            shoe_seed = seed_base + hand_idx if self._np_seed is not None else None
            shoe = Shoe(self.rules, seed=shoe_seed)

            episode: List[Tuple[State, Action]] = []
            strategy = self._make_strategy(episode)

            reward = play_round(shoe, bet, self.rules, strategy)

            # ── Q update (every-visit MC with G = terminal reward) ───────────
            for state, action in episode:
                qv = self._q_values(state)
                qv[action] += self.alpha * (reward - qv[action])

            # Decay epsilon.
            self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
            self.hands_trained += 1

    # ── Policy extraction ─────────────────────────────────────────────────────

    def get_policy(self) -> Dict[State, Action]:
        """Return the greedy policy as a state → action mapping.

        Only states that have been visited at least once are included.

        Returns:
            Dict mapping every visited :class:`State` to its best :class:`Action`.
        """
        return {state: self._best_action(state) for state in self._q}

    def action_for(self, hand: Hand, dealer_upcard: int) -> Action:
        """Return the agent's greedy action for a given hand.

        Falls back to basic strategy if the state has never been visited.

        Args:
            hand:          Player's current hand.
            dealer_upcard: Raw rank of dealer's visible card.

        Returns:
            Best :class:`Action` according to the Q-table, or basic strategy
            if the state is unknown.
        """
        state = _hand_to_state(hand, dealer_upcard)
        if state in self._q:
            return self._best_action(state)
        return basic_strategy(hand, dealer_upcard, self.rules)


# ---------------------------------------------------------------------------
# Convenience: train_agent
# ---------------------------------------------------------------------------

def train_agent(
    rules: GameRules,
    num_hands: int = 2_000_000,
    alpha: float = 0.1,
    epsilon_start: float = 1.0,
    epsilon_end: float = 0.05,
    epsilon_decay: float = 0.999995,
    seed: Optional[int] = None,
) -> QLearningAgent:
    """Create and train a Q-learning agent.

    Args:
        rules:          Game rules for training.
        num_hands:      Number of hands to train on (default 2 M).
        alpha:          Learning rate.
        epsilon_start:  Initial exploration rate.
        epsilon_end:    Minimum exploration rate.
        epsilon_decay:  Per-hand multiplicative epsilon decay.
        seed:           Optional seed for reproducibility.

    Returns:
        Trained :class:`QLearningAgent`.
    """
    agent = QLearningAgent(
        rules=rules,
        alpha=alpha,
        epsilon_start=epsilon_start,
        epsilon_end=epsilon_end,
        epsilon_decay=epsilon_decay,
        seed=seed,
    )
    agent.train(num_hands)
    return agent


# ---------------------------------------------------------------------------
# Policy comparison
# ---------------------------------------------------------------------------

def compare_to_basic_strategy(
    agent: QLearningAgent,
    rules: Optional[GameRules] = None,
) -> PolicyDiff:
    """Compare the agent's learned policy against basic strategy.

    Iterates over the canonical hard-total state space (player totals 4–21,
    dealer upcards 2–11, soft and hard variants) and records where the
    learned policy agrees or disagrees with ``basic_strategy``.

    States for which the agent has no Q-table entry (never visited) are
    counted as missing and do not contribute to the diff table.

    Args:
        agent: Trained :class:`QLearningAgent`.
        rules: Game rules for basic-strategy lookup.  Defaults to
               ``agent.rules`` if not supplied.

    Returns:
        :class:`PolicyDiff` with agreement statistics and diff table.
    """
    if rules is None:
        rules = agent.rules

    # ── Build canonical state space ──────────────────────────────────────────
    # Hard totals 4–20, dealer upcards 1(Ace)/2–10, not soft, not split.
    # Soft totals 12–20 (soft 12 = A+A counted as soft, but we use 12–20 for A+1..A+9).
    # We exclude totals ≥ 21 since basic strategy always STAND.
    canonical_states: List[State] = []

    for dealer_up in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        # Hard totals 4–20
        for total in range(4, 21):
            canonical_states.append(State(total, dealer_up, False, False))
        # Soft totals 12–20 (e.g., soft 13 = A+2, soft 20 = A+9)
        for total in range(12, 21):
            canonical_states.append(State(total, dealer_up, True, False))

    total_canonical = len(canonical_states)

    # ── Compare ─────────────────────────────────────────────────────────────
    policy = agent.get_policy()
    visited_canonical = sum(1 for s in canonical_states if s in policy)
    coverage = visited_canonical / total_canonical if total_canonical > 0 else 0.0

    agreements = 0
    disagreements = 0
    diff_table: List[Tuple[State, Action, Action]] = []

    for state in canonical_states:
        if state not in policy:
            continue  # agent never visited this state

        learned = policy[state]

        # Reconstruct a minimal Hand to call basic_strategy.
        bs_action = _basic_strategy_for_state(state, rules)
        if bs_action is None:
            continue  # state has no basic strategy answer (shouldn't happen)

        if learned == bs_action:
            agreements += 1
        else:
            disagreements += 1
            diff_table.append((state, learned, bs_action))

    total_compared = agreements + disagreements
    agreement_rate = agreements / total_compared if total_compared > 0 else 0.0

    return PolicyDiff(
        total_states=total_compared,
        agreements=agreements,
        disagreements=disagreements,
        agreement_rate=agreement_rate,
        diff_table=diff_table,
        coverage=coverage,
    )


def _basic_strategy_for_state(state: State, rules: GameRules) -> Optional[Action]:
    """Look up basic strategy for a canonical state.

    Builds a minimal Hand that matches the state's total, softness, and
    split-ability, then calls basic_strategy.

    Args:
        state: The canonical state to look up.
        rules: Game rules for strategy lookup.

    Returns:
        Basic strategy :class:`Action`, or None if the hand can't be
        constructed.
    """
    hand = _build_hand_for_state(state)
    if hand is None:
        return None
    # Reconstruct dealer upcard: State uses card_value form (1=Ace, 2-9, 10).
    # We need a raw rank for the strategy function; use rank = upcard value (1→1, 10→10).
    dealer_upcard = state.dealer_upcard  # already normalised
    return basic_strategy(hand, dealer_upcard, rules)


def _build_hand_for_state(state: State) -> Optional[Hand]:
    """Build a Hand that matches the given State for strategy lookup.

    Args:
        state: Target state (total, softness, split-ability).

    Returns:
        A minimal :class:`Hand`, or None if the state can't be reconstructed.
    """
    total = state.player_total

    if state.can_split:
        # Pair of cards with equal value.  Use half the total.
        half = total // 2
        if half < 1 or half > 10:
            return None
        # Map value back to rank: for 10-value use rank 10; Ace = 1.
        rank = 1 if half == 1 else (10 if half == 10 else half)
        hand = Hand(cards=[rank, rank], bet=10.0)
        return hand

    if state.is_soft:
        # Soft hand: Ace (rank 1) + a card.  Total = 1 + extra + 10 (ace as 11).
        # extra_val = total - 11.
        extra_val = total - 11
        if extra_val < 1 or extra_val > 9:
            return None
        hand = Hand(cards=[1, extra_val], bet=10.0)
        return hand

    # Hard hand: two cards that sum to total (without any Ace as 11).
    # Use 10 + (total - 10) if total >= 12, else split the total.
    if total <= 11:
        # E.g., hard 10 = 5+5, hard 9 = 4+5, hard 8 = 4+4, etc.
        hi = min(total - 1, 10)
        lo = total - hi
        if lo < 2:
            lo = 2; hi = total - lo
        hand = Hand(cards=[hi, lo], bet=10.0)
        return hand
    else:
        # Hard 12–20: 10 + (total - 10).  Ensure no Ace (would make it soft).
        second = total - 10
        if second > 10:
            second = 10  # cap at 10-value
        # Verify: no aces, correct total.
        hand = Hand(cards=[10, second], bet=10.0)
        if hand.total() == total and not hand.is_soft():
            return hand
        # Fallback: try 9 + (total - 9)
        second = total - 9
        if 2 <= second <= 10:
            hand = Hand(cards=[9, second], bet=10.0)
            if hand.total() == total and not hand.is_soft():
                return hand
        return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_policy_diff(diff: PolicyDiff) -> str:
    """Render a PolicyDiff as a plain-text report.

    Args:
        diff: Output of :func:`compare_to_basic_strategy`.

    Returns:
        Multi-line string suitable for printing or logging.
    """
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("  Q-LEARNING AGENT vs. BASIC STRATEGY")
    lines.append("=" * 72)
    lines.append(f"  States compared : {diff.total_states}")
    lines.append(f"  Coverage        : {diff.coverage:.1%} of canonical state space")
    lines.append(f"  Agreement rate  : {diff.agreement_rate:.1%}")
    lines.append(f"  Agreements      : {diff.agreements}")
    lines.append(f"  Disagreements   : {diff.disagreements}")
    lines.append("")

    if diff.diff_table:
        lines.append("  DISAGREEMENTS")
        lines.append(f"  {'State':<45} {'Learned':>10} {'Basic':>10}")
        lines.append("-" * 72)
        for state, learned, bs in sorted(diff.diff_table):
            up_str = "A" if state.dealer_upcard == 1 else str(state.dealer_upcard)
            soft_str = "soft" if state.is_soft else "hard"
            state_str = f"total={state.player_total} ({soft_str}) vs dealer {up_str}"
            lines.append(f"  {state_str:<45} {learned.value:>10} {bs.value:>10}")
    else:
        lines.append("  (no disagreements — perfect agreement with basic strategy)")

    lines.append("=" * 72)
    return "\n".join(lines)
