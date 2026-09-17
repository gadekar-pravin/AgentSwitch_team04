# Gap Report — Production Seat (Team 04)

**Team:** Ramesh, Nishanth, Pravin Gadekar  **Measured:** 16–17 September 2026, Suryodaya (India) and Keystone (US)
**Request:** *"This work order is late. Find out why, tell me what it blocks downstream, and reschedule what you can."*
**Evidence labels:** *documented* = Carbon's docs or public source · *observed* = seen live in AgentSwitch · *untested* = not safely exercised

## Why Carbon

[Carbon](https://carbon.ms) is an AI-native, open-source manufacturing system: ERP, MES and quality on one data model. It ships an **MCP server**, so an agent can drive its production data the way ours must, which makes the bar public. We reviewed its scheduling and MCP documentation and public source (*documented*, not run in a trial). Tulip's Production Dispatcher agent was a secondary reference for dispatching.

## What we have

Work orders with a six-state workflow, plus BOMs, routings, operations, workstations, changeover times, production plans, material requests, subcontract orders, quality inspections, batches and serial numbers. There is also a finite-schedule endpoint and a stock-availability check.

## 1. What Carbon does that we do not

| Capability | Carbon (*documented*) | AgentSwitch today (*observed*) |
|---|---|---|
| **Capacity-aware scheduling** | Places operations within work-centre hours, subtracts maintenance downtime, reserves qualified operators | The schedule projects open orders to finish today. It models neither work calendars nor labour, and downtime does not reduce capacity |
| **Specific delay reasons** | Operation-level reasons: waiting behind a named job, a work centre, or an operator | 50 of 51 late Suryodaya orders (17 Sep) get the same generic cause, which restates that the due date passed |
| **What-if and replanning** | Non-persistent completion forecast; whole-location replan that reports newly late jobs | No simulation or capacity-based replan. Submitted orders are date-locked, and only an admin can cancel to re-plan |
| **Shared-material allocation** | Shortfall calculated across active jobs in priority order | Stock is checked one order at a time; stock ledgers are outside the Production seat |
| **Order dependencies** | Predecessors within a job; knock-on lateness after a replan | No link between work orders; sub-assembly BOMs are flagged but not connected |

**Access bugs, not missing features.** Job cards, downtime entries and engineering change orders exist and are granted to our role in the schema, but the seat is refused, so we filed them as bugs. On Keystone the seat has no sales-order tools, because it lacks the `viewer` role that Suryodaya's seat has.

## 2. Which gaps an agent can close with the tools we already have

**Ours: orchestration over the current API**

- **Why it is late.** Join the work order with its material requests, subcontract orders, inspections, stock check and workstation status. The result is *candidate* causes, separating blockers with no known date (a subcontract never sent) from contributing ones.
- **What it blocks.** Follow the linked sales order to customer, date and value (Suryodaya). Walk BOMs in reverse to find *potential* consuming orders, never presented as confirmed blocks.
- **Reschedule what it can.** Draft orders accept new dates (*observed*); submitted orders refuse them (*observed*); in-progress and stopped orders are *untested*. The agent re-reads before writing, changes only what the state allows, re-reads to confirm, and escalates the rest with the evidence gathered.

**Yours: platform work**

Capacity-aware dates (calendars, labour, downtime) · what-if simulation and replanning · an amend transition for submitted orders · work-order pegging · a Production-scoped view of shared stock · fixing access to job cards, downtime and engineering changes · sales orders on Keystone.

## 3. What an agent can do that Carbon's product cannot

Carbon exposes MCP too, so we do not claim a capability no Carbon-connected agent could have. The advantage is **orchestration with evidence discipline**: finishing the whole request in one pass that Carbon's product leaves to a person.

- **Carbon splits capacity and material.** Its scheduler gates on capacity, while shortage lives in a separate service, so a shortage never appears as the late cause. An agent must join the two.
- **A Carbon date change does not replan itself.** A separate replan call follows, covering every job at the location, so the result must be re-read, not assumed from the write.

**Worked example: WO-2026-00048** (*observed*; stopped, 202 days past due on 16 Sep)

- **Rules out material:** its material request was received and stock is sufficient.
- **Finds the blocker:** subcontract orders SCO-2026-00030 and SCO-2026-00076 are still in draft, so the outside work was never sent.
- **States the exposure:** sales order SO-2026-00092, Kirloskar Pumps, INR 494,476.64, promised for 7 March 2026.
- **Decides what not to do:** it commits no date while the subcontract is unsent, says who must act, and names what the seat cannot see (job cards, downtime).

All of this happens in a book other teams are changing: the agent re-reads before acting and never overwrites a row that moved. On Keystone it reads currency (USD) and available tools from the platform, and reports customer impact as unknown instead of inventing a customer.

*Carbon source review: Pravin Gadekar. AgentSwitch observations: Team 04.*
