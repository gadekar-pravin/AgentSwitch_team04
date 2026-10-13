"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-12).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Second official harness run, 2026-10-12, deepseek-v4p1-flash: keystone_why_late_wo3 scored revise
with "causes [] omit not_started_past_planned_start". Asked to "find out why and reschedule", the
model can go straight to propose_reschedule, which diagnosed the order internally but returned only
dates, and kept that diagnosis where the cause restore never looked. So the model never saw a cause,
and the restore had nothing to restore from. These pin the three ways a cause now reaches the finding.

Run: python -m pytest tests_ai/test_causes_reach_the_finding.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

WO3 = {"id": "8b28f895-b529-4819-a648-c55daaa59659", "number": "WO-2026-00003"}
DIAG = {"found": True, "work_order": WO3, "signals": [
    {"code": "not_started_past_planned_start", "blocking": False, "record": "WO-2026-00003"}]}


@pytest.fixture
def agent(monkeypatch):
    calls = []

    def diagnose(mcp, ref):
        calls.append(ref)
        return DIAG if ref.upper() in (WO3["number"], WO3["id"].upper()) else {"found": False, "ref": ref}

    monkeypatch.setattr(domain, "diagnose", diagnose)
    monkeypatch.setattr(domain, "propose_reschedule", lambda mcp, ref, diag=None, down=None:
                        {"found": True, "work_order": WO3, "today": "2026-10-12", "proposals": [],
                         "downstream_considered": []})
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="keystone")), llm=object(), model="m")
    a.diagnose_calls = calls
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": "WO-2026-00003", "is_late": True,
            "blocking_causes": [], "contributing_causes": [], **over}


def test_propose_reschedule_now_shows_the_causes_it_planned_around(agent):
    result = agent._dispatch("propose_reschedule", {"work_order": "WO-2026-00003"})

    assert result["causes_found"] == [{"code": "not_started_past_planned_start", "blocking": False}]


def test_a_cause_found_only_through_propose_reschedule_is_restored(agent):
    agent._dispatch("propose_reschedule", {"work_order": "WO-2026-00003"})

    out = agent._restore_causes(_finding())

    assert out["contributing_causes"] == ["not_started_past_planned_start"]
    assert agent.diagnose_calls == ["WO-2026-00003"], "diagnosed once, and reused"


def test_a_finding_filed_by_id_or_in_other_case_still_finds_the_diagnosis(agent):
    agent._dispatch("diagnose_work_order", {"work_order": "WO-2026-00003"})

    by_id = agent._restore_causes(_finding(work_order=WO3["id"]))
    lower = agent._restore_causes(_finding(work_order="wo-2026-00003"))

    assert by_id["contributing_causes"] == lower["contributing_causes"] == ["not_started_past_planned_start"]
    assert agent.diagnose_calls == ["WO-2026-00003"]


def test_an_answer_about_an_order_never_diagnosed_gets_its_causes_from_the_database(agent):
    out = agent._restore_causes(_finding())

    assert out["contributing_causes"] == ["not_started_past_planned_start"]
    assert agent.diagnose_calls == ["WO-2026-00003"]


@pytest.mark.parametrize("outcome", ["refused", None])
def test_a_refusal_or_an_unfinished_finding_is_not_diagnosed(agent, outcome):
    finding = _finding(outcome=outcome)

    assert agent._restore_causes(finding) == finding
    assert agent.diagnose_calls == []


def test_a_failing_read_at_record_time_leaves_the_finding_as_it_was(agent, monkeypatch):
    def broken(mcp, ref):
        raise RuntimeError("502 from the instance")

    monkeypatch.setattr(domain, "diagnose", broken)
    finding = _finding()

    assert agent._restore_causes(finding) == finding
