"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

Ungraded. scripts/check_premises.py calls each verifier with no finding to learn whether a task's premise still
holds before a submission is spent on it. These pin how it reads a verdict and that it never runs a fixture that
writes. The graded, hand-written tests live in tests/.
"""
import importlib.util

from harness.verify import Verdict
from prod_agent import config

_spec = importlib.util.spec_from_file_location("check_premises", config.ROOT / "scripts" / "check_premises.py")
check_premises = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_premises)


def test_revise_for_a_run_that_did_nothing_means_the_premise_held():
    assert check_premises.classify(Verdict.REVISE, "no finding recorded in AgentMemory") == "holds"
    # escalation_raised_for checks its premise, then the run's own escalation, before its finding.
    assert check_premises.classify(Verdict.REVISE, "no escalation naming WO-2026-00048 raised by this seat") == "holds"


def test_any_unevaluated_is_reported_as_gone():
    assert check_premises.classify(Verdict.UNEVALUATED, "premise gone: WO-2026-00003 not found") == "GONE"
    # keystone_stopped_not_late words it differently; it is still a task that scores 0 today.
    assert check_premises.classify(Verdict.UNEVALUATED, "no work order is open and not late on this instance "
                                                        "today; nothing to check") == "GONE"


def test_approving_a_run_that_did_nothing_is_shown_not_counted_as_held():
    assert check_premises.classify(Verdict.APPROVE, "no draft subcontracts in DB and none claimed") == "OTHER"
    assert check_premises.classify(Verdict.UNEVALUATED, "verifier returned None, not a Verdict") == "OTHER"


def test_a_writing_fixture_is_skipped_before_anything_is_called(monkeypatch, tmp_path):
    def must_not_run(mcp):
        raise AssertionError("a writing fixture ran")

    monkeypatch.setitem(check_premises.FIXTURES, "late_draft_chain", must_not_run)
    task = {"id": "reschedule_fixture_chain", "fixture": "late_draft_chain", "verifier": "x:y"}

    status, reason = check_premises.check(task, "suryodaya", session=None, work=tmp_path)

    assert status == "skip" and "late_draft_chain" in reason


def test_the_verifier_sees_a_run_that_recorded_nothing(monkeypatch, tmp_path):
    seen = {}

    def verifier(ctx):
        seen["run_id"] = ctx.run_id
        return Verdict.REVISE, "no finding recorded in AgentMemory"

    monkeypatch.setattr(check_premises.runner, "capture_context", lambda rest, task: {"me": "u1", "snapshot": {}})
    monkeypatch.setattr(check_premises.runner, "_load_verifier", lambda ref: verifier)
    task = {"id": "keystone_why_late_wo3", "fixture": None, "verifier": "x:y"}

    assert check_premises.check(task, "keystone", session=None, work=tmp_path)[0] == "holds"
    assert seen["run_id"].startswith("premise-check-")
