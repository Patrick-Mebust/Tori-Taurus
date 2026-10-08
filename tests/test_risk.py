"""Known dollar-loss and whole-share limits, including existing holdings."""

from decimal import Decimal

import pytest

from tori_taurus.risk import RiskInputs, evaluate_risk


def plan(**changes):
    return RiskInputs(
        **(
            {
                "symbol": "TEST",
                "equity": 1000,
                "buying_power": 100,
                "entry": 2,
                "requested_shares": 20,
                "stop": Decimal("1.5"),
            }
            | changes
        )
    )


def test_known_new_position_boundaries():
    report = evaluate_risk(plan())
    assert report["status"] == "within_supplied_limits"
    assert report["conservative_budget_loss"] == "10.0"
    assert report["account_risk_percent"] == "1.00"
    assert report["allowable_add_shares"] == 20
    assert report["buying_power_after_add"] == "60"
    assert not report["stop_verified_with_broker"]
    assert "risk_budget_exceeded" in evaluate_risk(plan(requested_shares=21))["blockers"]


def test_existing_risk_uses_headroom_and_combined_average():
    report = evaluate_risk(plan(existing_shares=10, existing_average=2, requested_shares=10))
    assert report["existing_planned_loss"] == "5.0"
    assert report["incremental_planned_loss"] == "5.0"
    assert report["combined_average"] == "2"
    assert report["allowable_add_shares"] == 10


def test_existing_gains_do_not_offset_new_budget_loss():
    report = evaluate_risk(plan(existing_shares=10, existing_average=1))
    assert report["combined_net_planned_loss"] == "5.0"
    assert report["conservative_budget_loss"] == "10.0"


def test_affordability_and_concentration_limit_share_counts():
    report = evaluate_risk(plan(buying_power=9, max_concentration_percent=1))
    assert report["share_limits"]["buying_power"] == 4
    assert report["share_limits"]["concentration"] == 5
    assert report["allowable_add_shares"] == 4
    assert report["blockers"] == ["insufficient_buying_power", "concentration_limit_exceeded"]


def test_undefined_stop_never_sizes_or_invents_loss():
    report = evaluate_risk(plan(stop=None))
    assert report["status"] == "blocked" and report["allowable_add_shares"] == 0
    assert report["account_risk_percent"] is None
    assert report["capital_at_risk_without_stop"] == "40"
    assert report["combined_net_planned_loss"] is None


def test_user_reported_stop_is_not_verified():
    report = evaluate_risk(plan(stop_reported_active=True))
    assert report["stop_status"] == "user_reported_active"
    assert not report["stop_verified_with_broker"]


def test_existing_over_budget_and_fractional_capacity():
    report = evaluate_risk(plan(existing_shares=30, existing_average=2, requested_shares=0))
    assert report["allowable_add_shares"] == 0 and "risk_budget_exceeded" in report["blockers"]
    report = evaluate_risk(plan(entry="0.3", stop="0.1", buying_power="1", requested_shares=3))
    assert report["share_limits"]["buying_power"] == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"equity": 0},
        {"entry": 0},
        {"stop": 2},
        {"requested_shares": True},
        {"requested_shares": -1},
        {"buying_power": -1},
        {"existing_shares": 1},
        {"risk_budget_percent": 0},
        {"max_concentration_percent": 101},
        {"stop": None, "stop_reported_active": True},
    ],
)
def test_invalid_inputs(changes):
    with pytest.raises(ValueError):
        plan(**changes)
