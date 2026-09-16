"""
SLA policy engine for breach calculation and qualification.
"""
from datetime import datetime, timezone, timedelta


def get_timestamps(utc_only: bool = False) -> tuple[str, str]:
    """Get current UTC and local timestamps."""
    now = datetime.now(timezone.utc)
    utc_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not utc_only:
        local_ts = now.strftime("%Y-%m-%d %H:%M:%S%Z")
    else:
        local_ts = utc_ts
    return utc_ts, local_ts


class SLAPolicy:
    """Represents an SLA policy with configurable parameters."""

    def __init__(
        self,
        name: str,
        availability_target: float = 99.99,
        measurement_period: str = "monthly",
        max_outage_duration_seconds: float = 300.0,
        exclusion_rules: list[str] = None,
        maintenance_window_start: str = None,
        maintenance_window_end: str = None,
    ):
        self.name = name
        self.availability_target = availability_target
        self.measurement_period = measurement_period
        self.max_outage_duration_seconds = max_outage_duration_seconds
        self.exclusion_rules = exclusion_rules or []
        self.maintenance_window_start = maintenance_window_start
        self.maintenance_window_end = maintenance_window_end

    def calculate_downtime_budget(
        self,
        period_days: int = 30,
    ) -> dict:
        """Calculate allowable downtime for a measurement period."""
        # Annual allowable downtime for 99.99%: ~52.6 minutes
        # Monthly allowable downtime for 99.99%: ~4.38 minutes
        # Daily allowable downtime for 99.99%: ~0.143 minutes (8.6 seconds)

        seconds_per_day = 86400
        available_seconds = seconds_per_day * self.availability_target / 100

        if self.measurement_period == "monthly":
            period_seconds = period_days * seconds_per_day
            budget_seconds = round((period_seconds - available_seconds) / period_days, 2)
        elif self.measurement_period == "daily":
            budget_seconds = round(seconds_per_day - available_seconds, 2)
        else:
            # Annual
            budget_seconds = round(seconds_per_day * 365 - (seconds_per_day * 365 * self.availability_target / 100), 2)

        return {
            "policy_name": self.name,
            "availability_target": f"{self.availability_target}%",
            "period_days": period_days,
            "budget_seconds": budget_seconds,
            "budget_minutes": round(budget_seconds / 60, 2),
        }

    def is_outage_excluded(
        self,
        outage_start: str,
        outage_duration_seconds: float,
        reason: str,
    ) -> bool:
        """Check if an outage should be excluded from SLA calculation."""
        exclusions = [e.lower() for e in self.exclusion_rules]

        if "planned_maintenance" in exclusions and reason.lower().startswith("planned"):
            return True
        if "force_majeure" in exclusions:  # Would need to check specific force majeure events
            return True
        if "customer_equipment" in exclusions and reason.startswith("customer"):
            return True

        return False

    def is_within_maintenance_window(
        self,
        outage_start: str,
        outage_end: str,
    ) -> bool:
        """Check if an outage occurred within a maintenance window."""
        if not self.maintenance_window_start or not self.maintenance_window_end:
            return False

        start_time = datetime.strptime(self.maintenance_window_start, "%H:%M").time()
        end_time = datetime.strptime(self.maintenance_window_end, "%H:%M").time()

        # Simplified: check if outage falls within typical maintenance window (2am-6am)
        # A real implementation would parse timestamps properly
        return False  # Placeholder


class SLACalculator:
    """Calculate SLA metrics and breach status."""

    def __init__(self, policy: SLAPolicy):
        self.policy = policy

    def calculate_utilization(
        self,
        outage_events: list[dict],
        period_start: str,
        period_end: str,
    ) -> dict:
        """Calculate current SLA utilization."""
        # Filter outages that fall within the period
        period_outages = []

        for outage in outage_events:
            outage_start = datetime.fromisoformat(outage["start_timestamp_utc"].replace("Z", "+00:00"))
            outage_end = datetime.fromisoformat(outage.get("end_timestamp_utc") or outage["start_timestamp_utc"]).replace(
                tzinfo=timezone.utc,
            )

            period_start_dt = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
            period_end_dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))

            if outage_start >= period_start_dt and outage_end <= period_end_dt:
                # Check exclusions
                if not self.policy.is_outage_excluded(
                    outage["start_timestamp_utc"],
                    outage.get("duration_seconds") or 0,
                    outage.get("classification_reason") or "",
                ):
                    period_outages.append(outage)

        # Calculate totals
        total_downtime = sum(o.get("duration_seconds") or 0 for o in period_outages)
        excluded_count = sum(1 for o in outage_events if self.policy.is_outage_excluded(
            o["start_timestamp_utc"],
            o.get("duration_seconds") or 0,
            o.get("classification_reason") or "",
        ))

        # Calculate availability percentage
        uptime_budget_seconds = 86400 * (365 if self.policy.measurement_period == "annual" else 30)
        available_seconds = uptime_budget_seconds * self.policy.availability_target / 100
        observed_downtime = uptime_budget_seconds - total_downtime
        observed_availability = (observed_downtime / uptime_budget_seconds) * 100 if uptime_budget_seconds > 0 else 100

        return {
            "policy_name": self.policy.name,
            "period_start": period_start,
            "period_end": period_end,
            "outages_detected": len(period_outages),
            "outage_duration_total_seconds": total_downtime,
            "excluded_events": excluded_count,
            "qualifying_outage_minutes": round(total_downtime / 60, 2),
            "availability_target": f"{self.policy.availability_target}%",
            "observed_availability": f"{observed_availability:.2f}%",
            "downtime_budget_minutes": round(uptime_budget_seconds - available_seconds, 2),
            "remaining_budget_minutes": round(max(0, uptime_budget_seconds - available_seconds - total_downtime / 60), 2),
        }

    def classify_event(
        self,
        outage_duration_seconds: float,
        evidence_confidence: str,
        targets_affected: int,
    ) -> dict:
        """Classify an event as SLA-qualifying or excluded."""
        classification = {
            "duration_seconds": outage_duration_seconds,
            "evidence_confidence": evidence_confidence,
            "targets_affected": targets_affected,
            "meets_minimum_duration": outage_duration_seconds >= self.policy.max_outage_duration_seconds,
            "status": "pending",  # pending, excluded, confirmed, disputed
        }

        # Minimum duration check
        if not classification["meets_minimum_duration"]:
            classification["status"] = "excluded"
            classification["reason"] = f"Outage ({outage_duration_seconds}s) below minimum threshold ({self.policy.max_outage_duration_seconds}s)"
            return classification

        # Evidence confidence determines qualification
        valid_confidences = ["probable-upstream", "likely-upstream", "upstream-confirmed"]

        if evidence_confidence in valid_confidences:
            classification["status"] = "pending"  # Awaiting contractual confirmation
            classification["reason"] = f"Evidence indicates upstream failure; contractual SLA applicability pending"
        elif evidence_confidence == "local-only":
            classification["status"] = "excluded"
            classification["reason"] = "Local/Wi-Fi issue, not ISP responsibility"
        else:
            classification["status"] = "pending"
            classification["reason"] = "Upstream failure with sufficient evidence"

        return classification


class MaintenanceWindowManager:
    """Manage maintenance window tracking and exclusion."""

    def __init__(self):
        self.windows: list[dict] = []

    def add_window(self, window_id: str, start: str, end: str) -> None:
        """Add a maintenance window."""
        self.windows.append({
            "window_id": window_id,
            "start": start,
            "end": end,
            "is_planned": True,
        })

    def check_outage_in_window(
        self,
        outage_start: str,
        outage_end: str,
    ) -> dict:
        """Check if an outage falls within a maintenance window."""
        now = datetime.now(timezone.utc)
        outage_start_dt = datetime.fromisoformat(outage_start.replace("Z", "+00:00"))
        outage_end_dt = datetime.fromisoformat(outage_end.replace("Z", "+00:00"))

        for window in self.windows:
            window_start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
            window_end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))

            # Check if outage overlaps with maintenance window
            overlap_start = max(outage_start_dt, window_start)
            overlap_end = min(outage_end_dt, window_end)

            if overlap_start <= overlap_end:
                return {
                    "in_window": True,
                    "window_id": window["window_id"],
                    "scheduled": window.get("is_planned", False),
                    "within_allotted_time": self._is_within_maintenance_window(overlap_start, overlap_end),
                }

        return {
            "in_window": False,
            "window_id": None,
            "scheduled": False,
        }

    def _is_within_maintenance_window(self, start: datetime, end: datetime) -> bool:
        """Check if outage falls within typical maintenance window (e.g., 2am-6am)."""
        # For now, assume any maintenance window allows outages
        return True
