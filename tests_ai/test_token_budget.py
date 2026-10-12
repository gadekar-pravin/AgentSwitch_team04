"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-12).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

The first official harness run (2026-10-12) met an LLM token budget the announcement does not
mention: one per submission, shared by both instances. Suryodaya's first three tasks spent 304,284
tokens on deepseek-v4p1-flash, a reasoning model, and every later call, Keystone's included, was
refused with 429 budget_exhausted. These pin what stops that happening again: tokens counted per task,
a task's own limit that forces its finding first, thinking text never sent back, reasoning switched
off where the endpoint allows, and a runner that starts a task only when its whole limit still fits.

Run: python -m pytest tests_ai/test_token_budget.py -q
"""
from types import SimpleNamespace

import httpx
import openai
import pytest

from harness import runner
from harness.results import ResultsBook, diagnostics
from prod_agent.agent import ProductionAgent, probe_reasoning_off
from tests_ai.test_llm_error import FakeMessage, FakeToolCall, isolated_environment, recording_mcp  # noqa: F401

FORCE_FINDING = {"type": "function", "function": {"name": "record_finding"}}


class ThinkingMessage(FakeMessage):
    """A reasoning model's reply: the answer plus its thinking, which model_dump carries along."""

    def model_dump(self, **kwargs):
        return {**super().model_dump(**kwargs), "reasoning_content": "a long chain of thought " * 200}


def _reply(message, total, prompt=None):
    prompt = total // 2 if prompt is None else prompt
    usage = SimpleNamespace(prompt_tokens=prompt, completion_tokens=total - prompt, total_tokens=total,
                            model_dump=lambda: {"total_tokens": total})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class MeteredLLM:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = next(self.replies)
        if isinstance(reply, BaseException):
            raise reply
        return reply


def _tool_step(total):
    return _reply(FakeMessage(tool_calls=[FakeToolCall("no_such_tool", {})]), total)


def _done(total=1000):
    return _reply(FakeMessage(content="done"), total)


# ----------------------------------------------------------------------------- the agent

def test_tokens_and_steps_are_counted_from_the_models_usage(recording_mcp):
    mcp, _ = recording_mcp
    out = ProductionAgent(mcp, llm=MeteredLLM([_tool_step(4000), _done(1500)]), model="m").run("why late?")

    assert out["steps"] == 2
    assert out["tokens"] == {"prompt": 2750, "completion": 2750, "total": 5500}
    assert diagnostics({**out, "llm_error_code": None}) == "[2 steps, 5.5k tokens]"


def test_thinking_text_is_never_sent_back(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_reply(ThinkingMessage(tool_calls=[FakeToolCall("no_such_tool", {})]), 3000), _done()])

    ProductionAgent(mcp, llm=llm, model="m").run("why late?")

    replayed = [m for m in llm.requests[1]["messages"] if m.get("role") == "assistant"]
    assert replayed and all("reasoning_content" not in m for m in replayed)


def test_the_probes_fields_go_on_every_call_and_nothing_otherwise(recording_mcp):
    mcp, _ = recording_mcp
    off, default = MeteredLLM([_tool_step(1000), _done()]), MeteredLLM([_done()])
    extra = {"extra_body": {"thinking": {"type": "disabled"}}}

    ProductionAgent(mcp, llm=off, model="m", request_extra=extra).run("why late?")
    ProductionAgent(mcp, llm=default, model="m").run("why late?")

    assert all(r["extra_body"] == extra["extra_body"] for r in off.requests) and len(off.requests) == 2
    assert not {"extra_body", "reasoning_effort"} & set(default.requests[0])


def test_near_its_token_limit_the_finding_is_forced(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_tool_step(10_000), _done()])

    ProductionAgent(mcp, llm=llm, model="m", token_budget=30_000).run("why late?")

    assert "tool_choice" not in llm.requests[0]
    assert llm.requests[1]["tool_choice"] == FORCE_FINDING, "10k spent plus two more 10k steps reaches 30k"


def test_at_its_token_limit_the_run_stops_without_another_call(recording_mcp):
    mcp, _ = recording_mcp
    llm = MeteredLLM([_tool_step(6000)])
    events = []

    out = ProductionAgent(mcp, llm=llm, model="m", token_budget=5000, trace=events.append).run("why late?")

    assert out["stop_reason"] == "token_budget"
    assert len(llm.requests) == 1
    assert "token_budget" in [e["type"] for e in events]


def test_a_spent_run_budget_is_reported_by_its_code_and_not_waited_on(recording_mcp):
    mcp, _ = recording_mcp
    spent = openai.RateLimitError(
        "This run's LLM token budget is used up", response=httpx.Response(429, request=httpx.Request("POST", "https://x")),
        body={"message": "used up", "type": "insufficient_quota", "code": "budget_exhausted"})
    llm = MeteredLLM([spent])

    out = ProductionAgent(mcp, llm=llm, model="m").run("why late?")

    assert out["stop_reason"] == "llm_error" and out["llm_error_code"] == "budget_exhausted"
    assert len(llm.requests) == 1


# ----------------------------------------------------------------------------- the reasoning probe

def _400(message):
    return openai.BadRequestError(message, response=httpx.Response(400, request=httpx.Request("POST", "https://x")),
                                  body={"message": message})


def _form(kwargs) -> str:
    """Which of the four off switches a request carries, by the probe's own label."""
    if "reasoning_effort" in kwargs:
        return f"reasoning_effort {kwargs['reasoning_effort']}"
    body = kwargs.get("extra_body") or {}
    return "thinking disabled" if "thinking" in body else "chat_template thinking false"


class ThinkingHost(MeteredLLM):
    """A host that rejects some switches, and answers the rest with this many completion tokens."""

    def __init__(self, completion_by_form=None, error=None):
        super().__init__([])
        self.completion_by_form, self.error = completion_by_form or {}, error

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        form = _form(kwargs)
        if form not in self.completion_by_form:
            raise _400(f"Unsupported parameter for this model: {form}")
        completion = self.completion_by_form[form]
        return _reply(FakeMessage(content="ok"), 20 + completion, prompt=20)


def test_the_first_switch_that_comes_back_quiet_is_kept():
    host = ThinkingHost({"reasoning_effort none": 3, "thinking disabled": 2})
    out = probe_reasoning_off(host, "m")

    assert out["setting"] == "reasoning_effort none" and out["request_extra"] == {"reasoning_effort": "none"}
    assert len(host.requests) == 1, "a quiet answer ends the probe"


def test_a_switch_that_is_accepted_but_ignored_is_passed_over():
    out = probe_reasoning_off(ThinkingHost({"reasoning_effort none": 900, "thinking disabled": 4}), "m")

    assert out["setting"] == "thinking disabled"
    assert out["request_extra"] == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert out["tried"][0] == "reasoning_effort none: 900 completion tokens"


def test_when_nothing_is_quiet_the_quietest_accepted_switch_is_kept():
    out = probe_reasoning_off(ThinkingHost({"reasoning_effort none": 900, "reasoning_effort low": 300}), "m")
    assert out["setting"] == "reasoning_effort low" and out["tokens"]["completion"] == 300


def test_a_model_that_takes_no_switch_runs_as_it_is():
    out = probe_reasoning_off(ThinkingHost(), "m")
    assert out["setting"] is None and out["request_extra"] == {} and len(out["tried"]) == 4


def test_the_probe_does_not_hide_a_real_error():
    with pytest.raises(RuntimeError, match="down"):
        probe_reasoning_off(ThinkingHost(error=RuntimeError("down")), "m")


# ----------------------------------------------------------------------------- the runner

def _record(task, instance, tokens, code=None):
    return {"task_id": task["id"], "instance": instance, "verdict": "approve", "reason": "ok", "sample": False,
            "run_id": "r", "seconds": 1.0, "steps": 3, "tokens": {"total": tokens},
            "stop_reason": "llm_error" if code else "final_answer", "llm_error_code": code}


def _plan(*ids):
    return [({"id": i, "mode": "dry_run"}, "suryodaya") for i in ids]


def test_a_task_starts_only_while_its_whole_limit_fits(monkeypatch, tmp_path):
    caps = []
    monkeypatch.setattr(runner, "run_one", lambda task, instance, root, **kw: caps.append(kw["token_budget"])
                        or _record(task, instance, 10_000))
    book = ResultsBook(tmp_path / "results.json", "suryodaya")

    records = runner.execute(_plan("a", "b", "c", "d", "e"), tmp_path, book, budget=None, token_budget=65_000)

    # Each holds 30k while it runs and hands back the 20k it did not spend: 10+30, 20+30, 30+30 fit; 40+30 does not.
    assert [r["task_id"] for r in records] == ["a", "b", "c", "d"]
    assert caps == [runner.TASK_TOKENS_DEFAULT] * 4
    assert book.doc()["tasks"][-1]["evidence"] == "not run: token budget"


def test_a_spent_platform_budget_stops_the_run(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "run_one", lambda task, instance, root, **kw:
                        _record(task, instance, 2000, code="budget_exhausted" if task["id"] == "a" else None))
    book = ResultsBook(tmp_path / "results.json", "suryodaya")

    records = runner.execute(_plan("a", "b"), tmp_path, book, budget=None, token_budget=None)

    assert [r["task_id"] for r in records] == ["a"]
    assert "LLM budget is used up" in book.doc()["tasks"][1]["evidence"]


def test_evidence_says_how_each_task_ended(tmp_path):
    book = ResultsBook(tmp_path / "results.json", "suryodaya")
    task = {"id": "t", "checks": "Checks a thing."}
    book.record(task, "suryodaya", {**_record(task, "suryodaya", 31_500, code="budget_exhausted"),
                                    "verdict": "revise", "reason": "no finding recorded in AgentMemory"})

    assert book.doc()["tasks"][0]["evidence"] == \
        "revise [3 steps, 31.5k tokens, stop llm_error budget_exhausted]: no finding recorded in AgentMemory"
