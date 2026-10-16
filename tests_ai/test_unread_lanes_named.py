"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Full local harness run, 2026-10-16 (3c8e6e9, gpt-4.1): bottleneck_lanes_reported scored revise on Keystone
with "lanes the cockpit could not fill {'automation_failures': 'permission_denied', 'shortages':
'permission_denied'} are not named in not_visible, so they read as clear". shop_floor_exceptions had
returned those lane_states and the finding sent not_visible []. record_finding now names every lane the
tool said it could not fill, unless the model already did.

Run: python -m pytest tests_ai/test_unread_lanes_named.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

LANES = {"shortages": "permission_denied", "quality_blocks": "ready", "subcontract_blocks": "ready",
         "automation_failures": "permission_denied"}


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(domain, "shop_floor_exceptions", lambda mcp, *args, **kw: {
        "available": True, "lane_states": dict(LANES), "lanes": [
            {"kind": "quality_block", "count": 1, "examples": [{"record": "QI-2026-00002", "order_open": True}]}]})
    events = []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="keystone")), llm=object(), model="m",
                        trace=events.append)
    a.mcp.call = lambda name, args: {"id": "mem-1"}
    a.events = events
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": None, "is_late": None, "currency": "USD",
            "blocking_causes": [], "contributing_causes": [], "evidence_records": ["QI-2026-00002"],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


def test_the_live_failure_names_both_unreadable_lanes(agent):
    agent._dispatch("shop_floor_exceptions", {})
    agent._dispatch("record_finding", _finding())

    named = agent.finding["not_visible"]
    assert len(named) == 2
    assert any("shortages" in e for e in named) and any("automation_failures" in e for e in named)
    assert not any("quality_blocks" in e or "subcontract" in e for e in named), "a ready lane is not unknown"
    assert [e["type"] for e in agent.events].count("finding_corrected") == 1


def test_a_lane_the_model_already_named_is_not_named_twice(agent):
    agent._dispatch("shop_floor_exceptions", {})
    out = agent._restore_unread_lanes(_finding(not_visible=["Shortage lane: permission denied for this seat"]))

    assert out["not_visible"][0] == "Shortage lane: permission denied for this seat"
    assert len(out["not_visible"]) == 2 and "automation_failures" in out["not_visible"][1]


def test_both_already_named_leaves_the_finding_as_it_was(agent):
    agent._dispatch("shop_floor_exceptions", {})
    finding = _finding(not_visible=["shortages: permission_denied", "automation failures: permission_denied"])
    assert agent._restore_unread_lanes(finding) is finding


def test_a_run_that_never_read_the_cockpit_is_left_alone(agent):
    finding = _finding()
    assert agent._restore_unread_lanes(finding) is finding


def test_a_wrong_shape_is_left_for_the_shape_guard(agent):
    agent._dispatch("shop_floor_exceptions", {})
    finding = _finding(not_visible="shortages")
    assert agent._restore_unread_lanes(finding) is finding


def test_an_absent_not_visible_still_gets_the_lanes(agent):
    agent._dispatch("shop_floor_exceptions", {})
    finding = _finding()
    del finding["not_visible"]
    assert len(agent._restore_unread_lanes(finding)["not_visible"]) == 2
