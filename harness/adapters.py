"""Adapters that let tests drive the real agent loop and harness with fake inputs.

Plumbing, not tests. Written by Claude (AI-assisted). Every function here delegates to the real
code (ProductionAgent, VerifyContext, harness verifiers, runner.persist_then_verify), so tests that
use it exercise production behaviour, not a re-implementation.
"""
import copy
import json
from pathlib import Path

from prod_agent import config
from prod_agent.agent import ProductionAgent

from .runner import _write, persist_then_verify
from .verify import Verdict, VerifyContext
from .verifiers import team04

# ----------------------------------------------------------------------------- agent loop

_agents: dict[tuple[int, str], ProductionAgent] = {}


def run_agent(llm, mcp, max_steps: int = 20, request: str = "test request") -> dict:
    """Run the real loop with a fake model. Returns the run outcome plus every traced event."""
    events: list[dict] = []
    agent = ProductionAgent(mcp, llm=llm, trace=events.append, max_steps=max_steps)
    return {**agent.run(request), "trace": events}


def dispatch_tool(name: str, arguments: dict, mcp, run_id: str):
    """Dispatch one tool call on the agent for (mcp, run_id), so repeated calls share one run."""
    key = (id(mcp), run_id)
    if key not in _agents:
        _agents[key] = ProductionAgent(mcp, llm=object(), run_id=run_id)
    return _agents[key]._dispatch(name, arguments)


# ----------------------------------------------------------------------------- harness

class _RestShim:
    """Presents simple fake rows in the shapes the real REST client returns.

    findings:    [{"id", "run_id", "outcome", ...}] -> AgentMemory rows with the finding prefix
    work_orders: [{"id", "number", ...}]          -> WorkOrder rows
    """

    def __init__(self, fake):
        self.fake = fake

    @staticmethod
    def _rows(value):
        return value.get("data", []) if isinstance(value, dict) else list(value or [])

    def raw(self, path, **params):
        rows = []
        for f in self._rows(self.fake.raw(path, **params)):
            payload = {k: v for k, v in f.items() if k not in ("id", "created_by")}
            rows.append({"id": f["id"], "created_by": f.get("created_by"),
                         "content": config.FINDING_PREFIX + json.dumps(payload)})
        return {"data": rows}

    def list(self, entity, **params):
        rows = self._rows(self.fake.list(entity, **params))
        search = params.get("search")
        return [r for r in rows if not search or search in (r.get("number") or "")]

    def get(self, entity, record_id):
        for r in self._rows(self.fake.list(entity)):
            if r.get("id") == record_id:
                return copy.deepcopy(r)
        raise KeyError(record_id)


def make_verify_context(run_dir: Path, rest, context: dict, task: dict | None = None) -> VerifyContext:
    return VerifyContext(rest=_RestShim(rest), instance="test", task=task or {}, run_dir=Path(run_dir),
                         fixture=None, context=context)


def find_run_finding(ctx: VerifyContext):
    finding = ctx.finding_from_db()
    return (finding, finding["_agent_memory_id"]) if finding else (None, None)


def changed_work_orders(ctx: VerifyContext, exclude_ids=None) -> list[str]:
    return ctx.my_writes_since_start("WorkOrder", exclude_ids=exclude_ids or ())


def verify_unknown_order(ctx: VerifyContext, order_number: str) -> str:
    if order_number != "WO-2026-09999":
        raise ValueError("the refuse_unknown_work_order verifier is defined for WO-2026-09999")
    verdict, _reason = team04.refuse_unknown_work_order(ctx)
    return verdict.name


def run_task(run_dir: Path, agent, verifier) -> tuple[str, str]:
    """Same persist-then-verify path the runner uses. Verifier exceptions propagate to the test."""
    run_dir = Path(run_dir)
    result = agent()

    def verify():
        outcome = verifier()
        return Verdict[outcome] if isinstance(outcome, str) else outcome

    verdict, reason = persist_then_verify(run_dir, result, verify, catch=False)
    _write(run_dir / "verdict.json", {"verdict": verdict.value, "reason": reason})
    return verdict.name, reason
