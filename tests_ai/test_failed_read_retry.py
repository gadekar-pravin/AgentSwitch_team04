"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-18).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Full local run 2026-10-18 (gpt-4.1, d2b140b): suryodaya bottleneck_lanes_reported scored revise with outcome
'refused'. The platform closed the connection on shop_floor_exceptions after 146 s; the model asked again, and the
repeat guard answered "that result above is still current" about a result that was only an error, so the run refused
a question it could answer. A guarded read that failed now gets one retry; a second failure stands.

Run: python -m pytest tests_ai/test_failed_read_retry.py -q
"""
from prod_agent.agent import ProductionAgent
from tests_ai.test_llm_error import FakeMessage, FakeToolCall, finding_args, isolated_environment, recording_mcp  # noqa: F401
from tests_ai.test_token_budget import MeteredLLM, _reply


def _call(name, args=None):
    return _reply(FakeMessage(tool_calls=[FakeToolCall(name, args or {})]), 1000)


def _agent(mcp, llm, failures, events):
    agent = ProductionAgent(mcp, llm=llm, model="m", trace=events.append)
    real = agent._dispatch
    left = {"n": failures}

    def dispatch(name, args):
        if name == "company_context":
            if left["n"]:
                left["n"] -= 1
                raise ConnectionResetError("Remote end closed connection without response")
            return {"company": "Suryodaya", "currency": "INR"}
        return real(name, args)

    agent._dispatch = dispatch
    return agent


def _context_results(events):
    return [e["result"] for e in events if e["type"] == "tool" and e["name"] == "company_context"]


def test_a_read_the_platform_dropped_is_run_again(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_call("company_context"), _call("company_context"), _call("record_finding", finding_args()),
                      _reply(FakeMessage(content="done"), 1000)])
    events = []

    _agent(mcp, llm, 1, events).run("where is the shop floor stuck?")

    first, second = _context_results(events)
    assert "error" in first and "retry" in first, "the failure says a retry is allowed"
    assert second == {"company": "Suryodaya", "currency": "INR"}, "the retry ran, rather than being called a repeat"


def test_only_one_retry_after_a_failure(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_call("company_context"), _call("company_context"), _call("company_context"),
                      _call("record_finding", finding_args()), _reply(FakeMessage(content="done"), 1000)])
    events = []

    _agent(mcp, llm, 2, events).run("where is the shop floor stuck?")

    first, second, third = _context_results(events)
    assert "retry" in first and "error" in second and "retry" not in second
    assert third.get("repeat") is True, "a second failure stands: the guard stops a third identical call"


def test_a_read_that_answered_is_still_guarded(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_call("company_context"), _call("company_context"), _call("record_finding", finding_args()),
                      _reply(FakeMessage(content="done"), 1000)])
    events = []

    _agent(mcp, llm, 0, events).run("where is the shop floor stuck?")

    assert _context_results(events)[1].get("repeat") is True
