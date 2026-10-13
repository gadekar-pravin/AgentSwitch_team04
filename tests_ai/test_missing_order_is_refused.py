"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-12).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

refuse_unknown_work_order, 2026-10-12, gpt-4.1 locally: diagnose returned {"found": false} for
WO-2026-09999, the model searched on with query_records for five steps, ran into its 30k token limit,
and the forced finding said outcome 'answered'. DeepSeek took the same detour on the platform that
day (4-5 steps, 35-39k tokens) and only just recorded a refusal in time. These pin the plain-words
not-found result and the backstop that files such a finding as the refusal it is.

Run: python -m pytest tests_ai/test_missing_order_is_refused.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import agent as agent_module
from prod_agent import domain
from prod_agent.agent import ProductionAgent, _tool_content

MISSING = "WO-2026-09999"


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(domain, "diagnose", lambda mcp, ref: {"found": False, "ref": ref} if ref.upper() == MISSING
                        else {"found": True, "work_order": {"id": "u-1", "number": ref.upper()}, "signals": []})
    monkeypatch.setattr(domain, "downstream_impact", lambda mcp, ref: {"found": False, "ref": ref})
    events = []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m",
                        trace=events.append)
    a.events = events
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": MISSING, "is_late": False, "currency": "INR",
            "blocking_causes": ["not_released"], "contributing_causes": [], "evidence_records": [],
            "potentially_blocked_work_orders": ["WO-2026-00001"], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


@pytest.mark.parametrize("tool", ["diagnose_work_order", "downstream_impact", "propose_reschedule"])
def test_a_lookup_that_finds_nothing_tells_the_model_to_stop_and_refuse(agent, tool):
    result = agent._dispatch(tool, {"work_order": MISSING})

    assert result["found"] is False
    assert "Do not search for it another way" in result["instruction_for_agent"]
    assert "outcome 'refused'" in result["instruction_for_agent"]


def test_the_instruction_reaches_the_model_unfenced(agent):
    sent = _tool_content(agent._dispatch("diagnose_work_order", {"work_order": MISSING}))
    assert "Do not search for it another way" in sent and agent_module.DATA_OPEN not in sent


def test_an_answered_finding_about_a_missing_order_is_filed_as_a_refusal(agent):
    agent._dispatch("diagnose_work_order", {"work_order": MISSING})

    out = agent._refuse_missing_order(_finding())

    assert out["outcome"] == "refused" and out["is_late"] is None
    assert out["blocking_causes"] == [] and out["potentially_blocked_work_orders"] == []
    assert out["refusal_reason"] == f"{MISSING} does not exist on this instance"
    assert [e["type"] for e in agent.events] == ["finding_corrected"]


def test_the_models_own_refusal_reason_is_kept(agent):
    agent._dispatch("diagnose_work_order", {"work_order": MISSING})
    out = agent._refuse_missing_order(_finding(refusal_reason="WO-2026-09999 is not a work order here"))
    assert out["refusal_reason"] == "WO-2026-09999 is not a work order here"


def test_the_reference_matches_in_any_case(agent):
    agent._dispatch("diagnose_work_order", {"work_order": "wo-2026-09999"})
    assert agent._refuse_missing_order(_finding())["outcome"] == "refused"


def test_a_finding_about_an_order_that_exists_is_left_alone(agent):
    agent._dispatch("diagnose_work_order", {"work_order": MISSING})
    agent._dispatch("diagnose_work_order", {"work_order": "WO-2026-00003"})
    finding = _finding(work_order="WO-2026-00003")

    assert agent._refuse_missing_order(finding) == finding


def test_a_refusal_already_recorded_is_left_alone(agent):
    agent._dispatch("diagnose_work_order", {"work_order": MISSING})
    finding = _finding(outcome="refused", refusal_reason="does not exist")

    assert agent._refuse_missing_order(finding) == finding
    assert agent.events == []


def test_an_order_never_looked_up_is_not_assumed_missing(agent):
    finding = _finding()
    assert agent._refuse_missing_order(finding) == finding


def test_the_whole_record_path_files_the_refusal(agent):
    """Through record_finding itself, as the forced finding at the token limit would arrive."""
    saved = []
    agent.mcp.call = lambda name, args: saved.append(args) or {"id": "mem-1"}
    agent._dispatch("diagnose_work_order", {"work_order": MISSING})

    agent._dispatch("record_finding", _finding())

    assert agent.finding["outcome"] == "refused"
    assert '"outcome": "refused"' in saved[0]["content"]
