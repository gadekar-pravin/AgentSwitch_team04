# Team 04: Production agent for AgentSwitch

> "This work order is late. Find out why, tell me what it blocks downstream, and reschedule what you can."

Our own agent loop (no framework) driving AgentSwitch over MCP, plus a harness that stores every run on disk before verifying it against the database.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in both passwords and OPENAI_API_KEY; .env is git-ignored
```

## Run the agent

```bash
python -m prod_agent --instance suryodaya "WO-2026-00048 is late. Why, what does it block, and reschedule what you can."
python -m prod_agent --instance keystone  "..." --apply    # offers writes; each needs y at the prompt
```

Each run writes `runs/adhoc/<timestamp>-<instance>/trace.jsonl` and `result.json`.

## Run the harness

```bash
python -m harness.runner                          # every task, every instance it declares
python -m harness.runner --task <id> --instance keystone
python -m harness.runner --include-samples
```

Output goes to `runs/<timestamp>/<instance>/<task>/`: `task.json`, `fixture.json`, `trace.jsonl` (written event by event), and `result.json`, all fsync'd **before** the verifier writes `verdict.json`. Verdicts are `approve`, `revise` or `unevaluated`, and unevaluated never counts as a pass. See [harness/tasks/README.md](harness/tasks/README.md) for the task and verifier format.

## Layout

| path | what |
|---|---|
| `prod_agent/mcp_client.py` | JSON-RPC MCP client (errors arrive as HTTP 200) and an independent REST client for verifiers |
| `prod_agent/domain.py` | deterministic logic: `diagnose`, `downstream_impact`, `propose_reschedule`, `apply_proposal`, `record_finding` |
| `prod_agent/agent.py` | the loop, tool specs and system prompt |
| `harness/` | runner, verifier context, fixtures, task set |
| `tests/` | hand-written tests only |
| `GAP_REPORT.md` | week-one gap report (benchmark: Carbon) |
| `docs/BUGS_FILED.md` | platform bugs filed by the team |

## How the agent stays safe in a shared book

- **Re-reads before writing.** Each proposal carries `updated_at`. If the row changed or its status moved, the write is skipped with `changed_underneath`.
- **Writes only what the seat can write.** Submitted work orders are date-locked for `manufacturing_user` (verified live), so the agent writes dates on drafts only and proposes the rest.
- **Two gates on writes.** Every write needs approval (a human prompt in the CLI; in the harness, only the team's own fixture rows) and must be in the allowed-id set.
- **The finding goes into the database.** `record_finding` stores the structured conclusion in AgentMemory (private to our team), so verifiers read state, not prose.
- **Nothing is hardcoded to one country.** Country and currency come from `Company`, and missing tools (e.g. SalesOrder on Keystone) are detected, not assumed.

## Seat limits the agent reports rather than works around (2026-09-16)

- JobCard and DowntimeEntry: permission denied on both instances, despite the schema granting read.
- SalesOrder: read-only on Suryodaya, absent on Keystone.
- No PurchaseOrder or StockEntry tools. WorkOrder has no parent/child link, so downstream impact comes from a reverse walk of BOM materials.
- WorkOrder cancel requires admin.

## Rows this team created on Suryodaya

- WO-2026-00122: probe for the write-lock test, not_started, cannot be cancelled by our role.
- WO-2026-00123 and WO-2026-00124: harness fixtures (drafts, reused and reset every run).
