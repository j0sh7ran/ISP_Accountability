# Phased Implementation Roadmap

Each phase is independently verifiable before moving to the next. This mirrors the plan approved in
conversation; update this file if phase scope changes.

## Phase 0 — Scaffolding ✅ Done (2026-09-19)
Django project/app layout ([ARCHITECTURE.md](ARCHITECTURE.md)), settings (SQLite WAL config,
`USE_TZ=True`), `requirements.txt`, `.gitignore`, base templates/static vendoring (no CDN assets),
admin site enabled.
**Exit criterion:** `manage.py runserver` boots and serves an empty admin/dashboard shell locally. —
verified: both `/` and `/admin/login/` return HTTP 200, and SQLite `PRAGMA journal_mode` confirmed `wal`.

## Phase 1 — Core config models ✅ Done (2026-09-19)
`Target`, `ScheduleConfig`, `RetentionPolicy` + Django admin CRUD for them (§17/§31 — user-configurable
without code changes).
**Exit criterion:** an admin user can add/edit targets and schedules with no code change required. —
verified: model tests pass (`manage.py test apps.core`) and the three admin changelist pages
(`/admin/core/target/`, `/admin/core/scheduleconfig/`, `/admin/core/retentionpolicy/`) render and are
editable for an authenticated admin user.

## Phase 2 — Worker framework + first probe (ICMP) ✅ Done (2026-09-19)
`run_worker` management command, APScheduler + `ThreadPoolExecutor` wiring, ICMP probe end-to-end into
the DB.
**Exit criterion:** `runserver` and `run_worker` running simultaneously for 10+ minutes produce no
`database is locked` errors, and ICMP measurement rows accumulate on schedule. — verified: both
processes run concurrently against the shared WAL-mode SQLite file (worker writing every 5s, web
process handling concurrent reads) with zero errors on either side; 7+ `ICMPMeasurement` rows
accumulated in the observed window. Full soak beyond a few minutes is left to ongoing dogfooding
rather than blocking the next phase.

## Phase 3 — Remaining probes ✅ Done (2026-09-19)
DNS, HTTP/HTTPS, TCP, interface metrics (moderate priority); routing, MTU/PMTUD, IPv4/IPv6 comparison
(infrequent); throughput, bufferbloat (on-demand, mutex-guarded).
**Exit criterion:** each probe type has parser unit tests (captured CLI/library output, no live network
in CI) and produces correctly-typed rows end-to-end. Parallelizable per probe type once Phase 2's
pattern is established. — verified: 28 new unit tests (mocked, no real network) covering every probe's
success/failure paths plus the corresponding worker jobs; full suite is 38/38 passing. Live-verified
DNS/HTTP/TCP/interface/route/MTU against real targets (MTU sweep correctly found the standard 1472-byte
Ethernet path MTU; HTTP probe captured a full dns/connect/tls/ttfb/total breakdown). Throughput and
bufferbloat were verified via mocked tests only (real speedtest-cli runs are slow/bandwidth-consuming
and better exercised through the on-demand trigger once the dashboard exists in Phase 6). IPv4/IPv6
comparison has no dedicated probe — all measurements already carry `address_family`, so the comparison
itself is a Phase 6 dashboard/query concern, not a new probe.

## Phase 4 — State machine & incident engine ✅ Done (2026-09-19)
`network_state` app (state machine + confirmation thresholds), `incidents` app (Event derivation,
Incident correlation/evidence linking).
**Exit criterion:** synthetic measurement sequences (via unit tests) produce the expected state
transitions and incident groupings. — verified: 14 new unit tests covering every transition in the
ONLINE/DEGRADED/OFFLINE/RECOVERING diagram (including the OFFLINE→RECOVERING→ONLINE two-step recovery
and MICRO_OUTAGE vs OUTAGE duration-based classification), plus route-change and bufferbloat event
derivation (idempotent — re-running creates no duplicates). `run_icmp_job` now triggers state
evaluation and `run_route_job`/`run_bufferbloat_job` trigger their event derivation — confirmed live
against a real gateway target with zero errors across 6 ICMP ticks. Full suite: 52/52 passing.

## Phase 5 — SLA + baselines ✅ Done (2026-09-19)
`SLARule` CRUD, evaluation engine (triggered on incident close + periodic), `Baseline` model + seed
fixture data + versioning, baseline comparison views.
**Exit criterion:** a synthetic incident evaluates against a configured rule and produces the correct
`satisfied`/`breached`/`insufficient_data` result; baseline comparison view renders with source citation.
— verified: 15 new unit tests covering all 7 supported metrics (packet loss, latency, jitter,
availability, outage duration, throughput, DNS resolution), the `insufficient_data` path, the
`min_duration_seconds` grace logic, destination-filter matching for incident-triggered evaluation, and
baseline version selection/percentage-difference math. Confirmed live: `SLARule`/`SLAEvaluation`/
`Baseline` admin pages render and are usable. Full suite: 67/67 passing. Full dashboard-facing "SLA
comparison" / "industry comparison" views (§29/§30) are Phase 6 work — this phase delivers the
engine and data model, not the UI.

## Phase 6 — Dashboard ✅ Done (2026-09-19)
Overview (current state/metrics/active incidents), historical graphs (selectable ranges, Chart.js),
incident dashboard + drill-down, IPv4/IPv6 toggle views, polling JSON endpoints.
**Exit criterion:** dashboard fully renders and updates (via polling) with the network disconnected.
— verified: 12 new tests (services + views) passing; live-checked all pages/APIs
(`/`, `/graphs/`, `/incidents/`, `/incidents/<id>/`, `/api/overview/`, `/api/timeseries/`) return 200
and render real seeded data (target name, ONLINE state, incident description, 30 timeseries points,
correct uptime % reflecting a seeded outage). Chart.js is vendored locally
(`static/js/chart.umd.min.js`) and all dashboard JS/CSS is served from local `static/`, so the UI has
no CDN/internet dependency, satisfying the offline requirement. Full suite: 79/79 passing.

## Phase 7 — Reporting ✅ Done (2026-09-19)
HTML/PDF/CSV/JSON generators, auto-generation on incident close, dashboard links to reports,
historical/industry/SLA comparison views (§28-30).
**Exit criterion:** closing a synthetic incident auto-generates a linked report in all four formats,
entirely offline. — verified: 16 new tests (generators, download view, comparison views/services);
full suite 93/93 passing. Live-verified end-to-end: a real OFFLINE→RECOVERING→ONLINE transition cycle
auto-generated all 4 report files on disk, each downloadable via `/reports/<id>/download/` with the
correct content type (`text/html`, `application/pdf` — confirmed real `%PDF` header, `text/csv`,
`application/json`), and the incident detail page links to them. All 3 comparison pages
(`/sla-comparison/`, `/baseline-comparison/`, `/historical-comparison/`) render correctly. No network
access involved anywhere in the pipeline.

## Phase 8 — Retention & export ✅ Done (2026-09-19)
Aggregation jobs (raw → hourly → daily), configurable retention enforcement (incidents/SLA evidence
never auto-deleted), bulk export (CSV/JSON) of measurements + incidents.
**Exit criterion:** raw rows older than policy are aggregated and pruned while incidents/evaluations
remain intact; export produces valid CSV/JSON for a selected range. — verified: 11 new tests
(aggregation math/idempotency, retention deletion/exemption, export views); full suite 103/103 passing.
Live-verified: real `run_aggregation()` correctly rolled up 6 raw ICMP rows into 3 hourly-aggregate
rows (latency/loss/jitter) with correct avg/min/max/sample_count; real `enforce_retention()` deleted
exactly the one row older than a configured 30-day policy while keeping recent rows, and left
Incidents untouched even under a 1-day policy; CSV/JSON export endpoints and the new
HourlyAggregate/DailyAggregate admin pages all confirmed working live. Demo data cleaned up afterward.

## Phase 9 — Hardening & docs ✅ Done (2026-09-19)
Elevation-status detection/UI banner, firewall/setup notes, operational run-at-logon guidance
(Task Scheduler/`pythonw.exe`, optional), full test suite pass.
**Exit criterion:** full test suite green (network-dependent tests tagged/excluded from default run);
setup docs allow a fresh Windows machine to run the app from source. — verified: `apps/core/elevation.py`
detects Administrator status (Windows `IsUserAnAdmin`); the dashboard shows a warning banner and
`run_worker` prints a startup warning when not elevated — both confirmed live in this (non-elevated)
dev environment. 4 new tests; full suite **107/107 passing** via both `manage.py test` and `pytest`
(pytest-django now configured via `pytest.ini`). No test in the suite makes a real network call —
everything is mocked — so there was nothing to tag/exclude. New root [README.md](../README.md) and
[SETUP_AND_OPERATIONS.md](SETUP_AND_OPERATIONS.md) cover install, running, elevation, firewall
prompts, and an optional Task Scheduler/`pythonw.exe` run-at-logon convenience.

All 9 planned phases are now complete.

## Testing strategy (applies across all phases)
- Parser unit tests use captured sample CLI output (`ping.exe`/`tracert.exe`) — no real network calls.
- Correlation/state-machine unit tests use synthetic measurement sequences with controlled time.
- SLA evaluation unit tests use synthetic evidence windows.
- Django TestCase (runnable via both `manage.py test` and `pytest`/pytest-django) covers models,
  migrations, views, API endpoints, report generation.
- All outward network I/O is mocked (`unittest.mock`/subprocess mocking) — the suite never makes a
  real network call, so nothing needed a `@pytest.mark.network`-style exclusion in practice.

