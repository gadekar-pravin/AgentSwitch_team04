"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Full local harness run, 2026-10-16 (79d9c6b, gpt-4.1): bottleneck_lanes_reported scored revise on Suryodaya.
Asked where the shop floor is stuck right now, the agent named the cockpit's first examples,
QI-2026-00008/21/34: rejected inspections, but on work orders that had already closed. The blocks on open
orders (QI-2026-00049, QI-2026-00061) went unnamed, because the cockpit lists both alike. shop_floor_exceptions
now reads each block's work order and lists the ones on open orders first.

Run: python -m pytest tests_ai/test_shop_floor_open_orders.py -q
"""
from prod_agent import domain
from prod_agent.mcp_client import McpError
from tests_ai.test_capacity_and_policy import FakeMcp

COCKPIT = "endpoint.manufacturing.exception_cockpit"
ORDERS = [{"id": "wo-done", "number": "WO-2026-00010", "status": "completed"},
          {"id": "wo-run", "number": "WO-2026-00054", "status": "in_progress"},
          {"id": "wo-stop", "number": "WO-2026-00048", "status": "stopped"},
          {"id": "wo-draft", "number": "WO-2026-00119", "status": "draft"}]
INSPECTIONS = [{"id": f"qi-{n}", "number": f"QI-2026-000{n}", "reference_id": ref}
               for n, ref in (("08", "wo-done"), ("21", "wo-done"), ("34", "wo-done"), ("49", "wo-run"), ("61", "wo-stop"))]
SUBCONTRACTS = [{"id": "sco-1", "number": "SCO-2026-00001", "work_order_id": None},
                {"id": "sco-2", "number": "SCO-2026-00002", "work_order_id": "wo-done"},
                {"id": "sco-7", "number": "SCO-2026-00007", "work_order_id": "wo-draft"}]


def _item(kind, entity, row):
    return {"kind": kind, "entity": entity, "record_id": row["id"], "record_label": row["number"],
            "severity": "high", "state": "ready", "diagnostic": {"code": "quality_review"}}


# In the cockpit's own order, closed orders first, as it listed them live.
ITEMS = [_item("quality_block", "QualityInspection", q) for q in INSPECTIONS] + \
        [_item("subcontract_block", "SubcontractOrder", s) for s in SUBCONTRACTS]


def _mcp(cls=FakeMcp, **over):
    lists = {"QualityInspection": INSPECTIONS, "SubcontractOrder": SUBCONTRACTS, "WorkOrder": ORDERS, **over}
    return cls(tools={COCKPIT}, lists=lists,
               calls={COCKPIT: {"result": {"total_items": len(ITEMS), "complete": True, "lane_states": {}, "items": ITEMS}}})


def _lane(out, kind):
    return next(lane for lane in out["lanes"] if lane["kind"] == kind)


def test_blocks_on_open_orders_are_the_examples_named_first():
    lane = _lane(domain.shop_floor_exceptions(_mcp()), "quality_block")

    assert [e["record"] for e in lane["examples"]] == ["QI-2026-00049", "QI-2026-00061", "QI-2026-00008"]
    assert [e["order_open"] for e in lane["examples"]] == [True, True, False]
    assert lane["examples"][0]["work_order"] == "WO-2026-00054"
    assert lane["count"] == 5 and lane["on_open_orders"] == 2


def test_a_block_naming_no_order_sits_between_open_and_closed_ones():
    lane = _lane(domain.shop_floor_exceptions(_mcp()), "subcontract_block")

    assert [e["record"] for e in lane["examples"]] == ["SCO-2026-00007", "SCO-2026-00001", "SCO-2026-00002"]
    assert "order_open" not in lane["examples"][1], "no work order to describe, so none is claimed"
    assert lane["on_open_orders"] == 1


def test_an_unreadable_link_keeps_the_cockpits_own_order():
    class Denied(FakeMcp):
        def list_all(self, entity, page=200, max_rows=None, **filters):
            if entity == "QualityInspection":
                raise McpError(403, "forbidden")
            return super().list_all(entity, page, max_rows, **filters)

    lane = _lane(domain.shop_floor_exceptions(_mcp(Denied)), "quality_block")

    assert [e["record"] for e in lane["examples"]] == ["QI-2026-00008", "QI-2026-00021", "QI-2026-00034"]
    assert "order_open" not in lane["examples"][0] and "on_open_orders" not in lane


def test_lanes_whose_items_name_no_record_are_read_as_before():
    """The cockpit's other lanes carry no QualityInspection or SubcontractOrder id: nothing extra is read."""
    reads = []

    class Counting(FakeMcp):
        def list_all(self, entity, page=200, max_rows=None, **filters):
            reads.append(entity)
            return super().list_all(entity, page, max_rows, **filters)

    items = [{"kind": "automation_failure", "entity": "AgentJob", "record_label": "JOB-1", "severity": "low"}]
    mcp = Counting(tools={COCKPIT}, calls={COCKPIT: {"result": {"total_items": 1, "items": items}}})
    out = domain.shop_floor_exceptions(mcp)

    assert reads == []
    assert out["lanes"][0]["examples"][0]["record"] == "JOB-1"
