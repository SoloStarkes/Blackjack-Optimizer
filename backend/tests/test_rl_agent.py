"""
test_rl_agent.py — Tests for backend/rl_agent.py.

Covers:
  - State NamedTuple construction
  - QLearningAgent initialisation and Q-table structure
  - Short training: Q-table populated, epsilon decays, hands_trained increments
  - get_policy: returns state→action dict, actions are valid
  - action_for: falls back to basic strategy for unseen states
  - compare_to_basic_strategy: PolicyDiff structure and coverage
  - Longer training (200k hands): agreement rate improves significantly
  - train_agent convenience function
  - _build_hand_for_state: hand construction correctness
  - format_policy_diff: renders without error
"""

from __future__ import annotations

import pytest

from backend.engine import GameRules, Hand
from backend.rl_agent import (
    PolicyDiff,
    QLearningAgent,
    State,
    _basic_strategy_for_state,
    _build_hand_for_state,
    _hand_to_state,
    compare_to_basic_strategy,
    format_policy_diff,
    train_agent,
)
from backend.strategy import Action, basic_strategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rules():
    return GameRules(decks=1, penetration=0.75, h17=True, das=True, rsa=True,
                     max_splits=3, surrender=True, bj_payout=1.5)


@pytest.fixture(scope="module")
def short_agent(rules):
    """Agent trained for 10 000 hands — enough to populate Q-table, quick."""
    agent = QLearningAgent(rules=rules, seed=42)
    agent.train(10_000)
    return agent


@pytest.fixture(scope="module")
def medium_agent(rules):
    """Agent trained for 200 000 hands — should show decent agreement."""
    agent = QLearningAgent(rules=rules, seed=7, epsilon_decay=0.99999)
    agent.train(200_000)
    return agent


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

class TestState:
    def test_namedtuple_fields(self):
        s = State(player_total=16, dealer_upcard=10, is_soft=False, can_split=False)
        assert s.player_total == 16
        assert s.dealer_upcard == 10
        assert s.is_soft is False
        assert s.can_split is False

    def test_hashable(self):
        s = State(16, 10, False, False)
        d = {s: "test"}
        assert d[s] == "test"

    def test_equality(self):
        assert State(16, 10, False, False) == State(16, 10, False, False)
        assert State(16, 10, False, False) != State(16, 9, False, False)

    def test_hand_to_state_hard(self, rules):
        hand = Hand(cards=[9, 7], bet=10.0)   # hard 16
        state = _hand_to_state(hand, 10)
        assert state.player_total == 16
        assert state.dealer_upcard == 10
        assert state.is_soft is False
        assert state.can_split is False

    def test_hand_to_state_soft(self, rules):
        hand = Hand(cards=[1, 6], bet=10.0)   # soft 17
        state = _hand_to_state(hand, 5)
        assert state.player_total == 17
        assert state.is_soft is True
        assert state.can_split is False

    def test_hand_to_state_pair(self, rules):
        hand = Hand(cards=[8, 8], bet=10.0)   # pair of 8s
        state = _hand_to_state(hand, 10)
        assert state.player_total == 16
        assert state.can_split is True

    def test_hand_to_state_ace_upcard(self, rules):
        hand = Hand(cards=[9, 7], bet=10.0)
        state = _hand_to_state(hand, 1)  # Ace upcard
        assert state.dealer_upcard == 1


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_hands_trained_zero(self, rules):
        agent = QLearningAgent(rules=rules)
        assert agent.hands_trained == 0

    def test_epsilon_starts_at_one(self, rules):
        agent = QLearningAgent(rules=rules, epsilon_start=1.0)
        assert agent.epsilon == pytest.approx(1.0)

    def test_empty_q_table(self, rules):
        agent = QLearningAgent(rules=rules)
        assert len(agent.get_policy()) == 0

    def test_custom_alpha(self, rules):
        agent = QLearningAgent(rules=rules, alpha=0.05)
        assert agent.alpha == 0.05

    def test_custom_epsilon_end(self, rules):
        agent = QLearningAgent(rules=rules, epsilon_end=0.1)
        assert agent.epsilon_end == 0.1


# ---------------------------------------------------------------------------
# Short training
# ---------------------------------------------------------------------------

class TestShortTraining:
    def test_hands_trained_incremented(self, short_agent):
        assert short_agent.hands_trained == 10_000

    def test_epsilon_decayed(self, short_agent):
        assert short_agent.epsilon < 1.0

    def test_epsilon_above_minimum(self, short_agent):
        assert short_agent.epsilon >= short_agent.epsilon_end

    def test_q_table_populated(self, short_agent):
        assert len(short_agent._q) > 0

    def test_q_table_has_multiple_states(self, short_agent):
        # Should have visited many distinct states.
        assert len(short_agent._q) >= 50

    def test_actions_in_q_table(self, short_agent):
        for state, qv in list(short_agent._q.items())[:5]:
            assert set(qv.keys()) == set([Action.HIT, Action.STAND,
                                           Action.DOUBLE, Action.SURRENDER])


# ---------------------------------------------------------------------------
# get_policy
# ---------------------------------------------------------------------------

class TestGetPolicy:
    def test_returns_dict(self, short_agent):
        policy = short_agent.get_policy()
        assert isinstance(policy, dict)

    def test_values_are_actions(self, short_agent):
        policy = short_agent.get_policy()
        for action in policy.values():
            assert isinstance(action, Action)
            assert action in [Action.HIT, Action.STAND, Action.DOUBLE, Action.SURRENDER]

    def test_keys_are_states(self, short_agent):
        policy = short_agent.get_policy()
        for s in list(policy.keys())[:5]:
            assert isinstance(s, State)

    def test_policy_size_matches_q_table(self, short_agent):
        assert len(short_agent.get_policy()) == len(short_agent._q)


# ---------------------------------------------------------------------------
# action_for
# ---------------------------------------------------------------------------

class TestActionFor:
    def test_returns_action(self, short_agent):
        hand = Hand(cards=[9, 7], bet=10.0)
        action = short_agent.action_for(hand, 10)
        assert isinstance(action, Action)

    def test_fallback_to_basic_strategy(self, rules):
        """For an unseen state, should return basic strategy."""
        agent = QLearningAgent(rules=rules, seed=0)
        # No training — all states unseen.
        hand = Hand(cards=[9, 7], bet=10.0)
        bs_action = basic_strategy(hand, 10, rules)
        rl_action  = agent.action_for(hand, 10)
        assert rl_action == bs_action

    def test_valid_action_for_various_hands(self, short_agent, rules):
        test_cases = [
            (Hand(cards=[5, 6], bet=10.0), 7),    # hard 11 vs 7
            (Hand(cards=[1, 6], bet=10.0), 5),    # soft 17 vs 5
            (Hand(cards=[8, 8], bet=10.0), 10),   # pair of 8s vs 10
            (Hand(cards=[10, 6], bet=10.0), 10),  # hard 16 vs 10
        ]
        for hand, dealer_up in test_cases:
            action = short_agent.action_for(hand, dealer_up)
            assert action in [Action.HIT, Action.STAND, Action.DOUBLE,
                               Action.SPLIT, Action.SURRENDER], \
                f"Unexpected action {action} for {hand.total()} vs {dealer_up}"


# ---------------------------------------------------------------------------
# compare_to_basic_strategy
# ---------------------------------------------------------------------------

class TestCompareToBasicStrategy:
    def test_returns_policy_diff(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert isinstance(diff, PolicyDiff)

    def test_total_states_positive(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert diff.total_states > 0

    def test_agreement_rate_in_range(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert 0.0 <= diff.agreement_rate <= 1.0

    def test_agreements_plus_disagreements_equals_total(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert diff.agreements + diff.disagreements == diff.total_states

    def test_coverage_in_range(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert 0.0 <= diff.coverage <= 1.0

    def test_diff_table_is_list(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert isinstance(diff.diff_table, list)

    def test_diff_table_length_matches_disagreements(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        assert len(diff.diff_table) == diff.disagreements

    def test_diff_table_entries_are_tuples(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        for entry in diff.diff_table:
            state, learned, bs = entry
            assert isinstance(state, State)
            assert isinstance(learned, Action)
            assert isinstance(bs, Action)

    def test_coverage_increases_with_training(self, short_agent, medium_agent):
        diff_short  = compare_to_basic_strategy(short_agent)
        diff_medium = compare_to_basic_strategy(medium_agent)
        # More training should cover at least as many states.
        assert diff_medium.coverage >= diff_short.coverage


# ---------------------------------------------------------------------------
# Agreement rate after more training
# ---------------------------------------------------------------------------

class TestAgreementAfterTraining:
    def test_medium_agent_reasonable_agreement(self, medium_agent):
        """After 200k hands, agent should agree with basic strategy ≥30% of the time.

        This is a lenient bound — 200k hands is not enough for perfect
        convergence, but the Q-table should have learned enough signal."""
        diff = compare_to_basic_strategy(medium_agent)
        assert diff.agreement_rate >= 0.30, (
            f"Expected ≥30% agreement after 200k hands, got {diff.agreement_rate:.1%}"
        )

    def test_medium_agent_high_coverage(self, medium_agent):
        """200k hands should cover most canonical states."""
        diff = compare_to_basic_strategy(medium_agent)
        assert diff.coverage >= 0.50, (
            f"Expected ≥50% coverage after 200k hands, got {diff.coverage:.1%}"
        )


# ---------------------------------------------------------------------------
# train_agent convenience function
# ---------------------------------------------------------------------------

class TestTrainAgent:
    def test_returns_trained_agent(self, rules):
        agent = train_agent(rules=rules, num_hands=5_000, seed=1)
        assert isinstance(agent, QLearningAgent)
        assert agent.hands_trained == 5_000

    def test_q_table_non_empty(self, rules):
        agent = train_agent(rules=rules, num_hands=5_000, seed=1)
        assert len(agent._q) > 0

    def test_epsilon_decayed(self, rules):
        agent = train_agent(rules=rules, num_hands=5_000, seed=1)
        assert agent.epsilon < 1.0


# ---------------------------------------------------------------------------
# _build_hand_for_state
# ---------------------------------------------------------------------------

class TestBuildHandForState:
    def test_hard_total_correct(self):
        state = State(player_total=16, dealer_upcard=10, is_soft=False, can_split=False)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 16
        assert not hand.is_soft()

    def test_soft_total_correct(self):
        state = State(player_total=17, dealer_upcard=5, is_soft=True, can_split=False)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 17
        assert hand.is_soft()

    def test_pair_total_correct(self):
        state = State(player_total=16, dealer_upcard=10, is_soft=False, can_split=True)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 16
        assert hand.can_split()

    def test_hard_11(self):
        state = State(player_total=11, dealer_upcard=6, is_soft=False, can_split=False)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 11

    def test_hard_20(self):
        state = State(player_total=20, dealer_upcard=10, is_soft=False, can_split=False)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 20

    def test_soft_12(self):
        # soft 12 = Ace + Ace (both count as 1 = hard 2, but A+1 = soft 12)
        state = State(player_total=12, dealer_upcard=4, is_soft=True, can_split=False)
        hand = _build_hand_for_state(state)
        assert hand is not None
        assert hand.total() == 12


# ---------------------------------------------------------------------------
# _basic_strategy_for_state
# ---------------------------------------------------------------------------

class TestBasicStrategyForState:
    def test_returns_action(self, rules):
        state = State(player_total=16, dealer_upcard=10, is_soft=False, can_split=False)
        action = _basic_strategy_for_state(state, rules)
        assert action is not None
        assert isinstance(action, Action)

    def test_hard_11_vs_6_double(self, rules):
        """Hard 11 vs dealer 6 should be DOUBLE."""
        state = State(player_total=11, dealer_upcard=6, is_soft=False, can_split=False)
        action = _basic_strategy_for_state(state, rules)
        assert action == Action.DOUBLE

    def test_hard_20_vs_10_stand(self, rules):
        """Hard 20 vs dealer 10 should be STAND."""
        state = State(player_total=20, dealer_upcard=10, is_soft=False, can_split=False)
        action = _basic_strategy_for_state(state, rules)
        assert action == Action.STAND

    def test_hard_8_vs_7_hit(self, rules):
        """Hard 8 vs dealer 7 should be HIT."""
        state = State(player_total=8, dealer_upcard=7, is_soft=False, can_split=False)
        action = _basic_strategy_for_state(state, rules)
        assert action == Action.HIT


# ---------------------------------------------------------------------------
# format_policy_diff
# ---------------------------------------------------------------------------

class TestFormatPolicyDiff:
    def test_returns_string(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        output = format_policy_diff(diff)
        assert isinstance(output, str)

    def test_contains_agreement_rate(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        output = format_policy_diff(diff)
        assert "%" in output

    def test_contains_headers(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        output = format_policy_diff(diff)
        assert "Q-LEARNING" in output

    def test_non_empty(self, short_agent):
        diff = compare_to_basic_strategy(short_agent)
        output = format_policy_diff(diff)
        assert len(output) > 50

    def test_perfect_agreement_message(self, rules):
        """When there are no disagreements, a friendly message should appear."""
        # Create a fake diff with zero disagreements.
        diff = PolicyDiff(
            total_states=100,
            agreements=100,
            disagreements=0,
            agreement_rate=1.0,
            diff_table=[],
            coverage=0.9,
        )
        output = format_policy_diff(diff)
        assert "perfect agreement" in output.lower() or "no disagreements" in output.lower()
