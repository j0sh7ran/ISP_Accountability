---
name: isp-accountability-project
description: ISP Accountability monitor project - local network monitoring tool for SLA breach evidence collection
metadata:
  type: project
---

Project: ISP Accountability Monitor

Context: Building a portable Windows/Linux application that monitors ISP connectivity, detects outages, and generates professional reports for escalation to property management/vendor. Target environment: multifamily apartment with Gigstreem ISP via managed Wi-Fi provider Bexley Arcadia in Fort Worth, TX. Recurring network issues affecting Microsoft Teams calls (voice loss).

Goal: Create a local-first application with no cloud dependency that runs continuously, survives network interruptions, and produces defensible evidence of ISP connectivity failures including:
- Outage detection with automatic classification (local vs upstream/ISP)
- SLA policy configuration (availability targets, measurement periods, exclusions)
- Raw measurement preservation for audit trail
- PDF reports suitable for property management/vendor escalation

Key Design Decisions:
1. Cross-platform (Windows/Linux) - Python chosen for portability and wide package availability
2. Web interface at port 8000 accessible via machine IP (useful for RDP troubleshooting)
3. User-mode app with login startup (no Windows service, no admin rights needed)
4. Manual annotation only for confidential work scenarios (no Teams integration)
5. PDF reports first priority, then CSV/JSON for technical analysis
6. Simple probe implementation using subprocess ping + standard library

Current State: 2026-09-16 - Core architecture implemented with:
- FastAPI web server with SQLite database
- Network probes (ICMP, DNS, TCP, HTTPS, gateway)
- Outage detection engine with evidence-based classification
- SLA policy engine for breach calculation
- Web dashboard frontend (HTML/CSS/JS)
- Database models and repositories
- Retention/cleanup utilities

Next Tasks:
1. Wire up monitoring task to run continuously in background
2. Add report generation (PDF + CSV export)
3. Integrate storage repository with probe results
4. Add network simulator for testing without affecting live network
5. Implement maintenance window tracking UI
6. Complete documentation and user-facing help

See context.md for full project specification and design rationale.
