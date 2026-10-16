"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Platform-model rehearsal, 2026-10-16 (deepseek/deepseek-v4.1-flash): capacity_load_disputed, a platform task,
scored revise with "outcome 'refused', but this seat can answer the question from readable data". The model
recorded work_order "null", the word. _restore_causes looked up an order called "null", the lookup found
none, and _refuse_missing_order filed a correct load answer as a refusal. The same could have happened on
the official run. These pin that a placeholder names no order, and that only a value shaped like an order
reference is ever looked up at record time.

Run: python -m pytest tests_ai/test_placeholder_work_order.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

CAPACITY = {"board_load_pct": 117.04, "work_content_load_pct": 117.0, "figures_disagree": False}


@pytest.fixture
def agent(monkeypatch):
    looked_up = []

    def diagnose(mcp, ref):
        looked_up.append(ref)
        return {"found": False, "ref": ref}

    monkeypatch.setattr(domain, "diagnose", diagnose)
    events, saved = [], []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m",
                        trace=events.append)
    a.mcp.call = lambda name, args: saved.append(args) or {"id": "mem-1"}
    a.looked_up, a.events, a.saved = looked_up, events, saved
    return a


def _finding(work_order):
    return {"outcome": "answered", "work_order": work_order, "is_late": None, "currency": "INR",
            "blocking_causes": [], "contributing_causes": [], "evidence_records": [],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, "capacity": CAPACITY}


@pytest.mark.parametrize("placeholder", ["null", "NULL", " None ", "n/a", "", "-"])
def test_the_live_failure_stays_an_answer(agent, placeholder):
    agent._dispatch("record_finding", _finding(placeholder))

    assert agent.finding["outcome"] == "answered"
    assert agent.finding["work_order"] is None
    assert agent.looked_up == [], "no order was asked about, so none is looked up"


@pytest.mark.parametrize("text", ["the shop floor", "all workstations", "WO-2026-48"])
def test_text_that_is_not_an_order_reference_is_never_looked_up(agent, text):
    agent._dispatch("record_finding", _finding(text))

    assert agent.looked_up == []
    assert agent.finding["outcome"] == "answered"


@pytest.mark.parametrize("ref", ["WO-2026-09999", "wo-2026-09999", "8B28F895-B529-4819-A648-C55DAAA59659"])
def test_an_order_reference_is_still_looked_up_and_a_missing_one_refused(agent, ref):
    """The 2026-10-12 backstop stands: an answer about an order that does not exist is a refusal."""
    agent._dispatch("record_finding", {**_finding(ref), "capacity": None})

    assert agent.looked_up == [ref]
    assert agent.finding["outcome"] == "refused"
