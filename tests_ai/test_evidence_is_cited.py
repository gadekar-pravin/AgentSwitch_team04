"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-12).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Second official harness run, 2026-10-12, deepseek-v4p1-flash: three of eight tasks reached their 30k
token limit and filed a forced finding. why_late_wo48_subcontract passed only because the model, under
that forced call, still typed the draft subcontract numbers into evidence_records, which its verifier
requires. The record that proves each cause is already in the loop's diagnosis, so these pin that a
finding cites it whatever the model retyped.

Run: python -m pytest tests_ai/test_evidence_is_cited.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

WO48 = {"id": "5f0c1e8a-0000-4000-8000-000000000048", "number": "WO-2026-00048"}
DIAG = {"found": True, "work_order": WO48, "signals": [
    {"code": "subcontract_not_sent", "blocking": True, "record": "SCO-2026-00011"},
    {"code": "subcontract_not_sent", "blocking": True, "record": "SCO-2026-00012"},
    {"code": "material_shortage", "blocking": False, "record": "item-7"},
    {"code": "stock_check_unreliable", "blocking": False, "record": None}]}


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(domain, "diagnose", lambda mcp, ref: DIAG if ref.upper() == WO48["number"]
                        else {"found": False, "ref": ref})
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m")
    a._dispatch("diagnose_work_order", {"work_order": WO48["number"]})
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": WO48["number"], "is_late": True, "currency": "INR",
            "blocking_causes": ["subcontract_not_sent"], "contributing_causes": [], "evidence_records": [],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


def test_every_record_that_proves_a_named_cause_is_cited(agent):
    out = agent._cite_evidence(_finding())
    assert out["evidence_records"] == ["SCO-2026-00011", "SCO-2026-00012"]


def test_the_models_own_citations_stay_first_and_are_not_repeated(agent):
    out = agent._cite_evidence(_finding(evidence_records=["WO-2026-00048", "SCO-2026-00012"]))
    assert out["evidence_records"] == ["WO-2026-00048", "SCO-2026-00012", "SCO-2026-00011"]


def test_a_cause_the_finding_does_not_name_is_not_cited(agent):
    out = agent._cite_evidence(_finding(blocking_causes=[], contributing_causes=["material_shortage"]))
    assert out["evidence_records"] == ["item-7"]


def test_a_signal_with_no_record_adds_nothing(agent):
    finding = _finding(blocking_causes=[], contributing_causes=["stock_check_unreliable"])
    assert agent._cite_evidence(finding) == finding


@pytest.mark.parametrize("outcome", ["refused", None])
def test_a_refusal_or_an_unfinished_finding_is_left_alone(agent, outcome):
    finding = _finding(outcome=outcome)
    assert agent._cite_evidence(finding) == finding


def test_a_wrong_shape_is_left_for_the_shape_guard(agent):
    finding = _finding(evidence_records="SCO-2026-00011")
    assert agent._cite_evidence(finding) == finding


def test_an_order_never_diagnosed_is_left_alone(agent):
    finding = _finding(work_order="WO-2026-00049")
    assert agent._cite_evidence(finding) == finding


def test_the_whole_record_path_cites_the_subcontracts(agent):
    """Through record_finding itself, as the forced finding at the token limit would arrive."""
    saved = []
    agent.mcp.call = lambda name, args: saved.append(args) or {"id": "mem-1"}

    agent._dispatch("record_finding", _finding())

    assert agent.finding["evidence_records"][:2] == ["SCO-2026-00011", "SCO-2026-00012"]
    assert "SCO-2026-00012" in saved[0]["content"]
