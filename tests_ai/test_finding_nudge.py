"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-12).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Local rehearsal on the platform's model, 2026-10-12 (deepseek/deepseek-v4.1-flash through OpenRouter,
platform mode): keystone_why_late_wo3 scored revise with "no finding recorded in AgentMemory". At step 3
wrap-up forced record_finding by name; the model answered in prose instead ("I can't write the
reschedule, so this needs a person. Let me escalate.") and called nothing, and a reply without a tool
call ended the run. These pin that a prose reply to a forced record_finding is answered once with a
reminder and a second forced call, rather than ending the run with nothing to grade, while a prose
answer the loop never forced still ends the run, as the graded suite's test 30 requires.

Run: python -m pytest tests_ai/test_finding_nudge.py -q
"""
from prod_agent.agent import FINDING_NUDGE, ProductionAgent
from tests_ai.test_llm_error import FakeMessage, FakeToolCall, finding_args, isolated_environment, recording_mcp  # noqa: F401
from tests_ai.test_token_budget import FORCE_FINDING, MeteredLLM, _reply


def _prose(text="Let me escalate.", total=1000):
    return _reply(FakeMessage(content=text), total)


def _record(total=1000):
    return _reply(FakeMessage(tool_calls=[FakeToolCall("record_finding", finding_args())]), total)


def _tool(total=1000):
    return _reply(FakeMessage(tool_calls=[FakeToolCall("no_such_tool", {})]), total)


def test_the_live_failure_now_records_its_finding(recording_mcp):
    """Forced by name near the token limit, answered in prose: reminded, forced again, recorded."""
    mcp, _ = recording_mcp
    llm = MeteredLLM([_tool(10_000), _prose(total=1000), _record(), _prose("done")])
    events = []

    out = ProductionAgent(mcp, llm=llm, model="m", token_budget=30_000, trace=events.append).run("why late?")

    assert llm.requests[1]["tool_choice"] == FORCE_FINDING, "wrap-up forced it, and the model ignored that"
    assert llm.requests[2]["tool_choice"] == FORCE_FINDING
    sent = llm.requests[2]["messages"]  # the loop's own list, so it also holds what came after this request
    at = sent.index({"role": "user", "content": FINDING_NUDGE})
    assert sent[at - 1]["content"] == "Let me escalate.", "the reminder answers the prose reply"
    assert out["finding"] is not None and out["stop_reason"] == "final_answer"
    assert [e["type"] for e in events].count("finding_nudge") == 1


def test_a_prose_answer_nothing_forced_still_ends_the_run(recording_mcp):
    """The graded suite's test 30: a final answer the loop never asked to be a tool call ends the run."""
    mcp, _ = recording_mcp
    llm = MeteredLLM([_prose("hi")])
    events = []

    out = ProductionAgent(mcp, llm=llm, model="m", max_steps=3, trace=events.append).run("why late?")

    assert out["stop_reason"] == "final_answer" and len(llm.requests) == 1
    assert [e["type"] for e in events] == ["start", "llm", "end"]


def test_the_reminder_is_given_once(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_tool(10_000), _prose(), _prose("still no")])

    out = ProductionAgent(mcp, llm=llm, model="m", token_budget=30_000).run("why late?")

    assert out["stop_reason"] == "final_answer" and out["finding"] is None
    assert len(llm.requests) == 3


def test_a_prose_reply_after_the_finding_ends_the_run(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_record(), _prose("done")])
    events = []

    out = ProductionAgent(mcp, llm=llm, model="m", trace=events.append).run("why late?")

    assert out["stop_reason"] == "final_answer" and len(llm.requests) == 2
    assert "finding_nudge" not in [e["type"] for e in events]
