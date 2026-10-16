"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Full local harness run, 2026-10-16 (79d9c6b, gpt-4.1): keystone_customer_impact_wo4, a platform task,
scored revise with "DB links SO-2026-00003 to WO-2026-00004; finding reported
['ceef0019-805e-4c1e-b934-d68d63f8b7cc']". downstream_impact had returned the sales order with both its
id and its number, and the model copied the id. The schema asks for record numbers and every verifier
matches numbers, so record_finding now files any id a tool result paired with a number as that number.

Run: python -m pytest tests_ai/test_record_numbers_not_ids.py -q
"""
import json
from types import SimpleNamespace

import pytest

from prod_agent import config, domain
from prod_agent.agent import ProductionAgent

WO4 = {"id": "a1c2e3f4-0000-4000-8000-000000000004", "number": "WO-2026-00004"}
SO3 = {"id": "ceef0019-805e-4c1e-b934-d68d63f8b7cc", "number": "SO-2026-00003", "customer": "Tri-State Farm Equipment",
       "via_work_order": "WO-2026-00004", "link": "sales_order_id", "confidence": "linked"}
WO9 = {"id": "b2d3e4f5-0000-4000-8000-000000000009", "number": "WO-2026-00009", "confidence": "potential"}
DOWNSTREAM = {"found": True, "work_order": WO4, "blocked_sales_orders": [SO3],
              "potentially_blocked_work_orders": [WO9], "customer_impact": "known"}


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(domain, "diagnose", lambda mcp, ref: {"found": True, "work_order": WO4, "signals": []})
    monkeypatch.setattr(domain, "downstream_impact", lambda mcp, ref: DOWNSTREAM)
    events, saved = [], []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="keystone")), llm=object(), model="m",
                        trace=events.append)
    a.mcp.call = lambda name, args: saved.append(args) or {"id": "mem-1"}
    a.events, a.saved = events, saved
    a._dispatch("downstream_impact", {"work_order": WO4["number"]})
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": WO4["number"], "is_late": True, "currency": "USD",
            "blocking_causes": [], "contributing_causes": [], "evidence_records": [WO4["number"]],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [SO3["number"]], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


def test_the_live_failure_files_the_sales_order_by_its_number(agent):
    agent._dispatch("record_finding", _finding(blocked_sales_orders=[SO3["id"]],
                                               evidence_records=[WO4["number"], SO3["id"]]))

    stored = json.loads(agent.saved[0]["content"].removeprefix(config.FINDING_PREFIX))
    assert stored["blocked_sales_orders"] == ["SO-2026-00003"]
    assert stored["evidence_records"] == ["WO-2026-00004", "SO-2026-00003"]
    corrected = [e for e in agent.events if e["type"] == "finding_corrected"]
    assert corrected and corrected[0]["replaced"] == {SO3["id"]: "SO-2026-00003"}


def test_an_id_beside_its_own_number_is_listed_once(agent):
    out = agent._numbers_not_ids(_finding(evidence_records=["SO-2026-00003", SO3["id"], WO4["number"]]))
    assert out["evidence_records"] == ["SO-2026-00003", "WO-2026-00004"]


def test_a_work_order_and_its_dependants_filed_by_id_are_filed_by_number(agent):
    out = agent._numbers_not_ids(_finding(work_order=WO4["id"], potentially_blocked_work_orders=[WO9["id"]]))
    assert out["work_order"] == "WO-2026-00004"
    assert out["potentially_blocked_work_orders"] == ["WO-2026-00009"]


def test_an_id_no_tool_returned_is_left_alone(agent):
    unknown = "deadbeef-0000-4000-8000-000000000000"
    out = agent._numbers_not_ids(_finding(evidence_records=[unknown]))
    assert out["evidence_records"] == [unknown]


def test_a_finding_already_in_numbers_is_untouched_and_not_traced(agent):
    finding = _finding()
    assert agent._numbers_not_ids(finding) is finding
    assert [e for e in agent.events if e["type"] == "finding_corrected"] == []


def test_a_wrong_shape_is_left_for_the_shape_guard(agent):
    finding = _finding(blocked_sales_orders=SO3["id"])
    assert agent._numbers_not_ids(finding)["blocked_sales_orders"] == SO3["id"]


def test_numbers_are_learned_wherever_a_result_nests_them():
    agent = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="keystone")), llm=object(), model="m")
    agent._learn_numbers({"rows": [{"order": {"id": "x-1", "number": "SO-1"}}, {"id": "x-2", "number": "SO-2"}],
                          "id": "not-a-record", "count": 2})
    assert agent._numbers == {"x-1": "SO-1", "x-2": "SO-2"}


def test_a_record_whose_id_is_its_number_teaches_nothing():
    agent = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="keystone")), llm=object(), model="m")
    agent._learn_numbers([{"id": "SO-1", "number": "SO-1"}, {"id": "", "number": "SO-2"}, "plain text", None])
    assert agent._numbers == {}
