# Bugs filed by Team 04

All reports were filed through `POST /api/bug-report` as team04 (Production seat). Full reproduction steps are in each report (`GET /api/bug-report/mine`).

| # | Instance | Report id | Summary |
|---|---|---|---|
| B1 | Suryodaya (also Keystone) | f99d53d5-a527-4884-9d91-2407107f0b95 | JobCard and DowntimeEntry unreadable for `manufacturing_user`, although the schema grants read |
| B1a | Suryodaya (also Keystone) | 92bb5235-35ed-4ce2-bea2-52acc3b4fc08 | EngineeringChangeOrder unreadable too; same root cause as B1 |
| B2 | Suryodaya (also Keystone) | cda6df5e-d47e-4e5e-9d4f-55a7a88bf1da | `finite_schedule` returns JobCard ids that `JobCard.get` reports as not found |
| B2a | Suryodaya | 0c52d179-4916-4eda-864e-51ae842448a3 | `finite_schedule` exposes downtime and job-card data the entity tools refuse; follow-up to B2 and B4 |
| B3 | Suryodaya | 9dd39dd6-69b4-4683-ad62-5302273e6a5d | Admin-only transitions (e.g. WorkOrder cancel) listed in `tools/list` for `manufacturing_user` |
| B4 | Suryodaya | 293321e3-7f66-4d13-a645-872ba6cb7052 | `finite_schedule` never attributes downtime or blocking to late orders |
| B5 | Keystone | a45d393a-da35-46e5-b0a9-659f38e88141 | Workstation numbers contain the literal format token (`WS-.#####-2026-00001`) |
| B5a | Keystone | 32c5715c-4879-4bf1-b881-6ff65d5231c2 | Duplicate of B5; adds serial numbers with an empty `number` |
| B6 | Keystone | 4c26c220-0513-4423-8b5c-76eb28c5bbc6 | Cost Analysis page shows ₹ for a US company whose currency is USD |
| B9 | Suryodaya (also Keystone) | a77321bc-5a2d-4a3d-8106-3f05a7146afc | `check_stock_availability` returns "not found" inside a success response instead of an error |

Distinct defects: about 7 (B1a, B2a and B5a are follow-ups or duplicates).
