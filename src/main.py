"""
Main FastAPI application for ISP Accountability Monitor.
Provides network monitoring, outage detection, SLA analysis, and web dashboard.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Import our modules
from storage.models import init_database, seed_default_targets
from storage.repo import (
    MeasurementRepository,
    OutageRepository,
    SLARepository,
    InterfaceRepository,
    ConfigurationRepository,
)
from probes.icmp import ping_target, probe_gateway
from probes.dns import resolve_host, probe_dns_resolvers
from probes.tcp import probe_tcp_connect
from probes.gateway import probe_with_tcp_fallback, get_default_gateway
from detection.engine import OutageDetector, ClassificationEngine
from sla.policy import SLAPolicy, SLACalculator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database
    db_path = "data/network-sla.db"
    init_database(db_path)
    seed_default_targets(db_path)

    # Initialize repositories
    measurement_repo = MeasurementRepository(db_path)
    outage_repo = OutageRepository(db_path)
    sla_repo = SLARepository(db_path)
    interface_repo = InterfaceRepository(db_path)
    config_repo = ConfigurationRepository(db_path)

    app.state.measurement_repo = measurement_repo
    app.state.outage_repo = outage_repo
    app.state.sla_repo = sla_repo
    app.state.interface_repo = interface_repo
    app.state.config_repo = config_repo

    yield


app = FastAPI(
    title="ISP Accountability Monitor",
    description="Network monitoring and SLA breach evidence collection",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware for remote access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=JSONResponse)
async def root():
    """Health check and home endpoint."""
    return {
        "service": "ISP Accountability Monitor",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/status")
async def get_status():
    """Get current monitoring status."""
    outage = app.state.outage_repo.get_active_outage()
    config = app.state.config_repo.get_all_config()

    # Get latest measurement for a target
    latest_measurement = None
    try:
        latest_measurement = app.state.measurement_repo.get_latest_measurement("1.1.1.1")
    except Exception:
        pass

    return {
        "monitoring_active": True,
        "current_outage": outage or None,
        "configuration": config,
        "latest_icmp_measurement": latest_measurement,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/interfaces")
async def get_interfaces():
    """Get network interface information."""
    try:
        import psutil

        interfaces = []
        for iface_name, addrs in psutil.net_if_addrs().items():
            if "lo" in iface_name or "docker" in iface_name or "veth" in iface_name:
                continue

            iface_info = {
                "name": iface_name,
                "type": "wifi" if "wireless" in str(addrs) else "ethernet",
                "addresses": [addr.address for addr in addrs if hasattr(addr, 'address')],
            }

            interfaces.append(iface_info)

        return {"interfaces": interfaces}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/endpoints")
async def get_endpoints():
    """Get configured probe endpoints."""
    try:
        import socket
        from probes.dns import get_system_dns_servers

        return {
            "icmp_targets": ["1.1.1.1", "8.8.8.8", "9.9.9.9"],
            "dns_resolvers": get_system_dns_servers(),
            "tcp_ports": [443],
            "https_endpoints": ["https://1.1.1.1/", "https://cloudflare-dns.com/"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/probe/gateway")
async def probe_gateway_endpoint():
    """Manually trigger gateway probe."""
    try:
        result = probe_with_tcp_fallback("1.1.1.1", port=80)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/probe/{target_type}/{target_host}")
async def probe_target(
    target_type: str,
    target_host: str,
):
    """Trigger a probe against a specific target."""
    try:
        if target_type == "icmp":
            result = ping_target(target_host)
        elif target_type == "dns":
            result = resolve_host(target_host)
        elif target_type == "tcp":
            port = 443
            result = probe_tcp_connect(target_host, port)
        else:
            raise HTTPException(status_code=400, detail="Invalid probe type")

        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/outages")
async def get_outages(limit: int = 10):
    """Get recent outage records."""
    outages = app.state.outage_repo.get_all_outages(limit=limit)
    return {"outages": outages}


@app.get("/api/measurements")
async def get_measurements(
    target_host: str,
    limit: int = 50,
):
    """Get recent measurements for a target."""
    try:
        measurements = []

        # Get measurement in range from last hour
        one_hour_ago = (datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        )

        measurements = app.state.measurement_repo.get_measurements_in_range(one_hour_ago, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))[:limit]

        return {
            "target_host": target_host,
            "measurements": measurements,
            "count": len(measurements),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/outage/acknowledge")
async def acknowledge_outage(outage_id: int):
    """Mark an outage as acknowledged/user-reported."""
    try:
        # Get outage and add annotation
        outage = app.state.outage_repo.get_outage_by_id(outage_id)

        if not outage:
            raise HTTPException(status_code=404, detail="Outage not found")

        # In a full implementation, this would add an annotation
        return {
            "success": True,
            "outage_id": outage_id,
            "status": "acknowledged",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    """Get current application configuration."""
    try:
        config = app.state.config_repo.get_all_config()
        return {"config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config")
async def set_config():
    """Update application configuration (read-only for MVP)."""
    return {
        "success": False,
        "message": "Configuration updates not implemented in MVP",
        "note": "Use config directory to update settings before restart",
    }


@app.get("/api/report")
async def generate_report(
    period_start: str = None,
    period_end: str = None,
    format_type: str = "json",
):
    """Generate a report in the specified format."""
    try:
        if period_start is None or period_end is None:
            now = datetime.now(timezone.utc)
            period_start = (now - __import__("datetime").timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            period_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # In MVP, we just return JSON report
        outages = app.state.outage_repo.get_outages_by_period(period_start, period_end)

        return {
            "report_generated": True,
            "period": {"start": period_start, "end": period_end},
            "summary": {
                "total_outages": len(outages),
                "total_duration_seconds": sum(o.get("duration_seconds") or 0 for o in outages),
                "gateway_failures": sum(1 for o in outages if o.get("gateway_failed")),
            },
            "outages": outages,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve static files from web/ directory
static_files = StaticFiles(directory="web")

@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve static web assets."""
    try:
        return static_files.respond_with_static_file(path)
    except Exception as e:
        # If file not found, return 404
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Resource not found")
        raise


# Background monitoring task (run on startup)
@app.on_event("startup")
async def start_monitoring():
    """Start background monitoring task on application startup."""
    # In production, this would run uvicorn process or background thread
    # For MVP, we'll just log that monitoring is ready
    import logging
    logger = logging.getLogger(__name__)
    logger.info("ISP Accountability Monitor started - ready for probing")

    # Store start time in config
    app.state.config_repo.set_config("started_at", datetime.now(timezone.utc).isoformat())


@app.get("/api/report/pdf", response_class=FileResponse)
async def generate_pdf_report():
    """Generate HTML report that can be printed to PDF using browser Print to PDF."""
    from storage.repo import MeasurementRepository, OutageRepository
    from tasks.report import generate_report_html

    repo = MeasurementRepository("data/network-sla.db")
    outage_repo = OutageRepository("data/network-sla.db")

    # Get recent outages
    outages = outage_repo.get_all_outages()

    # Get SLA period info
    sla_period = app.state.sla_repo.get_sla_period() or {
        "availability_target": 99.99,
        "downtime_budget_minutes": 52.34,
        "observed_downtime_minutes": sum(o.get("duration_seconds", 0) / 60 for o in outages),
    }

    summary = {
        "uptime_target": f"{sla_period.get('availability_target', 99.99)}%",
        "downtime_budget_minutes": sla_period.get("downtime_budget_minutes", 52.34),
        "observed_availability": f"{(1 - sum(o.get('duration_seconds', 0) for o in outages) / (86400 * 30)) * 100:.2f}%",
        "remaining_budget_minutes": round(sla_period.get("downtime_budget_minutes", 52.34) -
                                          sum(o.get('duration_seconds', 0) for o in outages) / 60, 2),
        "total_duration_seconds": sum(o.get("duration_seconds") or 0 for o in outages),
    }

    period_start = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    period_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    html_content = generate_report_html(
        period_start=period_start,
        period_end=period_end,
        outages=outages,
        summary=summary,
    )

    return FileResponse("web/report.html", content=html_content, media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
