# ISP Network SLA Monitor — Architecture Documentation

This folder is the source of truth for the system design, agreed upon before implementation begins
(per [Requirements.md](../Requirements.md)). Update these docs whenever an architectural decision changes —
do not let code and docs drift.

## Documents

| Doc | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System overview, process model, components, offline operation |
| [DATA_MODEL.md](DATA_MODEL.md) | Full database schema (ER diagram + field descriptions) |
| [WORKER_AND_SCHEDULING.md](WORKER_AND_SCHEDULING.md) | Non-blocking measurement worker design, scheduling tiers |
| [STATE_MACHINE_AND_INCIDENTS.md](STATE_MACHINE_AND_INCIDENTS.md) | Connectivity state machine, event/incident correlation |
| [SLA_AND_BASELINES.md](SLA_AND_BASELINES.md) | Configurable SLA rule engine vs. industry baseline system |
| [REPORTING_AND_RETENTION.md](REPORTING_AND_RETENTION.md) | Report generation pipeline, retention/aggregation, export |
| [PHASES.md](PHASES.md) | Phased implementation roadmap and exit criteria |
| [DECISIONS.md](DECISIONS.md) | Running log of architectural decisions and open risks |
| [SETUP_AND_OPERATIONS.md](SETUP_AND_OPERATIONS.md) | Install/run instructions, elevation, firewall, run-at-logon |

## Diagrams

Editable source diagrams live in [diagrams/](diagrams/) as `.drawio` files (open with the
[draw.io / diagrams.net VS Code extension](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio)
or [app.diagrams.net](https://app.diagrams.net)). Each `.drawio` diagram is mirrored as a Mermaid
diagram inline in the relevant markdown doc so it renders without any extension.

| Diagram | Mirrored in |
|---|---|
| [diagrams/architecture-overview.drawio](diagrams/architecture-overview.drawio) | ARCHITECTURE.md |
| [diagrams/er-overview.drawio](diagrams/er-overview.drawio) | DATA_MODEL.md |
| [diagrams/state-machine.drawio](diagrams/state-machine.drawio) | STATE_MACHINE_AND_INCIDENTS.md |
| [diagrams/incident-sla-flow.drawio](diagrams/incident-sla-flow.drawio) | STATE_MACHINE_AND_INCIDENTS.md |

## Maintenance rule

Whenever a design decision is proposed and approved in conversation, the corresponding `.md` file (and
`.drawio` diagram if affected) must be updated in the same change, and the decision appended to
[DECISIONS.md](DECISIONS.md). Nothing here should be considered final until reflected in these files.
