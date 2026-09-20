# SLA Engine & Industry Baselines

These are two deliberately separate systems, kept visually and semantically distinct in the UI
(§22/§23/§30) — one is the user's actual ISP contract terms, the other is generic industry reference
data with no contractual weight.

## SLA rule engine

`SLARule` fields: metric, operator, threshold, unit, minimum duration, measurement window, applicable
protocol/destination/time period, severity, enabled/disabled. Rules are entered by the user from their
actual ISP contract — **the application never ships hard-coded "real" SLA numbers**; any examples in
requirements/docs are illustrative only.

Evaluation triggers:
- **On incident close** — evaluate all enabled rules whose metric/protocol/destination filters match
  the incident's evidence, over the incident's time window.
- **Periodic** — rules like "availability < 99.9% monthly" need evaluation on a rolling/periodic basis
  independent of any single incident.

Each evaluation produces an `SLAEvaluation` row: observed value, threshold value, and a status of
`satisfied`, `breached`, or `insufficient_data` (used when there isn't enough evidence to conclude
either way — never silently assume compliance). The evidence supporting the observed value is stored as
JSON alongside the row.

## Industry baseline system

`Baseline` rows store: metric, value, unit, population/context, technology type, geographic scope,
source, source URL, publication date, methodology, notes, and a `version` number. Baselines are:

- Seeded once via a Django data migration/fixture (offline, no runtime fetch).
- Versioned so historical comparisons stay reproducible even after a baseline value is later updated
  (old reports reference the version they were generated against, not "whatever the baseline is today").
- Compared against measurements at query/report time by matching on `metric` — there is no FK from
  `Baseline` to measurement tables.

## UI separation

| | SLA Comparison | Baseline Comparison |
|---|---|---|
| Source of truth | User-entered ISP contract terms | Versioned reference data with cited source |
| Question answered | "Did my ISP violate the contract?" | "How does my connection compare to typical figures?" |
| Result semantics | `satisfied` / `breached` / `insufficient_data` | Descriptive difference only, no pass/fail |
| Table | `SLA_RULE` / `SLA_EVALUATION` | `BASELINE` |

The dashboard/report views must never blend these into a single score — each is shown with its own
observed value, its own reference value, and (for baselines) its source citation.
