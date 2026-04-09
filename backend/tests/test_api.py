"""
test_api.py — Integration tests for backend/api.py.

Uses FastAPI's TestClient (backed by httpx) so no live server is required.
All simulation calls use a small num_shoes (≤ 500) and a fixed seed so the
suite completes in a few seconds.
"""

from __future__ import annotations

import math
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from backend.api import app

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

MINIMAL_RULES: Dict[str, Any] = {
    "decks": 6,
    "penetration": 0.75,
    "h17": True,
    "das": True,
    "rsa": False,
    "max_splits": 3,
    "surrender": True,
    "bj_payout": 1.5,
}

# Wong-in at TC ≥ 1, spread to $200 at TC ≥ 5.
COUNTING_SPREAD: Dict[str, float] = {
    "0": 0.0,
    "1": 25.0,
    "2": 50.0,
    "3": 100.0,
    "4": 150.0,
    "5": 200.0,
}

FLAT_SPREAD: Dict[str, float] = {"0": 25.0}

MINIMAL_BODY: Dict[str, Any] = {
    "rules": MINIMAL_RULES,
    "bet_spread": COUNTING_SPREAD,
    "bankroll": 25_000,
    "rounds_per_hour": 100,
    "num_shoes": 200,
    "seed": 7,
}


# ===========================================================================
# GET /health
# ===========================================================================

class TestHealth:

    def test_status_200(self):
        r = client.get("/health")
        assert r.status_code == 200

    def test_body_ok(self):
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_version_present(self):
        r = client.get("/health")
        assert "version" in r.json()


# ===========================================================================
# POST /simulate — happy-path
# ===========================================================================

class TestSimulateHappyPath:

    @pytest.fixture(scope="class")
    def response(self):
        return client.post("/simulate", json=MINIMAL_BODY)

    @pytest.fixture(scope="class")
    def body(self, response):
        return response.json()

    def test_status_200(self, response):
        assert response.status_code == 200

    def test_ev_per_hour_present(self, body):
        assert "ev_per_hour" in body

    def test_std_dev_per_hour_present(self, body):
        assert "std_dev_per_hour" in body

    def test_risk_of_ruin_in_range(self, body):
        ror = body["risk_of_ruin"]
        assert 0.0 <= ror <= 1.0

    def test_hours_to_n0_present(self, body):
        assert "hours_to_n0" in body

    def test_score_present(self, body):
        assert "score" in body

    def test_total_hands_positive(self, body):
        assert body["total_hands"] > 0

    def test_total_wagered_positive(self, body):
        assert body["total_wagered"] > 0

    def test_edge_by_tc_is_dict(self, body):
        assert isinstance(body["edge_by_tc"], dict)

    def test_edge_by_tc_has_integer_keys(self, body):
        for key in body["edge_by_tc"]:
            assert isinstance(key, int) or (isinstance(key, str) and key.lstrip("-").isdigit())

    def test_sd_per_hour_positive(self, body):
        assert body["std_dev_per_hour"] > 0

    def test_ev_per_hand_present(self, body):
        assert "ev_per_hand" in body

    def test_std_dev_per_hand_present(self, body):
        assert "std_dev_per_hand" in body


# ===========================================================================
# POST /simulate — reproducibility
# ===========================================================================

class TestSimulateReproducibility:

    def test_same_seed_same_result(self):
        r1 = client.post("/simulate", json=MINIMAL_BODY).json()
        r2 = client.post("/simulate", json=MINIMAL_BODY).json()
        assert r1["ev_per_hour"] == r2["ev_per_hour"]
        assert r1["total_hands"] == r2["total_hands"]

    def test_different_seed_may_differ(self):
        body_a = {**MINIMAL_BODY, "seed": 1}
        body_b = {**MINIMAL_BODY, "seed": 2}
        r1 = client.post("/simulate", json=body_a).json()
        r2 = client.post("/simulate", json=body_b).json()
        # Different seeds almost always produce different hands counts or EV.
        # At least one metric should differ.
        differs = (
            r1["ev_per_hour"] != r2["ev_per_hour"]
            or r1["total_hands"] != r2["total_hands"]
        )
        assert differs


# ===========================================================================
# POST /simulate — bet_spread string-key handling
# ===========================================================================

class TestSimulateBetSpreadKeys:

    def test_string_integer_keys_accepted(self):
        body = {**MINIMAL_BODY, "bet_spread": {"1": 25.0, "3": 100.0}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 200

    def test_negative_string_keys_accepted(self):
        # Playing through all counts (even negative) with a minimum bet.
        body = {**MINIMAL_BODY, "bet_spread": {"-5": 10.0, "0": 10.0, "3": 100.0}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 200

    def test_non_integer_string_key_rejected(self):
        body = {**MINIMAL_BODY, "bet_spread": {"one": 25.0}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 422

    def test_negative_bet_rejected(self):
        body = {**MINIMAL_BODY, "bet_spread": {"1": -25.0}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 422

    def test_all_zero_bets_rejected(self):
        body = {**MINIMAL_BODY, "bet_spread": {"0": 0.0, "1": 0.0}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 422

    def test_empty_spread_rejected(self):
        body = {**MINIMAL_BODY, "bet_spread": {}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 422


# ===========================================================================
# POST /simulate — rules validation
# ===========================================================================

class TestSimulateRulesValidation:

    def test_invalid_deck_count_rejected(self):
        rules = {**MINIMAL_RULES, "decks": 5}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_penetration_zero_rejected(self):
        rules = {**MINIMAL_RULES, "penetration": 0.0}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_penetration_one_rejected(self):
        rules = {**MINIMAL_RULES, "penetration": 1.0}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_bj_payout_one_rejected(self):
        rules = {**MINIMAL_RULES, "bj_payout": 1.0}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_bj_payout_too_high_rejected(self):
        rules = {**MINIMAL_RULES, "bj_payout": 3.0}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_max_splits_out_of_range_rejected(self):
        rules = {**MINIMAL_RULES, "max_splits": 5}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 422

    def test_valid_single_deck(self):
        rules = {**MINIMAL_RULES, "decks": 1}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 200

    def test_valid_8_deck(self):
        rules = {**MINIMAL_RULES, "decks": 8}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 200

    def test_h17_false_accepted(self):
        rules = {**MINIMAL_RULES, "h17": False}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 200

    def test_6_5_payout_accepted(self):
        rules = {**MINIMAL_RULES, "bj_payout": 1.2}
        r = client.post("/simulate", json={**MINIMAL_BODY, "rules": rules})
        assert r.status_code == 200


# ===========================================================================
# POST /simulate — other field validation
# ===========================================================================

class TestSimulateFieldValidation:

    def test_zero_bankroll_rejected(self):
        r = client.post("/simulate", json={**MINIMAL_BODY, "bankroll": 0})
        assert r.status_code == 422

    def test_negative_bankroll_rejected(self):
        r = client.post("/simulate", json={**MINIMAL_BODY, "bankroll": -1})
        assert r.status_code == 422

    def test_zero_rounds_per_hour_rejected(self):
        r = client.post("/simulate", json={**MINIMAL_BODY, "rounds_per_hour": 0})
        assert r.status_code == 422

    def test_too_few_shoes_rejected(self):
        r = client.post("/simulate", json={**MINIMAL_BODY, "num_shoes": 50})
        assert r.status_code == 422

    def test_too_many_shoes_rejected(self):
        r = client.post("/simulate", json={**MINIMAL_BODY, "num_shoes": 600_000})
        assert r.status_code == 422

    def test_null_seed_accepted(self):
        body = {**MINIMAL_BODY, "seed": None}
        r = client.post("/simulate", json=body)
        assert r.status_code == 200


# ===========================================================================
# POST /simulate — default rules / missing fields
# ===========================================================================

class TestSimulateDefaults:

    def test_missing_rules_uses_defaults(self):
        body = {
            "bet_spread": {"1": 25.0},
            "bankroll": 10_000,
            "rounds_per_hour": 100,
            "num_shoes": 200,
            "seed": 0,
        }
        r = client.post("/simulate", json=body)
        assert r.status_code == 200

    def test_missing_bankroll_uses_default(self):
        body = {
            "bet_spread": {"1": 25.0},
            "num_shoes": 200,
            "seed": 0,
        }
        r = client.post("/simulate", json=body)
        assert r.status_code == 200

    def test_partial_rules_uses_defaults_for_missing(self):
        body = {**MINIMAL_BODY, "rules": {"decks": 2}}
        r = client.post("/simulate", json=body)
        assert r.status_code == 200


# ===========================================================================
# POST /simulate — economic sanity
# ===========================================================================

class TestSimulateEconomicSanity:

    @pytest.fixture(scope="class")
    def counting_metrics(self):
        body = {**MINIMAL_BODY, "num_shoes": 1_000, "seed": 42}
        return client.post("/simulate", json=body).json()

    @pytest.fixture(scope="class")
    def flat_metrics(self):
        body = {**MINIMAL_BODY, "bet_spread": FLAT_SPREAD,
                "num_shoes": 1_000, "seed": 42}
        return client.post("/simulate", json=body).json()

    def test_counting_spread_higher_ev_than_flat(
            self, counting_metrics, flat_metrics):
        # Wonging with a spread should outperform flat-betting all counts.
        assert (counting_metrics["ev_per_hour"]
                > flat_metrics["ev_per_hour"])

    def test_risk_of_ruin_in_zero_one(self, counting_metrics):
        ror = counting_metrics["risk_of_ruin"]
        assert 0.0 <= ror <= 1.0

    def test_edge_by_tc_higher_at_positive_counts(self, counting_metrics):
        etc = counting_metrics["edge_by_tc"]
        # At least one positive TC should show a positive edge.
        positive_tc_edges = [
            v for k, v in etc.items()
            if int(k) >= 3
        ]
        if positive_tc_edges:
            assert any(e > 0 for e in positive_tc_edges)

    def test_hours_to_n0_non_negative(self, counting_metrics):
        n0 = counting_metrics["hours_to_n0"]
        # -1 is the sentinel for ∞; any other value must be ≥ 0.
        assert n0 == -1.0 or n0 >= 0


# ===========================================================================
# POST /variance-visual — happy-path
# ===========================================================================

VARIANCE_BODY: dict = {
    **MINIMAL_BODY,
    "hours": 50.0,
    "num_paths": 100,
    "percentiles": [5.0, 50.0, 95.0],
}


class TestVarianceVisualHappyPath:

    @pytest.fixture(scope="class")
    def response(self):
        return client.post("/variance-visual", json=VARIANCE_BODY)

    @pytest.fixture(scope="class")
    def body(self, response):
        return response.json()

    def test_status_200(self, response):
        assert response.status_code == 200

    def test_hours_list_present(self, body):
        assert "hours" in body
        assert isinstance(body["hours"], list)
        assert len(body["hours"]) > 1

    def test_hours_starts_at_zero(self, body):
        assert body["hours"][0] == pytest.approx(0.0)

    def test_hours_ends_at_requested_hours(self, body):
        assert body["hours"][-1] == pytest.approx(VARIANCE_BODY["hours"])

    def test_percentile_curves_keys_present(self, body):
        curves = body["percentile_curves"]
        for p in VARIANCE_BODY["percentiles"]:
            key = str(int(p) if p == int(p) else p)
            assert key in curves, f"Missing percentile curve for {p}"

    def test_percentile_curves_same_length_as_hours(self, body):
        n = len(body["hours"])
        for key, curve in body["percentile_curves"].items():
            assert len(curve) == n, f"Curve {key} length mismatch"

    def test_ev_curve_present(self, body):
        assert "ev_curve" in body
        assert len(body["ev_curve"]) == len(body["hours"])

    def test_ev_curve_starts_at_bankroll(self, body):
        assert body["ev_curve"][0] == pytest.approx(VARIANCE_BODY["bankroll"])

    def test_ruin_probability_in_range(self, body):
        assert 0.0 <= body["ruin_probability"] <= 1.0

    def test_percentile_ordering(self, body):
        # At any given tick, p5 ≤ p50 ≤ p95 (check the final tick).
        curves = body["percentile_curves"]
        p5  = curves["5"][-1]
        p50 = curves["50"][-1]
        p95 = curves["95"][-1]
        assert p5 <= p50 <= p95

    def test_50th_percentile_near_bankroll_for_short_horizon(self):
        # Over a very short horizon (5 hours), median should stay near start.
        body = {**VARIANCE_BODY, "hours": 5.0, "num_paths": 200, "seed": 99}
        resp = client.post("/variance-visual", json=body).json()
        p50_end = resp["percentile_curves"]["50"][-1]
        bankroll = VARIANCE_BODY["bankroll"]
        # Median should be within ±30% of starting bankroll after just 5 hours.
        assert abs(p50_end - bankroll) / bankroll < 0.30


# ===========================================================================
# POST /variance-visual — validation
# ===========================================================================

class TestVarianceVisualValidation:

    def test_zero_hours_rejected(self):
        body = {**VARIANCE_BODY, "hours": 0}
        r = client.post("/variance-visual", json=body)
        assert r.status_code == 422

    def test_too_few_paths_rejected(self):
        body = {**VARIANCE_BODY, "num_paths": 10}
        r = client.post("/variance-visual", json=body)
        assert r.status_code == 422

    def test_too_many_paths_rejected(self):
        body = {**VARIANCE_BODY, "num_paths": 10_000}
        r = client.post("/variance-visual", json=body)
        assert r.status_code == 422

    def test_invalid_percentile_rejected(self):
        body = {**VARIANCE_BODY, "percentiles": [50.0, 110.0]}
        r = client.post("/variance-visual", json=body)
        assert r.status_code == 422

    def test_percentiles_are_sorted_in_response(self):
        body = {**VARIANCE_BODY, "percentiles": [75.0, 25.0, 50.0]}
        resp = client.post("/variance-visual", json=body)
        assert resp.status_code == 200
        curves = resp.json()["percentile_curves"]
        # Validator sorts them; all three should be present.
        assert "25" in curves and "50" in curves and "75" in curves

    def test_default_percentiles_used_when_omitted(self):
        body = {k: v for k, v in VARIANCE_BODY.items() if k != "percentiles"}
        resp = client.post("/variance-visual", json=body)
        assert resp.status_code == 200
        curves = resp.json()["percentile_curves"]
        # Default is [5, 25, 50, 75, 95].
        assert "5" in curves and "95" in curves


# ===========================================================================
# CORS headers
# ===========================================================================

class TestCorsHeaders:

    def test_cors_header_on_simulate(self):
        r = client.options(
            "/simulate",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        # CORSMiddleware returns 200 for preflight.
        assert r.status_code == 200
        assert "access-control-allow-origin" in r.headers

    def test_cors_origin_in_health_response(self):
        r = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert "access-control-allow-origin" in r.headers


# ===========================================================================
# Unknown routes
# ===========================================================================

class TestUnknownRoutes:

    def test_unknown_get_returns_404(self):
        r = client.get("/does-not-exist")
        assert r.status_code == 404

    def test_unknown_post_returns_405_or_404(self):
        r = client.get("/simulate")   # GET on a POST-only endpoint
        assert r.status_code in (405, 404)
