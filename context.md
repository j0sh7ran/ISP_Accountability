# context.md

## Project context

I live in a multifamily apartment community (Bexley Arcadia in Fort Worth, Texas) where internet service is provided through Gigstreem as the property's managed/property-wide Wi-Fi provider. The property has an exclusive arrangement, so residents cannot simply choose a competing ISP.

I work remotely, and recurring network outages / severe degradation have materially interfered with normal internet use, especially Microsoft Teams calls. A particularly important symptom is **outbound voice loss**: during Teams calls, other participants sometimes report that my voice cuts out or becomes unintelligible. This happens frequently, including essentially daily in some periods.

The immediate goal is bigger than troubleshooting my apartment connection:

> Build a local application that continuously measures network availability/quality and determines when observed network failures could constitute an ISP/service-level/SLA breach, producing defensible evidence that can be used in a vendor/property-management escalation.

The application should be generic enough to work with different ISPs and SLA definitions rather than hard-coding Gigstreem/Bexley.

---

## What we know about the ISP/property situation

- Bexley Arcadia advertises "Property Wide Wi-Fi."
- Gigstreem is identified as the property's Wi-Fi provider.
- The property is managed by Weinstein Properties.
- Public apartment listings have advertised high-speed internet as a separate per-unit charge, but the exact lease/billing terms have not been independently verified.
- The actual Bexley Arcadia ↔ Gigstreem contract has not been found publicly.
- Therefore, **do not assume that Gigstreem's publicly advertised SLA is contractually applicable to Bexley Arcadia.**
- Gigstreem publicly advertises **99.99% "Proven Uptime"** for its connectivity services and has described 99.99% reliability as an SLA in public materials.
- The actual contractual SLA for this property must be treated as configurable/unknown until confirmed.

### Accountability chain

The practical escalation chain appears to be:

`Resident → Bexley onsite management → Weinstein/corporate/vendor management → Gigstreem`

Gigstreem support tickets are still valuable for evidence, but because residents are required to use the property's selected provider, Bexley/Weinstein has the stronger vendor-management relationship and leverage.

Texas landlord-tenant law should not be assumed to create a broadband-specific SLA remedy. Statutory utility-interruption protections primarily concern services such as water, wastewater, gas, and electricity. The application's purpose is therefore **evidence collection and contractual SLA analysis**, not automatic legal determination.

---

## SLA concepts the application needs to support

The application should NOT assume that an outage automatically equals an SLA breach.

An SLA breach generally depends on:

1. The contractual SLA.
2. The applicable measurement period.
3. The definition of uptime/downtime.
4. What constitutes a qualifying incident.
5. Exclusions.
6. Planned maintenance rules.
7. Maintenance windows.
8. Measurement point / service boundary.
9. Required response time.
10. Required restoration time.
11. Incident aggregation rules.
12. Service-credit/remedy rules.

The app should therefore have a configurable **SLA policy engine**.

### Example

If an SLA were actually 99.99% uptime:

- Annual allowable downtime is approximately 52 minutes 34 seconds.
- For a 30-day month, it is approximately 4 minutes 23 seconds.
- Daily equivalent is approximately 8.6 seconds.

But these figures are illustrative only. The application must calculate allowable downtime based on the user's configured SLA period and policy.

A single one-hour outage would exceed the annual downtime budget of a simple 99.99% SLA, but this does **not** by itself prove a contractual breach because exclusions and measurement definitions may apply.

---

## Evidence the app should collect

The application should collect continuous and event-based network evidence.

### Core measurements

At minimum:

- Timestamp
- Local timezone
- Internet reachability
- Packet loss
- Latency / RTT
- Jitter
- DNS resolution success/failure
- Connection state
- Interface used (Wi-Fi/Ethernet)
- Default gateway reachability
- External target reachability
- Outage start time
- Outage end time
- Duration
- Consecutive failure count
- Recovery timestamp

### Multiple measurement points

Ideally monitor at least:

1. **Local default gateway**
   - Helps identify Wi-Fi/LAN problems.
2. **ISP/property-network endpoint**, if discoverable/configurable.
3. **Reliable external endpoint(s)** such as Cloudflare/1.1.1.1.
4. **DNS endpoint(s)**.
5. Optionally multiple independent external endpoints.

This distinction is important.

For example:

- Gateway fails → likely local Wi-Fi/LAN/access-point issue.
- Gateway stable but external targets fail → stronger evidence of upstream/WAN/ISP/property network issue.
- One external target fails while others work → likely target/path-specific issue.
- Multiple independent external targets fail simultaneously → stronger evidence of general upstream connectivity loss.

Do not label these automatically as contractual breaches. Label them as **observed network events with probable scope**.

---

## Network measurement approach

The application should perform all primary measurements itself rather than relying on Teams or another application.

### Continuous ICMP measurement

A simple Windows test is:

```powershell
ping -t 1.1.1.1
```

This can show:

- `Request timed out`
- Latency spikes
- Repeated packet loss

However:

**ICMP ping is not proof of Teams UDP packet loss.**

Some networks deprioritize/block ICMP. It is supporting evidence only.

### Better test: two simultaneous paths

Run continuous tests against:

1. Default gateway
2. External endpoint such as 1.1.1.1

If the gateway remains stable while the external endpoint loses packets or experiences latency spikes, that is stronger evidence that the problem is beyond the local Wi-Fi segment.

If the gateway itself loses packets, investigate local Wi-Fi/router/access-point conditions first.

### Ethernet vs Wi-Fi

If possible, compare:

- Wi-Fi
- Direct Ethernet

If both experience the same failures while upstream targets fail, that strengthens the case for an upstream/property/WAN issue.

The app should record interface type so the evidence can be segmented.

---

## Outage/event logging

The application should maintain an immutable-ish event history.

For every suspected outage:

- Event ID
- Start timestamp
- End timestamp
- Duration
- Severity
- Detection source
- Targets affected
- Packet loss
- RTT
- Jitter
- DNS failures
- Gateway status
- Interface
- Wi-Fi SSID/BSSID if permitted
- Public IP if permitted
- ISP/property provider
- Planned/unplanned classification
- User-reported symptoms
- Work impact
- Screenshot/file attachments
- Support ticket number
- ISP response
- Root cause if later provided
- Whether SLA qualification is known/unknown
- Whether event is excluded
- Reason for exclusion
- SLA period affected
- Cumulative downtime
- Remaining downtime budget
- Potential breach status

---

## Critical distinction: observed failure vs SLA breach

The UI/data model should explicitly separate these states:

### Observed outage

The application detected connectivity failure.

Example:

`Internet unavailable for 7m 42s`

### Suspected ISP/property-network event

Evidence indicates the failure is probably upstream of the user's LAN.

Example:

`Gateway reachable; 3 independent Internet targets unreachable`

### Potential SLA event

The event meets configured technical criteria but contractual applicability is not confirmed.

Example:

`Potential qualifying outage: 7m 42s`

### Contractually qualifying SLA event

The user has configured/verified the applicable contract terms and the event meets them.

### Excluded event

The event falls under a documented SLA exclusion, such as:

- Planned maintenance
- Approved maintenance window
- Force majeure
- Customer equipment
- Customer LAN/Wi-Fi
- Third-party network
- Power outage
- Other contract-specific exclusions

### Confirmed breach

Only use this label when sufficient contractual information and evidence exist.

The app should avoid making legal conclusions. Prefer terminology such as:

- "Potential SLA breach"
- "SLA qualification pending"
- "Qualifying event based on configured policy"
- "Excluded under configured policy"
- "Contract terms not configured"

---

## Planned maintenance

The application should distinguish planned maintenance from unplanned incidents.

For planned maintenance, track:

- Announcement timestamp
- Scheduled start/end
- Actual start/end
- Maintenance window
- Notification lead time
- Scope
- Whether service was expected to be interrupted
- Whether interruption occurred inside the allowed maintenance window
- Whether SLA excludes it

Do not assume that daytime maintenance is automatically a breach or that maintenance must occur outside business hours. That depends on the actual contract.

---

## Gigstreem/Bexley escalation questions

The application should be able to generate a report containing questions such as:

1. What uptime/service-level commitment applies to Gigstreem service at Bexley Arcadia?
2. How are uptime and downtime defined and measured?
3. What are the response-time commitments?
4. What are the restoration-time commitments?
5. What constitutes an SLA event?
6. Are recent outages recorded as SLA incidents?
7. Has Bexley received or requested service credits/remedies?
8. What corrective action is Gigstreem taking?
9. Which incidents were planned maintenance?
10. Which were unplanned?
11. What maintenance window applies?
12. What underlying causes have been identified?
13. What steps are being taken to prevent recurrence?

The app should make it easy to export a professional evidence report for property management/vendor escalation.

---

## Desired application capabilities

Build a polished local-first application, ideally for Windows.

### Primary goals

- Run continuously in the background.
- Low CPU/RAM usage.
- Survive network interruptions.
- Automatically detect outages.
- Automatically detect degraded network quality.
- Correlate multiple measurements.
- Build outage timelines.
- Calculate SLA utilization.
- Flag potential SLA breaches.
- Generate evidence reports.
- Export CSV/JSON/PDF/HTML as appropriate.
- Allow manual event annotations.
- Allow SLA policies to be configured per ISP/service.
- Preserve raw measurement data so conclusions can be audited.

### Dashboard

Useful dashboard elements:

- Current connection status
- Current interface
- Current public IP
- Current latency
- Current packet loss
- Current jitter
- DNS status
- Gateway status
- ISP status
- Current outage duration
- Today's downtime
- Current SLA period
- SLA target
- Allowed downtime
- Observed qualifying downtime
- Remaining downtime budget
- Number of potential SLA events
- Number of excluded events
- Number of confirmed qualifying events
- Recent incidents timeline
- Work-impact events

Avoid showing a single "ISP reliability score" unless the score is explicitly requested and clearly defined. Raw metrics and transparent calculations are more useful for contractual evidence.

---

## SLA policy engine

Make SLA rules data-driven.

Example conceptual policy:

```yaml
name: "Example 99.99% Monthly Uptime"
measurement_period: monthly
availability_target: 99.99

measurement:
  start: first_day_of_period
  end: last_day_of_period

qualifying_event:
  requires:
    - upstream_failure
    - duration_greater_than: 60s

exclusions:
  - planned_maintenance
  - approved_maintenance_window
  - customer_lan
  - customer_power
  - force_majeure

maintenance:
  allowed_window:
    start: "02:00"
    end: "06:00"

remedies:
  type: service_credit
  schedule:
    - threshold: ...
      credit: ...
```

This is only an example schema. The actual contract should control the configured policy.

The engine should support multiple SLA dimensions, not just uptime:

- Availability percentage
- Maximum outage duration
- Monthly downtime budget
- Incident response time
- Incident restoration time
- Packet loss
- Latency
- Jitter
- DNS availability
- Support response
- Maintenance exclusions
- Credit/remedy schedules

---

## Measurement architecture

A reasonable architecture could be:

### Collector

Runs locally and periodically measures:

- ICMP
- TCP connectivity
- DNS
- HTTPS
- Gateway reachability
- Multiple endpoints

Potential technologies:

- Python
- Go
- Rust
- .NET

Prioritize reliability and low resource usage.

### Local storage

SQLite is likely sufficient initially.

Suggested tables:

- `measurements`
- `outages`
- `sla_policies`
- `sla_periods`
- `sla_events`
- `maintenance_windows`
- `annotations`
- `support_tickets`
- `teams_events`
- `network_interfaces`
- `endpoints`
- `reports`

Store raw observations separately from derived classifications.

### Detection engine

Convert measurements into events:

`measurement → anomaly → incident → SLA classification`

Avoid losing raw measurements.

### UI

A local web UI is acceptable, e.g.:

- FastAPI backend
- React/Vite frontend

Or a simpler single-process desktop/local web app.

The app should be usable entirely on localhost and not require a cloud account.

---

## Data integrity / evidence requirements

Evidence quality is important because the eventual purpose is vendor escalation.

The app should:

- Timestamp all measurements in UTC plus local display time.
- Use monotonic clocks for duration calculations.
- Record clock synchronization status where possible.
- Preserve raw observations.
- Never silently rewrite historical data.
- Record when users manually edit/classify events.
- Maintain an audit trail.
- Hash exported evidence bundles if practical.
- Include software version/configuration in reports.
- Include endpoint configuration in reports.
- Record timezone.
- Record measurement interval.
- Record whether measurement was Wi-Fi or Ethernet.
- Distinguish automatic detection from user-reported events.

The report should show the evidence chain rather than just a conclusion.

Example:

```text
2026-09-16 14:03:11 — gateway reachable
2026-09-16 14:03:12 — 1.1.1.1 unreachable
2026-09-16 14:03:12 — 8.8.8.8 unreachable
2026-09-16 14:03:13 — HTTPS health endpoint failed
2026-09-16 14:03:14 — Teams call active
2026-09-16 14:03:15 — user reports outbound audio loss
...
2026-09-16 14:08:42 — external connectivity restored
```

Then:

```text
Observed Internet interruption: 5m 30s
Local gateway interruption: none
Independent external targets affected: 3
Classification: probable upstream/property-network event
SLA classification: pending contractual policy/exclusions
```

This is much stronger than simply saying "ISP outage."

---

## Correlation / confidence

The application can calculate an evidence-confidence classification, but should not pretend this is legal certainty.

For example:

- Local-only failure
- Likely Wi-Fi/LAN
- Likely upstream
- Likely ISP/property network
- External-path-specific
- Insufficient evidence

The rules should be transparent and configurable.

Possible evidence inputs:

- Gateway packet loss
- External packet loss
- Multiple external endpoints
- DNS failure
- HTTPS failure
- Ethernet vs Wi-Fi
- Public IP change
- Concurrent user report
- Application-generated network telemetry
- Other devices, if monitored
- ISP outage notice
- ISP support ticket
- ISP-provided incident ID

---

## Multi-device capability

A future version should support multiple probes/devices.

Example:

- Primary Windows workstation
- Phone
- Another laptop
- Raspberry Pi / mini PC
- Optional always-on local probe

This helps distinguish:

`single-device issue` vs `apartment/local Wi-Fi issue` vs `property-wide outage`.

If multiple devices on different access points/interfaces fail simultaneously, that is stronger evidence of a property/upstream event.

Do not assume devices are under the user's administrative control; make the probe architecture opt-in.

---

## Support ticket integration

Allow the user to record:

- Ticket number
- Date/time opened
- Date/time closed
- Contact method
- Support representative
- ISP-provided cause
- ISP-provided outage duration
- ISP incident ID
- Promised corrective action
- Service credit
- Attached screenshots/emails

The application should correlate support tickets with detected events.

---

## Report generation

The app should generate an export suitable for:

- Apartment management
- Property owner/manager
- ISP/vendor management
- Corporate IT
- Personal records

Suggested report structure:

1. Executive summary
2. Service/SLA configuration
3. Measurement methodology
4. Monitoring period
5. Availability statistics
6. Outage timeline
7. Potential SLA events
8. Excluded events
9. Teams/work-impact correlation
10. Support tickets
11. ISP explanations
12. Evidence appendix
13. Raw-data export/hash

The executive summary should remain factual and avoid inflammatory/legal conclusions.

Example:

> "During the monitoring period, the collector recorded 14 connectivity incidents totaling 83 minutes of external Internet unavailability. 11 incidents were observed while the local gateway remained reachable. Three incidents overlapped with manually recorded Teams call-quality degradation. Contractual SLA qualification is pending confirmation of the applicable Bexley Arcadia/Gigstreem service agreement and exclusions."

---

## Important current evidence / research notes

Public Gigstreem materials indicate 99.99% uptime/reliability, but the Bexley-specific contract has not been verified.

Microsoft Teams documentation provides useful technical thresholds for diagnosing call quality, but those thresholds should not be treated as ISP SLA thresholds.

ICMP ping is useful but insufficient by itself to prove Teams packet loss or an SLA breach.

The application should therefore use **multiple independent measurements and preserve raw evidence**.

---

## What the local coding model should build first

The application should be a **portable Windows network-monitoring appliance in software**.

The user should be able to copy the application to a Windows machine, launch it, configure an SLA policy, and let it run continuously without needing a cloud service.

The application itself should generate the measurements required for SLA analysis.

### Core requirement: simulate the network from the device

Do not make another application (Teams, a browser, etc.) the source of truth.

The portable app should actively exercise the network and independently calculate:

- Availability
- Packet loss
- RTT / latency
- Jitter
- DNS availability
- DNS resolution latency
- TCP connection success/failure
- TCP connection latency
- TLS handshake timing
- HTTPS availability
- HTTPS response latency
- HTTP status
- Download throughput
- Upload throughput, where practical
- Consecutive failures
- Outage duration
- Recovery duration
- Interface state
- Default gateway availability
- External endpoint availability

Where technically practical, add an application-level test that sends/receives a small controlled payload so the app can measure actual transport/application behavior rather than relying exclusively on ICMP.

### Measurement layers

The application should use several independent layers:

#### Layer 1 — Local link

Measure:

- Network adapter state
- Wi-Fi/Ethernet
- Default gateway reachability
- Gateway RTT
- Gateway packet loss

Purpose:

Identify failures local to the user's device/LAN/access point.

#### Layer 2 — Internet reachability

Measure multiple independent endpoints.

For example:

- ICMP endpoint A
- ICMP endpoint B
- HTTPS endpoint A
- HTTPS endpoint B
- DNS resolver A
- DNS resolver B

Do not hard-code providers. Endpoints should be configurable.

Purpose:

Determine whether the failure extends beyond the local gateway.

#### Layer 3 — Transport/application behavior

Perform controlled TCP/HTTPS tests.

Record:

- DNS lookup duration
- TCP connect duration
- TLS handshake duration
- Time to first byte
- Total request duration
- Response success/failure
- HTTP status
- Payload bytes transferred

Purpose:

Capture failures that ICMP alone cannot demonstrate.

#### Layer 4 — Throughput/degradation tests

Do not continuously run large bandwidth tests.

Instead, provide configurable periodic or on-demand tests.

Record:

- Download Mbps
- Upload Mbps
- Test duration
- Test endpoint
- Bytes transferred
- Interface

These should be clearly separated from availability measurements because a slow connection is not necessarily an outage.

---

## Device-side simulation / synthetic transaction engine

A major design goal is to make the app behave like a synthetic client using the network.

Create a configurable **Synthetic Network Test Engine**.

Example test profile:

```yaml
name: "Standard ISP SLA Probe"

interval_seconds: 5

gateway:
  enabled: true
  target: auto_detect
  method: icmp

internet:
  icmp:
    - target: "configured-endpoint-1"
    - target: "configured-endpoint-2"

  dns:
    - resolver: "configured-resolver-1"
    - resolver: "configured-resolver-2"

  https:
    - url: "configured-health-endpoint-1"
    - url: "configured-health-endpoint-2"

tcp:
  - host: "configured-endpoint-1"
    port: 443

throughput:
  enabled: false
  interval_minutes: 60
```

The application should support multiple profiles.

The default profile should be conservative and low-bandwidth.

---

## Jitter calculation

Jitter must be calculated from a sequence of latency samples rather than treated as a single value.

Store individual RTT samples.

Calculate at least:

- Minimum RTT
- Maximum RTT
- Mean RTT
- Median RTT
- Standard deviation
- Interquartile range
- Jitter

Document the exact jitter algorithm used.

If an industry-standard RTP-style jitter calculation is implemented, clearly identify it as such. Otherwise use a transparent inter-arrival/RTT variation calculation and label it accordingly.

Do not simply invent a proprietary "jitter score."

---

## Packet-loss calculation

Store raw probe results:

```text
timestamp
target
sequence_number
success
rtt_ms
error
```

Then calculate:

- Rolling packet loss
- Event packet loss
- Period packet loss
- Consecutive lost probes
- Recovery

Use configurable windows.

Example:

- 1-minute
- 5-minute
- 15-minute
- SLA-period

Do not delete failed probes after deriving the percentage.

---

## Outage detection algorithm

The detection engine should not declare an outage because one ping fails.

Use configurable thresholds such as:

```yaml
outage_detection:
  minimum_duration_seconds: 30
  minimum_failed_probes: 3

  external_failure:
    required_targets: 2
    required_successive_failures: 3

  gateway:
    separate_local_failure: true
```

The exact defaults can be tuned during testing.

A possible classification pipeline:

```text
raw probe
    ↓
measurement
    ↓
anomaly detection
    ↓
candidate incident
    ↓
correlation across endpoints
    ↓
incident classification
    ↓
SLA policy evaluation
```

---

## Network failure classification

The application should distinguish:

### Local device/link failure

Examples:

- Adapter disconnected
- Gateway unreachable
- Wi-Fi dropped
- Ethernet link down

### Local network failure

Gateway unreachable while adapter remains connected.

### Upstream connectivity failure

Gateway reachable while multiple independent Internet targets fail.

### DNS-specific failure

IP connectivity works but DNS resolution fails.

### HTTPS/application-path failure

DNS/TCP works but HTTPS transaction fails.

### Endpoint-specific failure

Only one destination fails while independent destinations work.

### General degradation

Connectivity remains available but latency, loss, jitter, or throughput significantly degrades.

### Unknown

Evidence is insufficient.

These are technical classifications, not contractual/legal conclusions.

---

## SLA calculation engine

The SLA engine consumes classified incidents and the configured contract.

It should answer:

- How much total downtime occurred?
- How much qualifying downtime occurred?
- What percentage availability was observed?
- How much SLA budget has been consumed?
- How much remains?
- Which events are potentially qualifying?
- Which events are excluded?
- Why was each event included/excluded?
- Which contractual fields are still unknown?

Every result should be traceable back to raw measurements.

---

## MVP build sequence

### Phase 1 — Portable monitoring core

- Windows portable executable
- No cloud dependency
- Runs without administrator privileges where possible
- SQLite
- Automatic default-gateway detection
- Multiple configurable external endpoints
- ICMP probes
- DNS probes
- TCP probes
- HTTPS probes
- RTT
- Packet loss
- Jitter
- DNS latency
- TCP latency
- TLS timing
- HTTP timing
- Interface detection
- Incident detection
- Raw measurement storage

### Phase 2 — Local dashboard

Show:

- Live connection status
- Gateway status
- Internet status
- DNS status
- HTTPS status
- Current latency
- Packet loss
- Jitter
- Recent incidents
- Current outage
- Interface
- Monitoring uptime

### Phase 3 — SLA policy engine

- Configurable SLA
- Measurement period
- Availability target
- Downtime budget
- Maximum outage duration
- Response/restoration requirements
- Exclusions
- Planned maintenance
- Maintenance windows
- Credit/remedy schedules
- Potential breach classification

### Phase 4 — Evidence/reporting

- Incident annotations
- Support tickets
- ISP explanations
- CSV export
- JSON export
- HTML report
- PDF report
- Evidence bundle
- Hash/integrity metadata
- Audit history

### Phase 5 — Advanced synthetic testing

- Controlled upload/download tests
- Configurable TCP payload tests
- Additional protocol tests
- Multiple local probes
- Cross-device correlation
- Notifications
- Optional ISP status feeds

---

## Automated testing / simulation environment

The developer should build a **network-condition simulator** so the application can be validated without waiting for real ISP outages.

The simulator should be able to generate:

1. Perfect network
2. Random packet loss
3. Sustained packet loss
4. High latency
5. Latency spikes
6. Jitter
7. DNS failure
8. TCP connection failure
9. HTTPS failure
10. Complete Internet outage
11. Gateway outage
12. Gateway healthy + upstream outage
13. Single-endpoint outage
14. Intermittent outages
15. Short outages below SLA threshold
16. Long outages above SLA threshold
17. Planned maintenance
18. Excluded events
19. Recovery
20. Multiple simultaneous endpoint failures

The simulator should verify that the detection and SLA engines classify each scenario correctly.

If the application uses dependency injection for network probes, the same measurement interfaces can be backed by:

- Real Windows network probes
- Deterministic simulated probes
- Recorded/replay data

This is preferable to trying to manipulate the operating system's network stack to create every failure condition.

---

## Portable application requirements

Target Windows first.

Prefer a self-contained build:

```text
NetworkSLA/
  NetworkSLA.exe
  config/
  data/
    network-sla.db
  exports/
  logs/
```

The application should ideally run from a directory or USB drive without installation.

If a Windows service is later added for continuous background monitoring, make it optional. The MVP should work as a normal user application.

Requirements:

- No cloud account
- No mandatory telemetry
- No external database
- No admin rights for normal monitoring
- Minimal network traffic
- Configurable probe frequency
- Configurable retention
- Local-only storage by default

---

## Design principles

1. **Evidence first.**
2. **Never confuse technical degradation with contractual breach.**
3. **Never assume the ISP SLA; make it configurable.**
4. **Preserve raw measurements.**
5. **Make classifications explainable.**
6. **Use multiple independent endpoints.**
7. **Separate local Wi-Fi problems from upstream failures.**
8. **Separate observed events from user-reported symptoms.**
9. **Separate SLA qualification from legal conclusions.**
10. **Keep the application local-first and privacy-conscious.**
11. **Do not require administrative privileges unless truly necessary.**
12. **Do not bypass corporate security controls on managed devices.**
13. **Make reports understandable to nontechnical property managers.**
14. **Make raw evidence available to technical/vendor teams.**
15. **Design the data model to support different ISPs and different SLA contracts.**

## Refined implementation notes (2026-09-16)

- **Language**: Python with FastAPI backend + simple HTML/CSS/JS SPA frontend
- **UI delivery**: Web interface accessible at `http://<machine-ip>:8000` for remote troubleshooting via RDP or any client connection to the machine
- **Storage constraints**: Assume 100GB free space; configure SQLite retention at 50% (~50GB) with automatic rotation
- **Probe frequency**: Default 1 second intervals (configurable per endpoint type via UI)
- **Gold-standard targets**: Cloudflare/1.1.1.1, Cloudflare/1.0.0.1, Google DNS/8.8.8.8, Quad9/9.9.9.9 (resilient, globally distributed, non-routable to prevent lockout)
- **Wi-Fi details**: Capture SSID/BSSID for all active interfaces; include in dashboard and reports
- **Dashboard focus**: Show metrics that make a case against ISP: outage duration, upstream failure evidence, excluded events, qualifying events
- **Reports on demand**: Generate incident-specific reports immediately when an incident ends, plus on-demand historical report generation
- **No Teams monitoring**: Do NOT attempt to monitor Teams calls for compliance reasons; only prove ISP SLA issues independently
- **Resource usage**: Modern home PC target — don't over-optimize prematurely; focus on correctness and evidence quality

---

## MVP build sequence (refined)

### Phase 1 — Portable monitoring core

- Windows-friendly Python application
- No cloud dependency
- SQLite with automatic retention management
- Automatic default-gateway detection
- Multiple configurable external endpoints (Cloudflare/Google DNS defaults)
- ICMP probes
- DNS probes (success/failure + latency)
- TCP probes
- HTTPS probes
- RTT, packet loss, jitter calculations
- Interface detection (Wi-Fi/Ethernet)
- Wi-Fi SSID/BSSID capture
- Incident detection with configurable thresholds
- Raw measurement storage

### Phase 2 — Local web dashboard

Show:

- Live connection status
- Gateway status
- Internet status
- DNS status
- Current latency, packet loss, jitter (rolling windows)
- Recent incidents timeline
- Current outage duration
- SLA utilization (budget, events count)
- Interface + SSID/BSSID display
- Monitoring uptime

### Phase 3 — SLA policy engine

- Configurable SLA policies (availability target, measurement period)
- Downtime budget calculation
- Exclusion tracking (planned maintenance, force majeure, customer equipment)
- Maintenance window support
- Service credit schedules (optional)
- Potential breach classification
- Qualifying event vs excluded event distinction

### Phase 4 — Evidence/reporting

- Incident annotations and manual classifications
- Support ticket recording
- ISP explanations/correlations
- **CSV export** (detailed measurements and events)
- **JSON export** (structured data for further processing)
- **PDF report** (executive summary + evidence chain)
- **HTML report** (visual timeline + charts)
- Audit history and raw-data hash

### Phase 5 — Advanced synthetic testing (future)

- Controlled upload/download tests (on-demand, not continuous)
- Configurable TCP payload tests
- Additional protocol tests as needed
- Optional multi-device correlation support

---

## Key architectural decisions

1. **Single Python process**: FastAPI handles HTTP requests + background monitoring task runs concurrently (async or separate thread).
2. **SQLite database**: Single `network-sla.db` file with tables for measurements, outages, policies, events, maintenance windows, annotations, tickets, reports, endpoints, interfaces.
3. **Retention management**: Monitor disk space; when approaching 100GB limit, delete oldest raw measurements first to maintain 50% retention threshold.
4. **Evidence-first design**: Store every raw probe result individually; never aggregate/deletes before export unless retention policy forces cleanup.
5. **Configurable everything**: Probe intervals, target endpoints, SLA thresholds, exclusion rules — all configurable via JSON file or UI settings that persist to database.

---

## Next steps

1. Create project structure with `src/` for source code and config/data directories.
2. Implement SQLite database schema (Phase 1 storage).
3. Build network probe functions (ICMP, DNS, TCP, HTTPS, gateway).
4. Implement outage detection algorithm with configurable thresholds.
5. Build FastAPI backend with monitoring task runner.
6. Create simple HTML/CSS/JS dashboard frontend.
7. Test with simulated network conditions using the simulator module.
8. Iterate on metrics and classifications based on real outages.

The application should be useful even without a confirmed ISP SLA — collect high-quality evidence now, configure actual contract terms later when available.

---

## Immediate coding prompt (refined)

Build the MVP described above as a Python FastAPI web application with local SQLite storage.

Start by:

1. Creating project structure (`src/`, `config/`, `data/network-sla.db`, `exports/`)
2. Designing database schema
3. Implementing network probe functions
4. Building outage detection engine
5. Creating SLA policy engine
6. Developing web dashboard UI
7. Building network simulator for automated testing

Before implementing measurement code, identify and document assumptions about endpoint configuration in the config files. The application should collect evidence immediately, with actual SLA contracts configurable later if obtained.

---

## Build progress (2026-09-16)

### Completed Components

**Core Architecture:**
- FastAPI web server with SQLite database (`data/network-sla.db`)
- Cross-platform design for Windows/Linux
- Local-first operation with no cloud dependency
- HTTP dashboard at port 8000 (configurable)

**Database Schema (`storage/models.py`):**
- `measurements` - Raw probe results with timestamps
- `outages` - Detected connectivity incidents  
- `sla_events` - SLA qualification tracking
- `sla_periods` - Configurable time periods for SLA calculation
- `maintenance_windows` - Planned maintenance exclusions
- `targets` - Configurable endpoint definitions
- `support_tickets` - ISP ticket tracking
- `annotations` - Manual notes and classifications
- `interfaces` - Network interface info (SSID/BSSID)
- `config` - Application settings
- `reports` - Generated report metadata
- `events` - Classified measurement events

**Network Probes (`src/probes/`):**
- ICMP ping via subprocess (Windows/Linux compatible)
- DNS resolution testing with latency measurement
- TCP connectivity tests
- HTTPS/TLS health checks
- Gateway reachability detection

**Detection Engine (`detection/engine.py`):**
- Outage detection with configurable thresholds
- Evidence-based classification:
  - `local-wifi-issue` when gateway fails
  - `likely-upstream` when multiple targets fail
  - `endpoint-specific-failure` for single-target issues
  - Insufficient evidence cases

**SLA Policy Engine (`sla/policy.py`):**
- Configurable SLA policies with availability targets
- Downtime budget calculation (99.99% = ~52 min/year)
- Exclusion rule support (planned maintenance, force majeure)
- Maintenance window tracking
- Breach qualification logic

**Web Dashboard (`web/`):**
- HTML/CSS/JS static files
- Real-time status monitoring
- Outage timeline display
- Manual test trigger capability
- Report generation button

**Configuration (`config/default_config.json`):**
- Probe intervals (default 2 seconds)
- Endpoint lists (Cloudflare, Google DNS defaults)
- SLA policy parameters
- Retention settings

**Launch Scripts:**
- `start.bat` for Windows
- `start.sh` for Linux/Mac  
- README with setup documentation

### Next Steps

1. **Fix diagnostic issues**: Cleanup optional code paths in probes/https.py and other modules
2. **Implement background monitoring task**: Create async monitoring loop for continuous probing
3. **Add PDF report generation**: Integrate a lightweight library (e.g., `weasyprint` or headless browser)
4. **Build network simulator**: Implement test scenarios for validation
5. **Wire up all probes to measurement storage**: Connect probe results to database
6. **Add WebSocket for real-time updates**: Improve dashboard responsiveness
7. **Implement maintenance window UI**: Add form for recording planned maintenance

### Design Decisions Documented

1. **Cross-platform first**: Python chosen over Go/Rust for rapid development; portable from USB/Any device
2. **Web interface over CLI-only**: Browser accessible via machine IP suits RDP troubleshooting scenario
3. **Simple startup, no service**: User-mode app with login-startup preferred over Windows Service (no admin rights needed)
4. **PDF first for reports**: Property managers want professional PDF documents; CSV/JSON secondary
5. **Simulation deferred but planned**: Build real monitoring first; add simulator when validation needed
6. **Manual annotations only**: Respect privacy/confidentiality - no Teams integration or automatic work detection

### Architecture Summary

```
┌─────────────────────────────────────────────────┐
│              ISP Accountability Monitor          │
│                                                 │
│  ┌─────────────┐  ┌──────────────────────────┐ │
│  │ FastAPI Web │  │   SQLite (network-sla.db)│ │
│  │   Server    │  │                           │ │
│  │             │  │ ┌─────────────────────┐   │ │
│  └──────┬──────┘  │ │ measurements        │   │ │
│          │        │ │ outages             │   │ │
│         HTTP       │ │ sla_events          │   │ │
│    ┌─────▼────┐   │ │ sla_periods         │   │ │
│    │Static Files│  │ │ maintenance_windows │  │ │
│    │ Dashboard │   │ │ targets             │   │ │
│    └──────────┘   │ │ support_tickets      │   │ │
│                   │ │ annotations          │   │ │
│           │       │ │ interfaces           │   │ │
│           │       │ │ config               │   │ │
│         WebSocket│  │ reports              │   │ │
│         (future) │  └─────────────────────┘   │ │
│                   └──────────────────────────┘ │
└─────────────────────────────────────────────────┘

Probes: ICMP → DNS → TCP → HTTPS
        ↓          ↓      ↓       ↓
    Detection → SLA Engine → Reports
```

All data local, all conclusions evidence-based with transparency.

---

## Decisions confirmed (2026-09-16)

1. **Platform**: Cross-platform (Windows/Linux), browser-accessed UI via HTTP server
2. **UI approach**: Simple local web dashboard from the start (no CLI-first)
3. **Probe interval**: Default 2 seconds (configurable, low but responsive)
4. **Integration level**: Web dashboard with local SQLite + static files
5. **Teams integration**: None (respect privacy/confidential work - manual annotations only)
6. **Background mode**: User app with startup-from-login (no Windows service, no admin rights needed)
7. **Simulation strategy**: Build but don't aggressively test on live network (provide safety controls)
8. **Report priority**: PDF first, then CSV/JSON for technical analysis

---

## Architecture overview

```
ISP_Accountability/
  src/
    main.py              # FastAPI app entrypoint
    probes/
      icmp.py            # ICMP ping measurements
      dns.py             # DNS resolution tests
      tcp.py             # TCP connectivity checks
      https.py           # HTTPS/TLS timing
      gateway.py         # Default gateway reachability
      utils.py           # Shared measurement utilities
    detection/
      engine.py          # Outage detection & classification
    sla/
      policy.py          # SLA policy engine & breach calc
    storage/
      models.py          # SQLite models/schemas
      repo.py            # Repository pattern for DB access
    simulator/
      network.py         # Network condition simulator (for testing)
      scenarios.py       # Predefined test scenarios
    api/
      endpoints.py       # FastAPI route handlers
    tasks/
      monitor.py         # Background monitoring task
  config/
    default_config.json  # Default configuration
    sla_policies/        # SLA policy templates
  data/
    network-sla.db       # SQLite database (created at runtime)
  exports/
    reports/             # Generated PDF/CSV exports
  web/                   # Static web assets (HTML/CSS/JS)
  README.md             # User documentation
```

The application will:
- Run as a local HTTP server on port 8000 (or configurable)
- Start monitoring probes automatically on launch
- Persist all data to SQLite
- Provide REST API for configuration and reporting
- Generate PDF reports on demand
