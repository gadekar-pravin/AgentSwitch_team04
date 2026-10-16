"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-16).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Local run, 2026-10-16 (gpt-4.1): stopped_not_late scored revise with "is_late=True but WO-2026-00122 is due
2027-06-12". The agent had reported what diagnose told it. finite_schedule answered "late" for that order
with no projected finish and a capacity_ceiling cause at 14 and 30 days, and "on_time", finishing
2026-12-05, at 90; diagnose asks for 14. A "late" with no projected finish, for an order due after the
horizon ends, means the scheduler ran out of horizon, not that the order will miss its date.

Run: python -m pytest tests_ai/test_late_beyond_horizon.py -q
"""
import datetime as dt

import pytest
from test_behaviour_fakes import TODAY, Book, pin_today, schedule_entry, work_order

from prod_agent import domain


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    pin_today(monkeypatch)


def _late(**entry):
    return {"verdict": "late", "projected_finish": None, **entry}


def test_a_late_verdict_with_no_finish_for_an_order_due_past_the_horizon_is_not_late():
    due = TODAY + dt.timedelta(days=270)
    assert domain._schedule_late(_late(causes=[{"code": "capacity_ceiling"}]), due, TODAY) is False


def test_a_late_verdict_with_a_projected_finish_still_counts_however_far_off_the_due_date():
    due = TODAY + dt.timedelta(days=270)
    assert domain._schedule_late(_late(projected_finish="2027-07-01"), due, TODAY) is True


def test_a_late_verdict_for_an_order_due_inside_the_horizon_still_counts():
    due = TODAY + dt.timedelta(days=domain.SCHEDULE_HORIZON_DAYS)
    assert domain._schedule_late(_late(), due, TODAY) is True


@pytest.mark.parametrize("entry", [None, {}, {"verdict": "on_time", "projected_finish": None}])
def test_no_late_verdict_is_not_late(entry):
    assert domain._schedule_late(entry, TODAY + dt.timedelta(days=3), TODAY) is False


def test_the_live_order_is_reported_on_time_by_diagnose():
    wo = work_order("WO-2026-00122", "not_started", start="2026-11-01", end="2027-06-12")
    book = Book(tables={"WorkOrder": [wo]},
                schedule=[schedule_entry(wo, "late", causes=[{"code": "capacity_ceiling", "workstation_label": None}])])
    diag = domain.diagnose(book, "WO-2026-00122")

    assert diag["is_late"] is False
    assert diag["schedule"]["verdict"] == "late", "the schedule's own word is still shown, not hidden"


def test_list_late_work_orders_leaves_it_out_too():
    wo = work_order("WO-2026-00122", "not_started", start="2026-11-01", end="2027-06-12")
    overdue = work_order("WO-2026-00048", "stopped", start="2026-08-01", end="2026-08-20")
    book = Book(tables={"WorkOrder": [wo, overdue]}, schedule=[schedule_entry(wo, "late")])

    assert [w["number"] for w in domain.list_late_work_orders(book)] == ["WO-2026-00048"]
