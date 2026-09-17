# Gap Report — Production Seat (Team 04)

**Team:** Ramesh, Nishanth, Pravin Gadekar  **Measured:** 16–17 September 2026, Suryodaya (India) and Keystone (US)
**Request:** *"This work order is late. Find out why, tell me what it blocks downstream, and reschedule what you can."*
**Evidence labels:** *documented* = Carbon's docs or public source · *observed* = seen live in AgentSwitch · *untested* = not safely exercised

## Why Carbon

[Carbon](https://carbon.ms) is an AI-native, open-source manufacturing system (ERP, MES and quality on one data model) that ships an **MCP server** over its production data, so the bar for our agent is public. We reviewed its scheduling and MCP documentation and public source (*documented*, not run in a trial). Tulip's Production Dispatcher agent was a secondary reference.

## What we have

Work orders with a six-state workflow; job cards, downtime entries and engineering changes; BOMs, routings, workstations, material requests, subcontract orders and inspections; a finite-schedule endpoint and a stock check.

## 1. What Carbon does that we do not

| Capability | Carbon (*documented*) | AgentSwitch today (*observed*) | Gap assessment |
|---|---|---|---|
| **Capacity-aware scheduling** | Places operations within work-centre hours, subtracts maintenance downtime, reserves qualified operators | The schedule projects open orders to finish today and models neither work calendars nor labour. After our report, the platform says recorded downtime now reduces capacity (fixed 17 Sep, not yet re-measured by us) | **Platform defect and model gap** |
| **Specific delay reasons** | Operation-level reasons: waiting behind a named job, a work centre, or an operator | After the 17 Sep release, all 51 late Suryodaya orders get a generic "due date passed" cause; 46 also cite recorded downtime, often on another workstation. None says "waiting behind a job" or "no operator", and none is marked blocking | **Agent partly**; platform output gap |
| **What-if analysis** | Non-persistent forecast of projected completion | No simulation tool in the seat's MCP catalogue | **Platform capability missing** |
| **Replanning** | Whole-location replan that reports newly late jobs | No capacity-based replan. Submitted orders are date-locked, and only an admin can cancel to re-plan | **Platform capability missing** |
| **Shared-material allocation** | Shortfall calculated across active jobs in priority order | Stock is checked one order at a time; stock ledgers are outside the Production seat | **Agent partly**; seat limit plus scoped-service gap |
| **Order dependencies** | Predecessors within a job; knock-on lateness after a replan | No link between work orders; sub-assembly BOMs are flagged but not connected | **Agent partly**; platform link missing |

**Access bugs, now fixed.** Job cards, downtime entries and engineering change orders were refused to our seat when we measured, although the schema granted them. We filed bugs, and on 17 Sep the platform opened them. The agent now uses all three.

## 2. Which gaps an agent can close with the tools we already have

**Ours: orchestration over the current API**

- **Why it is late.** Join the work order with its job cards (the operation it is stuck at), recorded downtime, pending engineering changes, material requests, subcontract orders, inspections and stock check. The result is *candidate* causes, separating blockers with no known date (a subcontract never sent, an engineering change under review) from contributing ones.
- **What it blocks.** Follow the linked sales order to customer, date and value, on both books. Walk BOMs in reverse to find *potential* consuming orders, never presented as confirmed blocks.
- **Reschedule what it can.** Draft orders accept new dates (*observed*); submitted orders refuse them (*observed*); in-progress and stopped orders are *untested*. The agent re-reads before writing, changes only what the state allows, re-reads to confirm, and escalates the rest with the evidence gathered.

**Yours: platform work**

| Required capability | Why the agent cannot safely rebuild it | Classification |
|---|---|---|
| Capacity-aware projected dates | The schedule models neither calendars nor labour | Platform defect and model gap |
| What-if analysis and replanning | No tool previews a change without saving it; re-reading records cannot reproduce a scheduler | Platform capability missing |
| Re-dating submitted orders | Dates lock after submit; only an admin can cancel | Platform capability missing |
| Cross-order dependency (pegging) | A BOM match shows possible demand, not a confirmed supply link | Platform link missing |
| Shared-material allocation | Stock ledgers are outside the Production seat | Seat limit plus scoped-service gap |
| Material receipt dates | Purchase orders are outside the Production seat | Seat limit; escalate to a person |
| Operator availability and contact | Employee records are outside the Production seat | Seat limit; escalate to a person |

## 3. What an agent can do that Carbon's product cannot

Carbon exposes MCP too, so we claim no exclusive capability. The advantage is **orchestration with evidence discipline**: one pass through the whole request, which Carbon's product leaves to a person.

- **Carbon splits capacity and material:** a shortage never appears as the scheduler's late cause, so an agent must join the two.
- **A Carbon date change does not replan itself:** a separate location-wide replan follows, so the result must be re-read, not assumed.

**Worked example: WO-2026-00048** (*observed*; stopped, 202 days past due on 16 Sep)

- **Rules out material:** its material request was received and stock is sufficient.
- **Finds the blocker:** subcontract orders SCO-2026-00030 and SCO-2026-00076 are still in draft, so the outside work was never sent.
- **States the exposure:** sales order SO-2026-00092, Kirloskar Pumps, INR 494,476.64, promised for 7 March 2026.
- **Decides what not to do:** it commits no date while the subcontract is unsent, and escalates the order to the person the platform names instead of leaving a note.

It works in a book other teams are changing: it re-reads before acting, and if an order changes between its proposal and its write, it keeps the other edit, stops writing and escalates. On Keystone it reads currency (USD), sales orders and tools from the platform. Where no escalation assignee exists, it says so rather than claiming a handover.

*Carbon source review: Pravin Gadekar. AgentSwitch observations: Team 04.*
