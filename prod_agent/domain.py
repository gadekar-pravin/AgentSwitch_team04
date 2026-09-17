"""Deterministic production logic: why a work order is late, what it blocks, what can move.

Every function re-reads live data. Nothing is cached across calls, because other teams
change the shared book while the agent runs.
"""
import datetime as dt
import json
import re

from . import config
from .mcp_client import McpClient, McpError

OPEN_WO = {"draft", "not_started", "in_progress", "stopped"}
OPEN_MR = {"draft", "submitted", "partially_ordered", "ordered"}
DONE_SCO = {"completed", "cancelled"}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# Signals whose ready date is unknown: no reschedule date can honestly be committed.
UNDATED_BLOCKERS = {
    "subcontract_not_sent", "subcontract_overdue", "material_shortage",
    "quality_rejected", "workstation_unavailable",
}


def _date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


def _wo_summary(wo: dict) -> dict:
    return {
        "id": wo["id"],
        "number": wo.get("number"),
        "item": wo.get("_item_id_display") or wo.get("item_id"),
        "item_id": wo.get("item_id"),
        "status": wo.get("status"),
        "priority": wo.get("priority"),
        "qty": wo.get("qty"),
        "produced_qty": wo.get("produced_qty"),
        "planned_start_date": (wo.get("planned_start_date") or "")[:10] or None,
        "planned_end_date": (wo.get("planned_end_date") or "")[:10] or None,
        "sales_order_id": wo.get("sales_order_id"),
        "production_strategy": wo.get("production_strategy"),
        "expected_cost": wo.get("expected_cost"),
        "actual_cost": wo.get("actual_cost"),
        "updated_at": wo.get("updated_at"),
    }


def _probe_denied(mcp: McpClient, tool: str) -> str | None:
    """Return a reason if this seat cannot use `tool`, else None."""
    if not mcp.has_tool(tool):
        return "tool_not_in_seat_catalogue"
    try:
        mcp.call(tool, {"limit": 1} if tool.endswith(".list") else {})
        return None
    except McpError as e:
        return e.kind if e.kind in ("permission_denied", "row_scope_denied") else None


# --------------------------------------------------------------------------- lookups

def resolve_work_order(mcp: McpClient, ref: str) -> dict | None:
    ref = (ref or "").strip()
    if UUID_RE.match(ref):
        try:
            return mcp.call("WorkOrder.get", {"id": ref})
        except McpError as e:
            if e.kind == "not_found" or "not found" in e.message.lower():
                return None
            raise
    matches = [w for w in mcp.list_all("WorkOrder", search=ref) if (w.get("number") or "").upper() == ref.upper()]
    return mcp.call("WorkOrder.get", {"id": matches[0]["id"]}) if matches else None


def finite_schedule(mcp: McpClient, horizon_days: int = 14) -> dict:
    res = mcp.call("endpoint.manufacturing.finite_schedule", {"horizon_days": horizon_days})
    return res.get("result", res)


def seat_entities(mcp: McpClient) -> list[str]:
    return sorted({name.split(".")[0] for name in mcp.tool_names() if not name.startswith("endpoint.")})


def _words(name: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Z][a-z]+|[a-z]+", name) if len(w) > 2}


def seat_capability(mcp: McpClient, tool: str) -> dict:
    present = mcp.has_tool(tool)
    denied = _probe_denied(mcp, tool) if present and tool.endswith(".list") else None
    result = {"tool": tool, "in_catalogue": present, "usable": present and not denied, "denied_reason": denied}
    if not present:
        entity = tool.split(".")[0]
        entities = seat_entities(mcp)
        if entity not in entities:
            # An invented name proves nothing about access; point at the real entities instead.
            result["warning"] = f"'{entity}' is not an entity on this platform seat; check a real entity before concluding"
            result["similar_entities"] = [e for e in entities if _words(e) & _words(entity)][:5]
    return result


def company_context(mcp: McpClient) -> dict:
    """Country and currency come from data, never from assumptions about which book we are in."""
    companies = mcp.list_all("Company")
    wo = mcp.call("WorkOrder.list", {"limit": 1}).get("data", [])
    company_id = wo[0]["company_id"] if wo else (companies[0]["id"] if companies else None)
    c = mcp.call("Company.get", {"id": company_id}) if company_id else {}
    return {"company": c.get("_display") or c.get("name"), "country": c.get("country"),
            "currency": c.get("default_currency"), "instance": mcp.session.instance}


def list_late_work_orders(mcp: McpClient) -> list[dict]:
    today = config.today()
    sched = {o["work_order_id"]: o for o in finite_schedule(mcp).get("orders", [])}
    late = []
    for wo in mcp.list_all("WorkOrder"):
        if wo.get("status") not in OPEN_WO:
            continue
        due = _date(wo.get("planned_end_date"))
        entry = sched.get(wo["id"], {})
        if (due and due < today) or entry.get("verdict") == "late":
            s = _wo_summary(wo)
            s["days_past_due"] = (today - due).days if due else None
            s["projected_finish"] = entry.get("projected_finish")
            late.append(s)
    return sorted(late, key=lambda s: s["planned_end_date"] or "9999")


# --------------------------------------------------------------------------- diagnosis

def diagnose(mcp: McpClient, ref: str) -> dict:
    wo = resolve_work_order(mcp, ref)
    if not wo:
        return {"found": False, "ref": ref}
    today = config.today()
    wid = wo["id"]
    due = _date(wo.get("planned_end_date"))
    signals: list[dict] = []

    def sig(code, record=None, **detail):
        signals.append({"code": code, "blocking": code in UNDATED_BLOCKERS, "record": record, **detail})

    status = wo.get("status")
    if status == "draft":
        sig("not_released", wo.get("number"))
    if status == "stopped":
        sig("stopped_without_recorded_reason", wo.get("number"))
    start = _date(wo.get("planned_start_date"))
    if status == "not_started" and start and start < today:
        sig("not_started_past_planned_start", wo.get("number"), planned_start=_iso(start))

    for sco in mcp.list_all("SubcontractOrder", work_order_id=wid):
        if sco.get("work_order_id") != wid or sco.get("status") in DONE_SCO:
            continue
        expected = _date(sco.get("expected_delivery_date"))
        detail = {"status": sco.get("status"), "expected_delivery_date": _iso(expected),
                  "vendor": sco.get("_vendor_id_display") or sco.get("vendor_id")}
        if sco.get("status") == "draft":
            sig("subcontract_not_sent", sco.get("number"), **detail)
        elif expected and expected < today:
            sig("subcontract_overdue", sco.get("number"), **detail)
        else:
            sig("subcontract_pending", sco.get("number"), ready_date=_iso(expected), **detail)

    for mr in mcp.list_all("MaterialRequest", work_order_id=wid):
        if mr.get("work_order_id") != wid or mr.get("status") not in OPEN_MR:
            continue
        required_by = _date(mr.get("required_by_date"))
        sig("material_request_open", mr.get("number"), status=mr.get("status"),
            required_by_date=_iso(required_by),
            ready_date=_iso(required_by) if required_by and required_by >= today else None,
            overdue=bool(required_by and required_by < today))

    try:
        stock = mcp.call("endpoint.manufacturing.check_stock_availability", {"work_order_id": wid})
        items = stock.get("result", stock).get("items", [])
        for it in items:
            if (it.get("shortage") or 0) > 0:
                sig("material_shortage", it.get("item_id"), required=it.get("required"),
                    available=it.get("available"), shortage=it.get("shortage"), critical=it.get("is_critical"))
        if items and all((it.get("available") or 0) == 0 for it in items):
            sig("stock_check_unreliable", None, note="every component reports 0 available (known platform defect)")
    except McpError as e:
        sig("stock_check_failed", None, error=e.message)

    for qi in mcp.list_all("QualityInspection", reference_id=wid):
        if qi.get("reference_id") != wid:
            continue
        if qi.get("overall_result") == "rejected":
            sig("quality_rejected", qi.get("number") or qi["id"], rejected_qty=qi.get("rejected_qty"))
        elif qi.get("status") == "draft" and wo.get("quality_inspection_required"):
            sig("quality_inspection_pending", qi.get("number") or qi["id"])

    sched = finite_schedule(mcp)
    entry = next((o for o in sched.get("orders", []) if o["work_order_id"] == wid), None)
    load = {w["workstation_id"]: w for w in sched.get("workstation_load", [])}
    if entry:
        for cause in entry.get("causes", []):
            if cause.get("code") != "work_content_exceeds_due_date":
                sig(f"schedule_{cause['code']}", cause.get("workstation_label"), minutes=cause.get("minutes"))
        for ws_id in {op["workstation_id"] for op in entry.get("operations", []) if op.get("workstation_id")}:
            ws = load.get(ws_id, {})
            if ws.get("state") == "unavailable":
                sig("workstation_unavailable", ws.get("record_label"), status=ws.get("status_code"))
            if (ws.get("downtime_minutes") or 0) > 0:
                sig("workstation_downtime", ws.get("record_label"), downtime_minutes=round(ws["downtime_minutes"], 1))

    not_visible = [f"{t.split('.')[0]}: {r}" for t in ("JobCard.list", "DowntimeEntry.list")
                   if (r := _probe_denied(mcp, t))]

    return {
        "found": True,
        "work_order": _wo_summary(wo),
        "today": _iso(today),
        "is_late": bool(status in OPEN_WO and ((due and due < today) or (entry or {}).get("verdict") == "late")),
        "days_past_due": (today - due).days if due and status in OPEN_WO else None,
        "schedule": {k: (entry or {}).get(k) for k in ("verdict", "projected_finish", "days_late")},
        "route_workstations": sorted({op.get("workstation_label") for op in (entry or {}).get("operations", [])} - {None}),
        "signals": signals,
        "not_visible_to_this_seat": not_visible,
    }


# --------------------------------------------------------------------------- downstream

def downstream_impact(mcp: McpClient, ref: str, max_depth: int = 3) -> dict:
    wo = resolve_work_order(mcp, ref)
    if not wo:
        return {"found": False, "ref": ref}
    open_wos = [w for w in mcp.list_all("WorkOrder") if w.get("status") in OPEN_WO]
    bom_inputs = {b["id"]: {m.get("item_id") for m in (b.get("materials") or [])} for b in mcp.list_all("BOM")}

    blocked, visited, frontier = [], {wo["id"]}, [(wo, 0)]
    while frontier:
        parent, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for w in open_wos:
            if w["id"] in visited or parent.get("item_id") not in bom_inputs.get(w.get("bom_id"), set()):
                continue
            visited.add(w["id"])
            blocked.append({**_wo_summary(w), "depth": depth + 1, "consumes_output_of": parent.get("number")})
            frontier.append((w, depth + 1))

    so_ids = {}
    for w in [_wo_summary(wo)] + blocked:
        if w.get("sales_order_id"):
            so_ids.setdefault(w["sales_order_id"], w["number"])

    chain = [_wo_summary(wo)] + blocked
    unlinked_mto = [w["number"] for w in chain if w.get("production_strategy") == "make_to_order" and not w.get("sales_order_id")]
    so_visible = mcp.has_tool("SalesOrder.get")

    sales_orders, not_visible = [], []
    if not so_visible:
        not_visible.append("SalesOrder: tool_not_in_seat_catalogue (customer impact cannot be determined)")
    elif so_ids:
        for so_id, via in so_ids.items():
            try:
                so = mcp.call("SalesOrder.get", {"id": so_id})
            except McpError as e:
                not_visible.append(f"SalesOrder {so_id}: {e.kind}")
                continue
            sales_orders.append({
                "id": so_id, "number": so.get("number"), "customer": so.get("_party_id_display") or so.get("party_id"),
                "delivery_date": (so.get("delivery_date") or "")[:10] or None, "grand_total": so.get("grand_total"),
                "delivered_status": so.get("delivered_status"), "status": so.get("status"), "via_work_order": via,
            })

    if not so_visible:
        customer_impact = "undeterminable: sales orders are not visible to this seat"
    elif unlinked_mto:
        customer_impact = f"partly unknown: make-to-order without a linked sales order: {', '.join(unlinked_mto)}"
    elif sales_orders:
        customer_impact = "known"
    else:
        customer_impact = "none linked: no sales order on this order or its dependants"

    return {
        "found": True,
        "work_order": _wo_summary(wo),
        "customer_impact": customer_impact,
        "make_to_order_without_sales_order": unlinked_mto,
        "blocked_work_orders": blocked,
        "blocked_sales_orders": sales_orders,
        "method": "reverse walk of BOM materials over open work orders; WorkOrder has no parent/child link",
        "not_visible_to_this_seat": not_visible,
    }


# --------------------------------------------------------------------------- reschedule

def propose_reschedule(mcp: McpClient, ref: str) -> dict:
    diag = diagnose(mcp, ref)
    if not diag["found"]:
        return diag
    down = downstream_impact(mcp, ref)
    today = config.today()
    target = diag["work_order"]

    undated = [s for s in diag["signals"] if s["blocking"]]
    ready_dates = [_date(s["ready_date"]) for s in diag["signals"] if s.get("ready_date")]
    proposals = []

    def proposal(w, new_start, new_end, reason, commit_ok=True):
        writable = w["status"] == "draft"
        return {
            "work_order_id": w["id"], "number": w["number"], "status": w["status"],
            "current_start": w["planned_start_date"], "current_end": w["planned_end_date"],
            "new_start": _iso(new_start), "new_end": _iso(new_end), "reason": reason,
            "date_committable": commit_ok,
            "writable_by_seat": writable and commit_ok,
            "why_not_writable": None if writable and commit_ok else (
                "no committable date: " + ", ".join(sorted({s['code'] for s in undated})) if not commit_ok
                else f"status '{w['status']}': dates are locked after submit; changing them needs an admin cancel"),
            "snapshot_updated_at": w["updated_at"],
        }

    def duration(w):
        s, e = _date(w["planned_start_date"]), _date(w["planned_end_date"])
        return dt.timedelta(days=max((e - s).days, 1) if s and e else 1)

    target_end = None
    if target["status"] in ("in_progress", "completed", "cancelled"):
        pass  # already running or closed; nothing to move for the target itself
    elif undated:
        proposals.append(proposal(target, None, None, "blocked by an event with no known date", commit_ok=False))
    else:
        new_start = max([today] + [d for d in ready_dates if d])
        new_end = new_start + duration(target)
        projected = _date(diag["schedule"].get("projected_finish"))
        if projected and projected > new_end:
            new_end = projected
        target_end = new_end
        if (_iso(new_start), _iso(new_end)) != (target["planned_start_date"], target["planned_end_date"]):
            proposals.append(proposal(target, new_start, new_end, "earliest start after known blockers; finish from finite schedule"))

    upstream_end = {target["number"]: target_end}
    for w in down["blocked_work_orders"]:
        parent_end = upstream_end.get(w["consumes_output_of"])
        if w["status"] in ("in_progress", "stopped"):
            upstream_end[w["number"]] = None
            continue
        if parent_end is None:
            proposals.append(proposal(w, None, None, f"waits on {w['consumes_output_of']}, whose date cannot be committed", commit_ok=False))
            upstream_end[w["number"]] = None
            continue
        start = _date(w["planned_start_date"])
        if start and start > parent_end:
            upstream_end[w["number"]] = _date(w["planned_end_date"])
            continue
        new_start = parent_end + dt.timedelta(days=1)
        new_end = new_start + duration(w)
        upstream_end[w["number"]] = new_end
        proposals.append(proposal(w, new_start, new_end, f"must start after {w['consumes_output_of']} finishes"))

    return {"found": True, "work_order": target, "today": _iso(today), "proposals": proposals,
            "downstream_considered": [b["number"] for b in down["blocked_work_orders"]]}


def apply_proposal(mcp: McpClient, p: dict, allowed_ids: set[str] | None = None) -> dict:
    """Write one proposal, re-reading first. Never writes a row that changed since it was proposed."""
    out = {"work_order_id": p["work_order_id"], "number": p["number"]}
    if allowed_ids is not None and p["work_order_id"] not in allowed_ids:
        return {**out, "outcome": "refused", "detail": "work order is outside the approved set"}
    if not p.get("writable_by_seat"):
        return {**out, "outcome": "refused", "detail": p.get("why_not_writable")}
    current = mcp.call("WorkOrder.get", {"id": p["work_order_id"]})
    if current.get("updated_at") != p["snapshot_updated_at"] or current.get("status") != p["status"]:
        return {**out, "outcome": "changed_underneath",
                "detail": {"status": current.get("status"), "updated_at": current.get("updated_at")}}
    try:
        mcp.call("WorkOrder.update", {"id": p["work_order_id"],
                                       "planned_start_date": p["new_start"], "planned_end_date": p["new_end"]})
    except McpError as e:
        return {**out, "outcome": "write_rejected", "detail": e.message}
    after = mcp.call("WorkOrder.get", {"id": p["work_order_id"]})
    ok = (after.get("planned_start_date") or "")[:10] == p["new_start"] and (after.get("planned_end_date") or "")[:10] == p["new_end"]
    return {**out, "outcome": "applied" if ok else "write_not_persisted",
            "planned_start_date": after.get("planned_start_date"), "planned_end_date": after.get("planned_end_date")}


# --------------------------------------------------------------------------- findings

def record_finding(mcp: McpClient, run_id: str, finding: dict) -> dict:
    """Persist the agent's conclusion so verifiers read the database, not the reply text."""
    payload = {"run_id": run_id, "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(), **finding}
    row = mcp.call("AgentMemory.create", {
        "content": config.FINDING_PREFIX + json.dumps(payload, sort_keys=True),
        "category": "fact", "source": "system", "importance": 0.5, "is_active": True,
    })
    return {"agent_memory_id": row.get("id"), "run_id": run_id}
