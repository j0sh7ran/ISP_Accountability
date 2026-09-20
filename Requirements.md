# ISP Network SLA Monitor — Python/Django Application

## Role

You are acting as the lead software architect and implementation planner for a portable Windows network-monitoring application.

The goal is to build a **Python/Django web application that runs locally on a single Windows device** and continuously measures ISP/network performance, stores measurements locally, identifies network incidents, evaluates configurable SLA conditions, generates reports, and provides a dashboard.

This application must remain useful when the Internet connection is unavailable.

You are currently operating in **GitHub Copilot Plan Mode**.

### IMPORTANT

Do NOT begin implementation yet.

First:

1. Inspect the repository.
2. Identify the existing project structure and technology choices.
3. Identify reusable components.
4. Identify missing dependencies.
5. Produce a detailed implementation plan.
6. Identify architectural risks and decisions that should be made before implementation.
7. Break the implementation into logical phases/issues.
8. Explain the proposed database schema.
9. Explain how offline operation will work.
10. Explain how measurements will be collected without blocking the Django web application.
11. Explain how reports will be generated.
12. Explain how industry baselines will be represented.
13. Explain the testing strategy.

Do not make large architectural assumptions without documenting them in the plan.

---

# 1. Product Objective

Build a local-first network monitoring and ISP SLA analysis application.

The application should continuously answer:

> "What is the actual quality and reliability of my Internet connection, what happened when it degraded, how severe was it, and does the measured behavior potentially violate my ISP's SLA?"

The system should collect raw measurements, derive higher-level events, group events into incidents, compare measurements against configurable thresholds and industry reference baselines, and produce evidence-quality reports.

The application must NOT depend on cloud connectivity to operate.

---

# 2. Primary Requirements

The application must:

* Run locally on Windows.
* Use Python.
* Use Django for the web application.
* Use a portable local database.
* Continue collecting measurements while Internet connectivity is unavailable.
* Continue serving the dashboard while Internet connectivity is unavailable.
* Automatically resume normal measurements when connectivity returns.
* Persist measurements locally.
* Detect network outages.
* Detect network degradation.
* Detect recovery.
* Create an outage/incident report when connectivity goes offline.
* Link generated reports from the dashboard.
* Export historical measurements and incidents.
* Generate human-readable reports.
* Compare measured results against configurable ISP SLA thresholds.
* Compare measured results against configurable industry baselines.
* Maintain a complete historical measurement record.
* Avoid depending on external APIs for core functionality.

---

# 3. Local-First Architecture

The system must be designed as:

```text
Windows Device
      │
      ├── Django Web Application
      │
      ├── Local Measurement Engine
      │
      ├── Local Event/Incident Engine
      │
      ├── Local SLA Evaluation Engine
      │
      ├── Local Report Generator
      │
      └── Portable Local Database
```

Internet connectivity should only be required for network measurements themselves.

The Django UI, database, historical data, configuration, and reporting functionality must continue working when the Internet is unavailable.

---

# 4. Database

Use a portable local database.

Preferred initial implementation:

**SQLite**

Requirements:

* Database stored locally with the application.
* No external database server required.
* Database survives application restarts.
* Database survives Internet outages.
* Transactions should prevent data corruption.
* Database schema should support long-term historical storage.
* Use Django migrations.
* Avoid storing large binary data directly in normal measurement tables unless justified.

Design the schema so that the application could migrate to PostgreSQL later without a major redesign.

---

# 5. Measurement Categories

The measurement engine should support the following categories.

## Connectivity

* Default gateway reachability
* ISP first-hop reachability
* Internet endpoint reachability
* IPv4 connectivity
* IPv6 connectivity
* TCP connection success
* UDP reachability where practical
* HTTP availability
* HTTPS availability

## ICMP / Latency

Record:

* packets sent
* packets received
* packet loss percentage
* minimum RTT
* average RTT
* median RTT
* maximum RTT
* P95 RTT
* P99 RTT
* jitter
* timestamp
* destination
* protocol/address family

## Packet Loss

Measure:

* total loss
* consecutive packet loss
* burst loss
* loss duration
* loss frequency
* loss by destination
* loss by network layer

Distinguish between:

```text
Local gateway loss
ISP/access-network loss
Internet-path loss
Destination-specific failure
```

Do not assume that loss to one destination automatically means an ISP outage.

---

# 6. DNS Measurements

Support configurable DNS targets.

Measure:

* resolution time
* timeout
* SERVFAIL
* NXDOMAIN
* successful resolution
* failure rate
* IPv4 resolution
* IPv6 resolution
* DNS server used
* query type

Support comparison between:

* ISP DNS
* Cloudflare DNS
* Google DNS
* Quad9 DNS
* user-defined DNS servers

DNS tests must be independent from general Internet connectivity tests.

---

# 7. HTTP / HTTPS Measurements

Support configurable HTTP/HTTPS test endpoints.

Record:

* DNS lookup duration where measurable
* TCP connection duration
* TLS handshake duration
* time to first byte
* total request duration
* HTTP status code
* connection failure
* timeout
* redirect count
* IPv4/IPv6
* destination

Do not treat an HTTP server failure as automatically being an ISP outage.

---

# 8. TCP Measurements

Measure:

* TCP connection success
* TCP connection failure
* timeout
* connection refused
* connection reset
* connection establishment time

Where Windows APIs permit, collect TCP statistics including:

* retransmissions
* failed connections
* reset connections
* established connections

Clearly distinguish measured values from inferred values.

---

# 9. Throughput

Support controlled download and upload tests.

Record:

* download Mbps
* upload Mbps
* average throughput
* peak throughput
* minimum throughput
* throughput variance
* duration
* test endpoint
* IPv4/IPv6
* protocol
* test size

Do NOT continuously perform bandwidth saturation tests.

Bandwidth-intensive tests must have:

* configurable schedule
* configurable maximum duration
* configurable data limit
* manual trigger
* explicit enable/disable setting

The default configuration should prioritize low bandwidth consumption.

---

# 10. Bidirectional Throughput

Support controlled:

```text
Download only
Upload only
Download + Upload
```

tests.

During these tests measure:

* download Mbps
* upload Mbps
* latency
* jitter
* packet loss

This data should support congestion and bufferbloat analysis.

---

# 11. Bufferbloat

Implement a controlled test that compares:

```text
Idle latency
        ↓
Download-loaded latency
        ↓
Upload-loaded latency
        ↓
Bidirectional-loaded latency
        ↓
Recovery latency
```

Record:

* baseline RTT
* loaded RTT
* latency increase
* packet loss during load
* throughput during load
* recovery time

Do not label a result "bufferbloat" solely from one measurement.

Store the underlying measurements so the classification can be independently reviewed.

---

# 12. Routing

Support periodic route measurements.

Capture:

* hop number
* IP address
* hostname when available
* RTT
* timeout
* packet-loss indication where meaningful
* IPv4/IPv6
* timestamp

Detect:

* route changes
* first-hop changes
* hop-count changes
* persistent route differences

The application should distinguish:

```text
Observed route change
```

from:

```text
Potential routing problem
```

Do not automatically classify every route change as a fault.

---

# 13. MTU / PMTUD

Support controlled MTU testing.

Measure:

* largest successful packet size
* fragmentation behavior
* DF behavior
* PMTUD response
* failure threshold

Generate an event if configured thresholds indicate a possible MTU/PMTUD problem.

---

# 14. IPv4 / IPv6

All applicable measurements should record address family.

Dashboard should allow:

* IPv4-only view
* IPv6-only view
* combined view

Compare:

* latency
* loss
* throughput
* connectivity
* DNS
* routes

between IPv4 and IPv6.

---

# 15. Network Interface Metrics

Where available through Windows APIs, collect local interface information.

Potential metrics:

* interface state
* link speed
* bytes received
* bytes transmitted
* packets received
* packets transmitted
* receive errors
* transmit errors
* discarded packets
* interface changes

Use these metrics to help distinguish:

```text
Local device/interface problem
```

from:

```text
ISP/network problem
```

---

# 16. Measurement Architecture

Do NOT run measurement loops directly inside Django request handlers.

Create a separate measurement subsystem/process.

Recommended conceptual architecture:

```text
Django
  │
  ├── Dashboard
  ├── REST/API layer if useful
  ├── Configuration
  ├── Reports
  └── Database
          ▲
          │
Measurement Worker
  │
  ├── ICMP tests
  ├── TCP tests
  ├── DNS tests
  ├── HTTP tests
  ├── routing tests
  ├── throughput tests
  ├── MTU tests
  └── interface metrics
```

The worker should communicate with Django/database through a clean abstraction.

The architecture should allow the measurement engine to run even when the web UI is not actively open.

---

# 17. Scheduling

Measurements should have configurable frequencies.

Example defaults:

### Frequent

Every few seconds/minutes:

* gateway ping
* ISP/Internet reachability
* latency
* packet loss

### Moderate

Every few minutes:

* DNS
* HTTP/HTTPS
* TCP
* route sampling

### Infrequent

Every few hours/day:

* route analysis
* MTU testing
* IPv4/IPv6 comparison

### On-demand / scheduled

* bandwidth test
* bufferbloat test
* bidirectional saturation

Do not hard-code these values.

Store schedules/configuration in the database or application configuration.

---

# 18. Offline Behavior

This is a critical requirement.

The application must continue functioning when the Internet disappears.

When the network goes offline:

1. Detect loss of connectivity.
2. Continue running the local measurement engine.
3. Continue storing measurements locally.
4. Record the beginning of the outage.
5. Continue monitoring recovery.
6. Record the outage duration.
7. Record the recovery timestamp.
8. Generate an outage/incident report.
9. Link the report from the dashboard.
10. Resume normal measurements automatically after recovery.

The application must NOT require:

* cloud connectivity
* remote database access
* external authentication
* Internet-based report generation

for these operations.

---

# 19. Offline State Machine

Implement an explicit network state machine.

Conceptually:

```text
ONLINE
   │
   │ degradation
   ▼
DEGRADED
   │
   │ connectivity lost
   ▼
OFFLINE
   │
   │ connectivity restored
   ▼
RECOVERING
   │
   ▼
ONLINE
```

The exact states can be adjusted during architecture planning.

Avoid declaring an outage based on a single failed probe.

Use configurable confirmation thresholds such as:

* consecutive failures
* failure duration
* number of independent targets failing

---

# 20. Incident Detection

Create higher-level incidents from raw measurements.

Potential incident types:

```text
OUTAGE
MICRO_OUTAGE
PACKET_LOSS
LATENCY_DEGRADATION
JITTER_DEGRADATION
THROUGHPUT_DEGRADATION
DNS_FAILURE
DNS_DEGRADATION
ROUTE_CHANGE
IPV6_FAILURE
MTU_FAILURE
BUFFERBLOAT
CONNECTION_FAILURE
```

An incident should contain:

* start time
* end time
* duration
* type
* severity
* affected tests
* affected destinations
* supporting measurements
* recovery status
* generated report
* SLA evaluation

---

# 21. Incident Correlation

The system should correlate simultaneous measurements.

Example:

```text
Gateway: healthy
ISP first hop: healthy
Internet targets: failing
DNS: healthy
```

should produce different evidence from:

```text
Gateway: failing
ISP first hop: failing
Internet targets: failing
```

The system should store the evidence used to classify an incident.

Avoid making unsupported causal claims.

Use terminology such as:

* "Observed"
* "Consistent with"
* "Potential"
* "Unable to determine"

rather than automatically claiming definitive root cause.

---

# 22. SLA Engine

Create a configurable SLA rules system.

An SLA rule should be able to specify:

* metric
* threshold
* operator
* minimum duration
* measurement window
* applicable protocol
* applicable destination
* applicable time period
* severity
* enabled/disabled

Examples:

```text
Packet loss > 2% for > 5 minutes
Latency > 100 ms for > 10 minutes
Availability < 99.9% monthly
Outage > 30 seconds
Throughput < X Mbps
```

These are examples only.

Do not hard-code them as actual ISP contractual requirements.

The user must be able to enter the actual SLA terms from their ISP contract.

---

# 23. Industry Baselines

Create a separate baseline system.

Baselines should NOT be treated as contractual requirements.

Store:

* metric
* baseline value
* unit
* population/context
* technology type
* geographic scope if applicable
* source
* source URL
* publication date
* methodology
* notes

Examples:

```text
Typical latency
Typical packet loss
Typical jitter
Typical availability
Typical throughput
Typical DNS response time
```

The UI must clearly distinguish:

```text
ISP Contractual SLA
```

from:

```text
Industry Reference Baseline
```

Industry baselines should be versioned so historical comparisons remain reproducible.

---

# 24. Dashboard

Build a comprehensive local dashboard.

## Overview

Show:

* current network state
* current connectivity
* current latency
* packet loss
* jitter
* download speed
* upload speed
* IPv4 status
* IPv6 status
* DNS status
* active incidents
* recent incidents
* SLA violations/potential violations
* uptime

## Historical graphs

Support selectable ranges:

* last hour
* 6 hours
* 24 hours
* 7 days
* 30 days
* custom range

Charts should include:

* latency
* packet loss
* jitter
* throughput
* availability
* DNS response time
* route changes
* incident periods

---

# 25. Incident Dashboard

Provide a dedicated incident view.

For every incident display:

```text
Incident ID
Type
Start
End
Duration
Severity
Affected metrics
Affected endpoints
Evidence
SLA evaluation
Report
```

Allow the user to drill down into the raw measurements surrounding the event.

---

# 26. Outage Report

When an outage occurs, automatically create a report.

The report should include:

## Summary

* incident ID
* start
* end
* duration
* detected state
* recovery state

## Connectivity evidence

* gateway results
* ISP first-hop results
* Internet endpoint results
* IPv4 results
* IPv6 results

## Performance before outage

* latency
* jitter
* packet loss
* throughput

## Performance during outage

* failed tests
* successful tests
* timestamps
* destinations

## Recovery

* recovery time
* first successful measurements
* return-to-normal measurements

## SLA evaluation

* applicable rules
* observed values
* thresholds
* whether the rule appears satisfied/breached based on recorded evidence

Clearly label uncertainty.

---

# 27. Report Formats

Support at minimum:

* HTML
* PDF
* CSV

Potentially:

* JSON

HTML should be generated locally.

PDF generation should also work without Internet connectivity.

CSV should allow raw measurements to be exported.

JSON should allow machine-readable archival/export.

---

# 28. Historical Comparison

The user should be able to select:

```text
Current period
vs
Previous period
```

Examples:

```text
Today vs yesterday
This week vs last week
This month vs last month
Custom period vs custom period
```

Compare:

* uptime
* outages
* outage duration
* latency
* packet loss
* jitter
* throughput
* DNS
* route changes

Do not hide underlying data behind a single score.

---

# 29. Industry Comparison

Dashboard should allow:

```text
Measured value
Industry baseline
Difference
Percentage difference
```

Example:

```text
Median latency
Measured: 21 ms
Reference: 25 ms
Difference: -16%
```

This is a descriptive comparison, not a quality ranking.

Always show the source and context for the baseline.

---

# 30. SLA Comparison

Provide a separate view:

```text
Metric
Observed
Contract threshold
Duration
Result
Evidence
```

Example:

```text
Packet loss
Observed: 3.2%
Threshold: 2.0%
Duration: 8m 42s
Status: Potential SLA breach
```

The application should never silently convert industry benchmarks into SLA requirements.

---

# 31. Data Retention

Implement configurable retention.

Example options:

* 7 days
* 30 days
* 90 days
* 1 year
* indefinite

Do not delete raw data without explicit configuration.

Consider aggregation for older data:

```text
Raw measurements
      ↓
Hourly aggregates
      ↓
Daily aggregates
```

but preserve incidents and SLA evidence.

---

# 32. Export

Allow exports
