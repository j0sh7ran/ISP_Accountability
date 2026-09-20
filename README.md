# ISP Network SLA Monitor

A local-first Python/Django application that runs on a single Windows device to continuously
measure ISP/network quality, detect outages and degradation, evaluate results against your ISP's
SLA and generic industry baselines, and generate evidence-quality reports — all without depending
on cloud connectivity to operate.

See [Requirements.md](Requirements.md) for the full product requirements and [docs/](docs/README.md)
for the architecture, data model, and phased implementation history.

## Quickstart

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Then, in two separate terminals:

```powershell
.\.venv\Scripts\python.exe manage.py runserver      # dashboard: http://127.0.0.1:8000/
.\.venv\Scripts\python.exe manage.py run_worker     # measurement worker (run elevated for full ICMP fidelity)
```

Configure at least one `Target` (e.g. your default gateway) at `/admin/core/target/` before
starting the worker. Full setup, elevation, and firewall details are in
[docs/SETUP_AND_OPERATIONS.md](docs/SETUP_AND_OPERATIONS.md).

## Testing

```powershell
.\.venv\Scripts\python.exe manage.py test
```

## Project status

All 9 planned implementation phases are complete — see [docs/PHASES.md](docs/PHASES.md) for the
full roadmap, exit criteria, and verification notes for each phase.
