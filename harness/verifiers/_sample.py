"""SAMPLE verifier written by Claude to show the plumbing. Not graded. Write yours in a new module."""
from harness.verify import Verdict, VerifyContext


def finding_was_recorded(ctx: VerifyContext):
    finding = ctx.finding_from_db()
    if finding is None:
        return Verdict.REVISE, "no finding row in AgentMemory for this run"
    return Verdict.APPROVE, f"finding {finding['_agent_memory_id']} recorded with outcome {finding.get('outcome')}"
