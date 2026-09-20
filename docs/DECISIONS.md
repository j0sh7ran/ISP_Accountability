# Architectural Decisions Log

Running log of decisions made and open risks. Append new entries; do not delete history — if a
decision is later reversed, add a new dated entry explaining the change rather than editing the old one.

## 2026-09-19 — Initial architecture decisions

| Decision | Choice | Rationale / notes |
|---|---|---|
| Worker process model | Standalone process, started manually (`manage.py run_worker`) | Simplest to build/debug; requirement only needs the engine decoupled from the web request cycle, not necessarily an OS service. Trade-off: closing the console stops monitoring — mitigated with operational guidance (Task Scheduler/`pythonw.exe`), not code. |
| ICMP mechanism | Raw sockets (icmplib/pythonping) | More precise timing/control than shelling to `ping.exe`; user accepted the admin/elevation requirement. |
| Traceroute mechanism | Shell out to `tracert.exe`, parse text | No admin rights or Npcap driver needed; simpler than scapy despite admin being acceptable elsewhere. |
| MTU/PMTUD mechanism | `ping.exe -f -l <size>` sweep | Avoids raw packet crafting (scapy) entirely; Windows `ping.exe` natively supports DF-bit + size control, sufficient for PMTUD-style testing. |
| Throughput source | speedtest-cli / Ookla public servers | Easiest to implement; accepted dependency on third-party test infrastructure availability/rate-limits. |
| PDF generation | xhtml2pdf/reportlab (pure Python) | Avoids installing native GTK3 libraries on Windows (WeasyPrint's dependency), keeping the app portable/offline-friendly. |
| Admin/elevation | Acceptable for full feature set | Chosen over crippling ICMP/interface-stat fidelity; dashboard must surface elevation status so degraded mode is understood. |
| Dashboard live updates | JS polling (5-15s) against small JSON endpoints | Avoids Django Channels/ASGI/websocket complexity for v1; revisit if near-real-time push becomes a hard requirement. |
| Distribution | Run from source (venv + `manage.py`), optional `.bat` launcher | Matches "portable" via a self-contained project folder; no PyInstaller packaging phase for v1. |
| Database | SQLite, WAL mode, two-process access (web + worker) | Meets "portable local database" requirement; schema kept PostgreSQL-migration-friendly (see [DATA_MODEL.md](DATA_MODEL.md)). |
| Evidence linkage | `EVENT_EVIDENCE(measurement_type, measurement_id)` instead of Django `GenericForeignKey` | Simpler, indexable, and avoids a `contenttypes` dependency; portable to PostgreSQL. |

## 2026-09-19 — Phase 0 scaffolding notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Runtime versions | Python 3.14.4, Django 6.1.1 | Original plan assumed Python 3.12/Django 5.x (LTS-track); installed latest available on the dev machine instead since both install and `manage.py check`/`migrate`/`runserver` work cleanly. Revisit only if a dependency (e.g. icmplib, xhtml2pdf) proves incompatible. |
| App layout | All Django apps live under an `apps/` package (`apps.core`, `apps.measurements`, etc.), including a `apps.worker` app that holds only the `run_worker` management command (no models) | Management commands must live inside an installed app; `apps.worker` exists solely as a host for the worker command, matching the `worker/` package described in ARCHITECTURE.md. |
| WAL pragma wiring | `connection_created` signal registered in `apps.core.signals`, connected from `CoreConfig.ready()` | Keeps the SQLite WAL/synchronous pragmas applied for every connection (web or worker process) without per-call boilerplate. |

## 2026-09-19 — Phase 1 core models notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Shared category enum | `MeasurementCategory` (icmp/dns/http/tcp/route/mtu/throughput/bufferbloat/interface) used for both `ScheduleConfig.task_type` and `RetentionPolicy.data_type` | Avoids two near-identical enums; every probe category needs exactly one schedule and one retention policy. |
| Seed data | A data migration (`core.0002_seed_defaults`) seeds one `ScheduleConfig` row per category using the interval suggestions from docs/WORKER_AND_SCHEDULING.md, and one `RetentionPolicy` row per category defaulting to indefinite retention | Matches §17 (schedules must be DB-configured, not hard-coded) and §31 (never delete data without explicit configuration) while giving the worker sensible defaults to run against in Phase 2. `throughput`/`bufferbloat` seeded `enabled=False` per §9 (bandwidth-intensive tests default off). |
| `Target` seeding | None — left empty | Gateway/ISP-hop/DNS/HTTP targets are inherently user- and network-specific; no safe default to seed. |

## 2026-09-19 — Phase 2 worker framework notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Scheduler flavor | APScheduler `BlockingScheduler` (not `BackgroundScheduler`) inside `run_worker` | The management command's only job is to run the scheduler, so blocking the main thread is simpler than a manual sleep loop; `ThreadPoolExecutor` still runs probe jobs concurrently. |
| Job/command separation | Job functions live in `apps/worker/jobs.py`; `run_worker.py` only wires ScheduleConfig rows to APScheduler | Lets job logic be unit tested directly (`manage.py test apps.worker`) without going through the CLI/scheduler. |
| `ICMPMeasurement.timestamp` | Explicit field set by the job to `timezone.now()`, not `auto_now_add` | Keeps the semantic meaning ("when this probe batch ran") explicit and consistent with how later probe types will need to set it themselves (e.g. batch start time). |
| Measurement admin | `ICMPMeasurement` registered read-only (no add/change permission) | It's collected data, not hand-authored configuration — matches the `Target`/`ScheduleConfig` (editable) vs. measurement (read-only) distinction implied by the requirements. |
| Probe error handling | `run_icmp_probe` catches `ICMPLibError` (covers permission/timeout/name-lookup failures) and returns an error-flagged result row instead of raising | Confirmed live: this dev environment's terminal actually has ICMP raw-socket permission (0% loss observed), but the error path is unit-tested separately so degraded/non-elevated environments still record data instead of crashing the worker. |

## 2026-09-19 — Phase 3 remaining probes notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| HTTP timing breakdown | DNS/connect/TLS timed via raw `socket`/`ssl` on a throwaway connection; actual HTTP semantics (status/redirects/ttfb/total) via `requests` | `requests` doesn't expose per-phase timing; splitting the concerns keeps both halves simple and independently mockable in tests. |
| DNS query name | Hard-coded `DEFAULT_DNS_QUERY_NAME = 'www.example.com'` in `apps/worker/jobs.py`, not yet per-target configurable | Keeps Phase 3 scoped; revisit if per-resolver custom query names are needed — would need a new field on `Target` or a small config model. |
| Route/MTU target scope | Only run against `Target`s categorized `gateway`/`isp_hop`/`internet`, not every DNS/HTTP target | Matches the requirement's intent (representative upstream path), avoids redundant traceroutes/MTU sweeps per DNS resolver or HTTP endpoint. |
| MTU/PMTUD search | Binary search of DF-set `ping.exe -l <size>` between 1200–1500 bytes | Confirmed live: correctly found the standard 1472-byte Ethernet path MTU boundary on this dev machine. |
| Bandwidth-test mutex | A single `threading.Lock` (`BANDWIDTH_TEST_LOCK`) shared by `run_throughput_job`/`run_bufferbloat_job`, non-blocking acquire (skip the tick if busy) | Matches §9/§11 — these two tests must never run concurrently; simplest possible mechanism given both jobs run in the same worker process. |
| On-demand trigger | New `OnDemandTestRequest` model in `apps.core` (task_type/status/timestamps); throughput/bufferbloat jobs *always* get scheduled (default 30s poll) regardless of their `ScheduleConfig.enabled` flag, but only actually run the expensive test if a pending request exists or the schedule was explicitly enabled | Satisfies §17's "worker polls for on-demand requests" while keeping §9's "off by default" behavior — the poll is cheap (a couple of DB lookups), the actual test is not. |
| Bufferbloat concurrency | `ThreadPoolExecutor(max_workers=1)` runs the throughput probe while the main thread runs the "loaded" ICMP probe concurrently | Simplest way to get a genuinely concurrent load without a bigger async rewrite; baseline and recovery probes remain sequential before/after. |
| Throughput sub-metrics | `avg_mbps`/`peak_mbps`/`min_mbps`/`variance` left unset (speedtest-cli only reports one aggregate number per direction) | Documented as a best-effort limitation; would need a different throughput backend (e.g. multiple short samples) to populate these meaningfully. |

## 2026-09-19 — Phase 4 state machine & incident engine notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Confirmation thresholds | New `StateMachineConfig` singleton model (admin-editable: consecutive failures for degraded/offline, min independent targets, recovery confirmation successes, micro-outage threshold) | Requirements §19 explicitly calls for configurable thresholds; reuses the same admin-editable-singleton pattern precedent could later extend to other config. |
| State evaluation trigger | `evaluate_and_log_state()` called at the end of `run_icmp_job`, not on a separate timer | Connectivity state is entirely ICMP-derived for now, so evaluating right after new ICMP data lands is simpler than adding new scheduling infrastructure for a derived computation. |
| Confirming targets | Only `gateway`/`isp_hop`/`internet` category Targets feed the state machine | Matches §21's distinction between local-gateway/ISP/Internet-path evidence; DNS/HTTP/TCP targets don't participate in connectivity state directly. |
| DEGRADED → Incident | Not yet implemented — only OFFLINE transitions open/close an `Incident` | Keeps Phase 4 focused on the most clearly specified flow (§18 offline detection → incident/report). `NetworkStateLog` still records DEGRADED transitions for evidence; wiring a DEGRADED incident is a documented future extension. |
| MICRO_OUTAGE vs OUTAGE | Reclassified at incident-close time based on `duration_seconds < micro_outage_threshold_seconds` (default 60s) | Simplest way to apply the distinction without needing to know the outcome up front when the incident opens. |
| Event derivation scope | Only `OUTAGE`/`MICRO_OUTAGE` (state-machine-driven, full open/close lifecycle) and `ROUTE_CHANGE`/`BUFFERBLOAT` (standalone point-in-time Events, `incident=None`) are derived so far | `EventType` already defines all §20 types (`PACKET_LOSS`, `LATENCY_DEGRADATION`, `DNS_FAILURE`, etc.) for future use, but deriving each from its own measurement stream is left as a follow-up — the reusable pattern (check `EventEvidence` for already-processed rows, create `Event`/`EventEvidence`) is established by `derive_route_change_events`/`derive_bufferbloat_events`. |
| Correlation into Incidents | Route-change/bufferbloat Events are **not** wrapped in an Incident | An `Incident` is a duration-based grouping; a single instantaneous detection doesn't yet warrant one. Correlating these with concurrent OUTAGE/DEGRADED evidence (§21) is a documented future extension, not implemented in Phase 4. |
| `Incident.report` FK | Deferred | `apps.reports.Report` doesn't exist until Phase 7; the FK will be added via a migration then rather than pointing at a placeholder model now. |

## 2026-09-19 — Phase 5 SLA + baselines notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Supported SLA metrics | `packet_loss_pct`, `latency_ms`, `jitter_ms`, `availability_pct`, `outage_duration_s`, `throughput_mbps`, `dns_resolution_ms` (a fixed `SLAMetric` enum + `METRIC_COMPUTERS` dict in `apps/sla/engine.py`) | Covers every example metric named in §22; adding a new metric later is a one-function addition to the dict, not a schema change. |
| `min_duration_seconds` enforcement | Only applied when the evaluation is triggered *for a specific incident* (compares `incident.duration_seconds`); periodic/window evaluations skip this check | True "sustained breach for at least N seconds" would require scanning raw time series for contiguous excursions, which is a bigger feature. Incidents already carry a real `duration_seconds`, so this is where the check is meaningful today; documented as a simplification, not a full implementation of §22's duration semantics for continuously-sampled metrics. |
| Destination filtering | Simple case-insensitive substring match against `Target.name`/`Target.address` (for measurement queries) or `Incident.affected_destinations` (for incident-triggered rule matching) | Keeps rule authoring simple (type part of a target's name/address) without needing a many-to-many rule→target picker UI yet. |
| SLA trigger wiring | `evaluate_rules_for_incident()` called directly from `apps.incidents.derivation._close_outage_incident()`; `evaluate_periodic_rules()` runs on its own fixed 24h APScheduler interval (not via `ScheduleConfig`) | Incident-close is a natural, already-existing hook; periodic window-based rules (e.g. monthly availability) aren't tied to any probe category, so a `ScheduleConfig`/`MeasurementCategory` entry would be a poor fit. |
| Baseline seed data | One placeholder `latency_ms` row seeded via data migration, `source` explicitly labeled `"Example placeholder — not a verified source"` | The assistant should not fabricate real-looking industry statistics presented as fact. This seed only proves the comparison feature works end-to-end; real baselines must be entered by the user with a genuine citation before being relied upon. |
| `Incident.sla_evaluations` | Reverse relation from `SLAEvaluation.incident` FK (`related_name='sla_evaluations'`) | Lets the future incident-detail dashboard view list SLA results for that incident directly. |

## 2026-09-19 — Phase 6 dashboard notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| API layer | Plain Django views returning `JsonResponse` (`/api/overview/`, `/api/timeseries/`) — no Django REST Framework | Two simple read-only JSON endpoints don't justify a new dependency; matches ARCHITECTURE.md's "REST/API layer if useful", not a requirement. |
| IPv4/IPv6 toggle | A `?family=ipv4\|ipv6` query parameter applied to the overview/graphs views, rather than separate pages | Simpler to implement/maintain than duplicate templates; combined view is just the default (no `family` param). |
| Chart.js vendoring | Downloaded the official `chart.js@4` UMD build directly to `static/js/chart.umd.min.js` via a terminal request to a well-known CDN URL, committed as a vendored static asset | One-time fetch of a legitimate, well-known open-source library for local/offline use — matches the architecture decision (§ARCHITECTURE.md) to avoid CDN references at runtime; the file itself is now served locally with no further internet dependency. |
| Historical graphs | Chart.js line charts for `latency_ms`/`packet_loss_pct`/`jitter_ms`/`dns_resolution_ms` only; throughput/route-changes/incident-period shading not yet charted | Keeps Phase 6 scoped to the metrics with a simple raw-timeseries endpoint; throughput has too few on-demand samples to chart meaningfully yet, and incident-period shading needs a charting annotation plugin not yet vendored — documented as a future enhancement. |
| Incident drill-down | Shows nearby (±10 min) raw `ICMPMeasurement` rows and `NetworkStateLog` transitions inline on the incident detail page | Directly satisfies §25's "drill down into the raw measurements surrounding the event" for the connectivity signal; other measurement types can be added the same way later if needed. |
| Polling interval | 10s, hard-coded in `static/js/dashboard.js` | Matches the range suggested in ARCHITECTURE.md/WORKER_AND_SCHEDULING.md ("every 5-15s"); not yet DB-configurable since it's a UI concern, not a probe schedule. |

## 2026-09-19 — Phase 7 reporting notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| `Report` ↔ `Incident` relationship | `Report.incident` FK (`related_name='reports'`), i.e. many reports per incident | One incident naturally produces 4 report rows (one per format generated together); a single `Incident.report` FK as originally sketched in DATA_MODEL.md would only fit one format at a time. |
| Storage | Report *metadata* in the `Report` table; rendered content written to files under `MEDIA_ROOT/reports/`, referenced by `file_path` | Matches §4's "avoid storing large binary data directly in normal tables"; `MEDIA_ROOT`/`MEDIA_URL` added to settings for this purpose only (no external storage backend — stays fully local/offline). |
| HTML/PDF share one template | `templates/reports/outage_report.html` rendered once for HTML, and piped through `xhtml2pdf.pisa.CreatePDF` for PDF | Guarantees the two human-readable formats can never drift out of sync with each other. |
| CSV/JSON scope | Serialize the same `build_outage_report_context()` (summary, before/during/after ICMP evidence, SLA evaluations) as the HTML/PDF report — this is a per-incident report, not a bulk data dump | Bulk export of arbitrary historical measurements/incidents (governed by retention policy) remains Phase 8's distinct scope, per docs/REPORTING_AND_RETENTION.md's Report-vs-Export distinction. |
| Comparison views location | `sla_comparison`/`baseline_comparison`/`historical_comparison` added to `apps.dashboard` (views/services/templates), not `apps.reports` | These are live dashboard pages (query current DB state on every request), not generated/downloadable documents — consistent with the `dashboard` vs `reports` app boundary already established. |
| Report auto-generation trigger | All 4 formats generated together in `_close_outage_incident`, immediately after SLA evaluation | Matches §18/§26 ("generate an outage/incident report when connectivity goes offline" — interpreted as "when it's confirmed recovered and the full evidence window is known"). |

## 2026-09-19 — Phase 8 retention & export notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Aggregate scope | Only the 4 metrics already used elsewhere (`latency_ms`, `packet_loss_pct`, `jitter_ms`, `dns_resolution_ms`) are aggregated into `HourlyAggregate`/`DailyAggregate` | Keeps the aggregation engine consistent with the dashboard/SLA metric set; other measurement types (HTTP, TCP, throughput, interface, MTU, route) aren't yet aggregated — documented as a future extension using the same `METRIC_SOURCES` pattern. |
| Daily p95 | Approximated as the *average of the day's hourly p95 values*, not recomputed from raw data | True daily p95 would require re-scanning all raw rows for the day; this approximation is clearly weaker and documented as such — acceptable since raw data (while retained) can still be queried directly for exact figures. |
| Retention scope | `RAW_MODELS_BY_DATA_TYPE` covers all 9 raw measurement categories; `Incident`/`Event`/`SLAEvaluation`/`Report` are never included, so they're structurally exempt rather than specially guarded | Simpler than an explicit exemption list — exemption is just "this model was never in the deletion map". |
| Dangling evidence | Raw rows referenced by `EventEvidence` can still be pruned once their own retention window passes (the `Event`/`Incident` referencing them survives regardless) | The `Event.description` text is the durable human-readable record; documented as a known trade-off rather than adding complex evidence-aware retention exceptions. |
| Jobs scheduling | `run_aggregation_job` (hourly) and `run_retention_job` (daily) registered on their own fixed APScheduler intervals in `run_worker.py`, same pattern as the SLA periodic job | Neither is a probe category, so a `ScheduleConfig`/`MeasurementCategory` entry would be a poor fit — consistent with the Phase 5 precedent. |
| Export vs. Report | `apps/reports/exports.py` (bulk CSV/JSON dump for an arbitrary date range) is deliberately separate from `apps/reports/generators.py` (curated per-incident report documents) | Matches the Report-vs-Export distinction already documented in docs/REPORTING_AND_RETENTION.md; export endpoints live under the same `apps.reports` app since both produce downloadable files, but use different modules/views. |
| Known Django/SQL gotcha | Aggregation code explicitly calls `.order_by()` before `.distinct()` on `target_id` | Model `Meta.ordering` (e.g. `ICMPMeasurement`'s `-timestamp`) silently leaks into `SELECT DISTINCT` and breaks deduplication unless cleared first — caught by a failing test during this phase; now commented in the code as a trap for future contributors. |

## 2026-09-19 — Phase 9 hardening & docs notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Elevation detection | `ctypes.windll.shell32.IsUserAnAdmin()` in `apps/core/elevation.py`, returning `None` on non-Windows/errors rather than guessing | Matches the risk flagged back in the original plan (§ARCHITECTURE.md "Elevation / admin rights"); `None` is treated distinctly from `False` in the UI so we never claim "not elevated" when we simply don't know. |
| Banner placement | Dashboard overview template + `run_worker` startup message, both reading the same `is_elevated()` helper | Surfaces the same status wherever a user is likely looking (web UI or the worker's own console). |
| Firewall/setup docs | New root `README.md` (quickstart) + `docs/SETUP_AND_OPERATIONS.md` (elevation, firewall, optional Task Scheduler run-at-logon) | Fulfills the Phase 9 exit criterion that setup docs let a fresh machine run the app from source; kept operational detail out of `ARCHITECTURE.md` (design) to avoid mixing concerns. |
| pytest support | Added `pytest.ini` and installed `pytest`/`pytest-django`/`factory_boy`/`responses` (previously only listed in requirements.txt, not installed) | The test suite was written entirely with `django.test.TestCase` + `unittest.mock` and passed all along via `manage.py test`; adding pytest support makes the documented `pytest-django` dependency actually usable without changing a single test. |
| Network-tagged tests | None added — every test in the suite already mocks all outward network/subprocess calls | The Phase 9 exit criterion anticipated a `@pytest.mark.network` exclusion pattern, but since no test ever made a real network call across all 9 phases, there was nothing to tag or exclude. |

## 2026-09-20 — Dashboard UI refresh + live job status notes

| Decision | Choice | Rationale / notes |
|---|---|---|
| "What jobs are running" summary | New `apps/dashboard/services.job_status_summary()`, derived entirely from `ScheduleConfig` rows (enabled/interval/`last_run`) plus a recent-row count/error-count per category from `apps.measurements.retention.RAW_MODELS_BY_DATA_TYPE` | The web process and worker process only share the DB (no IPC/shared memory — see WORKER_AND_SCHEDULING.md), so job "liveness" has to be inferred from `ScheduleConfig.last_run` freshness rather than queried from a running scheduler object. A job is `overdue` once `last_run` is older than `2× interval + 30s` grace. |
| Near-real-time refresh | Reused the existing JS-polling pattern (no Channels/websockets, consistent with the original "Dashboard live updates" decision), shortened from 10s to 5s and extended to also refresh the new job-status grid and stat cards | Keeps the same non-blocking-JSON-endpoint architecture; 5s felt closer to "near real-time" without meaningfully increasing load for a single-user local app. |
| Visual refresh | Rewrote `static/css/base.css` with CSS custom properties (light theme + `prefers-color-scheme: dark` override), card/badge/stat-grid/job-grid components; restyled `base.html`'s header into a sticky topbar | Applied at the CSS/base-template layer so every existing page (graphs, incidents, SLA/baseline/historical comparisons) picks up the modern look via the same `section`/`table` element styling, without needing to rewrite each template's markup. |
| Admin theming | New `templates/admin/base_site.html` (extends `admin/base.html`, replicates the stock `title`/`branding`/`nav-global` blocks, adds an `extrastyle` link to `static/css/admin_theme.css`) + `admin.site.site_header/site_title/index_title` set in `isp_monitor/urls.py` | Django's admin CSS is entirely driven by CSS custom properties (`--primary`, `--header-bg`, etc. in `admin/css/base.css`), so re-theming means overriding those variables rather than fighting component CSS with `!important`; covers both the `light` and `data-theme="dark"` variants Django's admin already supports. Extending `admin/base.html` directly (not `admin/base_site.html`) was required — extending the same-named template from our own `templates/admin/base_site.html` would recurse onto itself since project `TEMPLATES.DIRS` is searched before app dirs. |

## 2026-09-20 — On-demand test request bug fixes

| Decision | Choice | Rationale / notes |
|---|---|---|
| Root cause #1: inert requests | `OnDemandTestRequestAdmin.formfield_for_choice_field` now restricts the `task_type` dropdown to `throughput`/`bufferbloat` only | The model's `task_type` field reused the full `MeasurementCategory` enum, so the admin let users create request rows for e.g. `icmp`/`dns`/`route` — but `apps/worker/jobs.py`'s `ON_DEMAND_TASK_TYPES` only ever polls for `throughput`/`bufferbloat` requests. Requests for any other category were silently inert (created, never read by any job, stuck at `pending` forever). This was reported as "on-demand jobs don't seem to be triggering." |
| Root cause #2: silent bufferbloat skip | `run_bufferbloat_job()` now marks a pending request `FAILED` (instead of just logging a warning and returning) when no enabled gateway `Target` exists | Previously a bufferbloat request with no gateway `Target` configured stayed at `pending` indefinitely with zero feedback in the admin/dashboard — indistinguishable from "not picked up yet" vs. "can't run, fix your config." `throughput` needs no `Target` so isn't affected the same way. |
| Existing worker process | Not automatically restarted by this fix | `run_worker` is a long-running script (`BlockingScheduler`), not autoreloading like `runserver` — code changes (including this fix, and any `ScheduleConfig`/interval edits for the always-registered-at-startup categories) only take effect after the process is manually stopped and restarted. Documented here since it's a recurring point of confusion. |

## 2026-09-20 — Real Target configuration + overview template crash fix

| Decision | Choice | Rationale / notes |
|---|---|---|
| Target set | 6 real `Target` rows added (gateway, ISP first hop, internet endpoint, DNS resolver, HTTP endpoint, TCP endpoint) using the host's actual default gateway/traceroute-derived first hop plus Cloudflare (`1.1.1.1`) as the public reference | Gives every probe category real data to collect; the dev machine had two active default gateways (a 10.x and a 172.16.x adapter) — `Get-NetRoute`/`tracert` confirmed only the 172.16.x (Wi-Fi) adapter actually reaches the public internet, so that one was used, not the first one `ipconfig` happened to list. |
| Overview template crash | Fixed `templates/dashboard/overview.html`'s HTTP row: `{{ row.measurement.status_code\|default:row.measurement.error_type\|default:"—" }}` raised an unhandled `VariableDoesNotExist` (500 error) whenever `row.measurement` was `None` (a freshly added HTTP target with no probe yet) — wrapped in `{% if row.measurement %}` instead | A `default` filter's *argument* expression (`row.measurement.error_type`) is resolved eagerly and does not get the same silent-failure handling Django gives a top-level `{{ variable }}` — attribute lookups on `None` there raise instead of failing quietly. This bug pre-dates today's session (Phase 6) but only manifests when an HTTP-category target exists with zero measurements yet; caught live while configuring real targets through the browser. Added a regression test (`test_overview_renders_with_http_target_and_no_measurements_yet`). |
| `pending_on_demand` accuracy | `job_status_summary()`'s pending-count query now filters `task_type__in=[THROUGHPUT, BUFFERBLOAT]` (previously counted *any* pending `OnDemandTestRequest`, including the now-impossible-to-create-but-still-existing inert rows from before the admin fix) | Otherwise the dashboard banner over-reported "N on-demand tests queued" using rows that will never be processed. Stray inert rows from before the admin fix were also deleted from the dev DB directly. |

## 2026-09-20 — Graphs time filters/hover + monthly report generation

| Decision | Choice | Rationale / notes |
|---|---|---|
| Custom time range | `resolve_range()` already supported `custom_start`/`custom_end`; wired a `?start=&end=` (ISO/`datetime-local`) pair through `graphs`/`api_timeseries` views alongside the existing preset range links, styled as a button group + small form | Presets (`1h`/`6h`/.../`30d`) plus an explicit custom range covers "time filters" without a new dependency; `datetime-local` inputs are naive, so `_parse_custom_datetime()` calls `timezone.make_aware()` on them (assumes server-local time — this is a single-user local app, not multi-timezone). |
| X-axis + hover | `static/js/graphs.js` rewritten: `scales.x.display` turned back on with a tick `callback` that formats each ISO label (time-of-day for ≤24h ranges, month/day for 7d/30d) and `maxTicksLimit: 8`; `pointHoverRadius`/`pointHitRadius` added and `interaction: { mode: 'index', intersect: false }` set so hovering anywhere near the line shows a tooltip, not just exactly on a (invisible, `pointRadius: 0`) point | No `chartjs-adapter-date-fns`/moment dependency added — a plain category-scale tick-label formatter callback was enough, keeping the app's "fully offline, no new vendored deps unless needed" pattern. Live-verified via a real hover screenshot showing a full timestamp + value tooltip. |
| Monthly report content | Reuses `apps.dashboard.services.period_stats()` (same uptime/latency/loss/jitter/DNS/outage-count/route-change-count figures as the existing Historical Comparison page) plus the period's `Incident`/`SLAEvaluation` rows — not new aggregation logic | Avoids a second, parallel "what happened this month" computation that could drift from the dashboard's own historical-comparison numbers. |
| Monthly report plumbing | New `Report(type=PERIODIC, incident=None)` rows via `apps/reports/generators.py`'s `generate_monthly_report()`/`generate_periodic_reports()` (parallel to the existing per-incident outage-report functions; `_write_file()` generalized to take a filename prefix instead of an `incident`) + `templates/reports/periodic_report.html` (parallel to `outage_report.html`) | `Report.incident` was already nullable (Phase 7 decision), so no migration needed — a periodic report is just a `Report` row with no incident and a full-month `period_start`/`period_end`. |
| Monthly scheduling | `run_worker.py` registers `run_monthly_report_job` on `CronTrigger(day='last', hour=23, minute=55)` (APScheduler's `day='last'` field value), deliberately **without** `next_run_time=timezone.now()` unlike the other periodic jobs | Firing immediately on every worker startup (like the SLA/aggregation/retention jobs do) would generate a garbage "monthly" report covering whatever partial period happened to be live at that moment, every single restart — this job should only ever fire for real at actual month-end. |
| Reports discoverability | New `reports:list` view/URL (`/reports/`) + nav link, listing every `Report` row (outage + periodic) with a download link, since periodic reports have no `Incident` page to be listed from | Outage reports were only ever visible via `incident_detail.html`; periodic reports needed their own home. |


## Open risks / flagged items

1. **Two-process SQLite contention** — mitigated via WAL + busy_timeout; revisit if write contention is
   observed in practice (e.g. move to a single-writer pattern where only the worker writes, and the web
   process's config changes are queued for the worker to apply).
2. **Elevation requirement** — full ICMP/interface-stat fidelity needs admin; dashboard must detect and
   display elevation status (Phase 9).
3. **speedtest-cli dependency** — third-party infra could rate-limit or go away; schema (`endpoint`,
   `test_size_bytes`) is generic enough to swap providers later without a schema change.
4. **Interface link-speed/error counters** — `psutil` covers basic counters without admin; deeper
   WMI-based stats are best-effort only.
5. **Worker reliability** — manual-start process; a closed console silently stops monitoring. No code
   mitigation planned for v1; documented as an operational note only.
6. **Requirements.md truncation** — §32 ("Export") cuts off after "Allow exports". Current scope for
   export is inferred from §2/§27 (CSV/JSON/HTML/PDF export of measurements + incidents). Revisit if the
   user provides the intended remainder of that section.
7. **Windows Firewall prompts** — first run of outbound probes may trigger a firewall prompt; documented
   as a setup note (Phase 9), not handled in code.
