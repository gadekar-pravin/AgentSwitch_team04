"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-30).

Ungraded. Cover the local run console (viewer/) without a network, a model or a live tenant.
The graded, hand-written tests live in tests/.
"""
import json
import os

import pytest

from viewer import runs

ROOT = "20260930-101500-000001"


def _task_dir(base, root, instance, task, verdict=None, trace=()):
    d = base / root / instance / task
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    (d / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in trace), encoding="utf-8")
    if verdict:
        (d / "verdict.json").write_text(json.dumps({"verdict": verdict, "reason": "because"}), encoding="utf-8")
    return d


def test_task_without_a_verdict_is_listed_as_unscored_never_approved(tmp_path):
    _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", verdict="approve")
    _task_dir(tmp_path, ROOT, "keystone", "refuse_x")

    [root] = runs.list_run_roots(tmp_path)

    assert root["complete"] is False
    assert {t["instance"]: t["verdict"] for t in root["tasks"]} == {"keystone": None, "suryodaya": "approve"}


def test_listing_skips_adhoc_demo_and_other_folders_and_reads_the_summary(tmp_path):
    for name in ("adhoc", "demo", "notes"):
        (tmp_path / name).mkdir()
    full = tmp_path / "20260917-110938"
    full.mkdir()
    (full / "summary.json").write_text(json.dumps({"approved": 30, "revise": 0, "unevaluated": 0,
                                                   "scored_total": 30}), encoding="utf-8")

    [root] = runs.list_run_roots(tmp_path)

    assert root["name"] == "20260917-110938"
    assert root["complete"] is True
    assert (root["approved"], root["scored_total"]) == (30, 30)


def test_newest_run_is_listed_first(tmp_path):
    for name in ("20260916-114054", ROOT):
        (tmp_path / name).mkdir()

    assert [r["name"] for r in runs.list_run_roots(tmp_path)] == [ROOT, "20260916-114054"]


def test_missing_base_lists_nothing(tmp_path):
    assert runs.list_run_roots(tmp_path / "demo") == []


def test_trace_read_leaves_a_half_written_line_for_the_next_read(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_bytes(b'{"type": "start"}\n{"type": "ll')

    events, offset = runs.read_trace(path)
    assert events == [{"type": "start"}]

    with path.open("ab") as f:
        f.write(b'm", "step": 0}\n')
    events, offset = runs.read_trace(path, offset)
    assert events == [{"type": "llm", "step": 0}]
    assert runs.read_trace(path, offset) == ([], offset)


def test_missing_trace_reads_as_no_events(tmp_path):
    assert runs.read_trace(tmp_path / "trace.jsonl", 5) == ([], 5)


@pytest.mark.parametrize("root,instance,task", [
    ("../etc", "suryodaya", "refuse_x"),
    (ROOT, "elsewhere", "refuse_x"),
    (ROOT, "suryodaya", "../../.env"),
    (ROOT, "suryodaya", "missing_task"),
])
def test_task_dir_refuses_anything_outside_the_run_layout(tmp_path, root, instance, task):
    _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x")

    assert runs.resolve_task_dir(tmp_path, root, instance, task, {"suryodaya", "keystone"}) is None


def test_task_dir_resolves_a_real_run(tmp_path):
    d = _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x")

    assert runs.resolve_task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", {"suryodaya", "keystone"}) == d


def test_task_run_reports_the_same_write_ordering_the_checker_requires(tmp_path):
    d = _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", verdict="approve", trace=[{"type": "start"}])
    os.utime(d / "result.json", (1000, 1000))
    os.utime(d / "verdict.json", (2000, 2000))

    run = runs.load_task_run(d)
    assert run["persisted_before_verdict"] is True
    assert run["verdict"]["verdict"] == "approve"
    assert run["trace"] == [{"type": "start"}]
    assert run["fixture"] is None

    os.utime(d / "result.json", (3000, 3000))
    assert runs.load_task_run(d)["persisted_before_verdict"] is False
