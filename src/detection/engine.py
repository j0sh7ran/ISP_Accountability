"""
Outage detection and classification engine.
Detects connectivity failures and classifies their scope.
"""
import json
from datetime import datetime, timezone
from typing import Optional


def get_timestamps(utc_only: bool = False) -> tuple[str, str]:
    """Get current UTC and local timestamps."""
    now = datetime.now(timezone.utc)
    utc_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not utc_only:
        local_ts = now.strftime("%Y-%m-%d %H:%M:%S%Z")
    else:
        local_ts = utc_ts
    return utc_ts, local_ts


# Detection thresholds (configurable)
DEFAULT_THRESHOLDS = {
    "minimum_duration_seconds": 30,  # Minimum outage duration to report
    "minimum_failed_probes": 3,      # Minimum consecutive failures
    "required_targets_for_upstream_failure": 2,  # How many targets must fail
}


class OutageDetector:
    """Detects and manages connectivity outages."""

    def __init__(
        self,
        thresholds: Optional[dict] = None,
    ):
        """Initialize detector with optional custom thresholds."""
        self.thresholds = {**DEFAULT_THRESHOLDS, **thresholds}
        self.current_outage_start: Optional[str] = None
        self.probe_failures: int = 0
        self.probe_successes: int = 0
        self.last_successful_probes: dict = {}
        self.last_failed_probes: dict = {}

    def record_measurement(
        self,
        target_host: str,
        success: bool,
        rtt_ms: Optional[float] = None,
    ) -> dict:
        """Record a measurement and update outage state."""
        result = {
            "timestamp_utc": get_timestamps()[0],
            "timestamp_local": get_timestamps()[1],
            "target_host": target_host,
            "success": success,
            "rtt_ms": rtt_ms,
        }

        if success:
            self.probe_successes += 1
            result["status"] = "healthy"
        else:
            self.probe_failures += 1
            self.last_failed_probes[target_host] = {
                "timestamp_utc": get_timestamps()[0],
                "rtt_ms": rtt_ms,
                "error": None,
            }

            # Check if we should declare an outage
            if self._should_declare_outage():
                result["status"] = "outage_declared"
                self.current_outage_start = get_timestamps()[0]
                self.probe_failures = 1  # Reset counter for this outage

        return result

    def _should_declare_outage(self) -> bool:
        """Check if current failures warrant declaring an outage."""
        if not self.last_failed_probes:
            return False

        failed_targets = list(self.last_failed_probes.keys())
        consecutive_failures = len(failed_targets)  # Simplified

        return (
            consecutive_failures >= self.thresholds["minimum_failed_probes"] and
            self.current_outage_start is not None
        )

    def end_outage(self) -> Optional[dict]:
        """End current outage if one exists."""
        if not self.current_outage_start:
            return None

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        duration = self._calculate_duration()

        return {
            "start_timestamp_utc": self.current_outage_start,
            "end_timestamp_utc": now,
            "duration_seconds": duration,
            "gateway_failed": len(self.last_failed_probes) > 0,
            "targets_affected": len(self.last_failed_probes),
            "severity": self._determine_severity(duration, targets_affected=len(self.last_failed_probes)),
        }

    def _calculate_duration(self) -> float:
        """Calculate outage duration in seconds."""
        if not self.current_outage_start:
            return 0

        start = datetime.fromisoformat(self.current_outage_start.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - start).total_seconds()

    def _determine_severity(
        self,
        duration: float,
        targets_affected: int,
    ) -> str:
        """Determine outage severity based on duration and scope."""
        if duration < 60 or targets_affected == 1:
            return "minor"
        elif duration < 300 or targets_affected < 3:
            return "moderate"
        elif duration < 900 or targets_affected < 5:
            return "severe"
        else:
            return "critical"

    def get_outage_status(self) -> dict:
        """Get current outage status."""
        if self.current_outage_start:
            duration = self._calculate_duration()
            return {
                "is_active": True,
                "start_timestamp_utc": self.current_outage_start,
                "duration_seconds": duration,
                "severity": self._determine_severity(duration),
                "targets_affected": len(self.last_failed_probes),
                "gateway_failed": False,  # Will be determined separately
            }
        return {
            "is_active": False,
            "start_timestamp_utc": None,
            "duration_seconds": 0,
            "severity": None,
        }

    def reset(self) -> None:
        """Reset detector state (for recovery detection)."""
        self.probe_failures = 0
        self.current_outage_start = None


class ClassificationEngine:
    """Classifies outage evidence and scope."""

    def __init__(self):
        self.evidence_inputs = {
            "gateway_packet_loss": False,
            "external_packet_loss": False,
            "multiple_external_endpoints": 0,
            "dns_failure": False,
            "https_failure": False,
            "ethernet_vs_wifi": "unknown",
            "public_ip_change": False,
        }

    def record_evidence(self, key: str, value: bool | int) -> None:
        """Record evidence input for classification."""
        self.evidence_inputs[key] = value

    def classify_outage(
        self,
        duration_seconds: float,
        gateway_failed: bool,
        targets_affected: int,
    ) -> dict:
        """Classify outage based on evidence and scope."""
        classification = {
            "evidence_confidence": "unknown",
            "classification": "unknown",  # local-only, likely-upstream, probable-upstream, upstream-confirmed, endpoint-specific
            "reasoning": [],
            "upstream_failure_probable": False,
        }

        # Rule 1: Gateway failed = local/Wi-Fi issue, not ISP
        if gateway_failed:
            classification["evidence_confidence"] = "local-only"
            classification["classification"] = "local-wifi-issue"
            classification["reasoning"].append(
                f"Gateway unreachable → likely local Wi-Fi/LAN or access-point issue",
            )

        # Rule 2: Multiple external targets fail while gateway is stable = upstream issue
        elif self.evidence_inputs["external_packet_loss"]:
            if targets_affected >= self._config["required_targets_for_upstream_failure"]:
                classification["evidence_confidence"] = "probable-upstream"
                classification["classification"] = "likely-upstream"
                classification["reasoning"].append(
                    f"Gateway reachable; {targets_affected} independent Internet targets unreachable → upstream/property network issue",
                )
            else:
                classification["evidence_confidence"] = "local-only"
                classification["classification"] = "endpoint-specific-failure"
                classification["reasoning"].append(
                    f"Only {targets_affected} of required targets failed",
                )

        # Rule 3: DNS failure + other failures suggests upstream
        elif self.evidence_inputs["dns_failure"]:
            if self.evidence_inputs["https_failure"]:
                classification["evidence_confidence"] = "probable-upstream"
                classification["classification"] = "likely-upstream"
                classification["reasoning"].append(
                    "DNS and HTTPS failures suggest upstream connectivity issue",
                )
            else:
                classification["evidence_confidence"] = "local-only"
                classification["classification"] = "dns-specific-issue"
                classification["reasoning"].append("Only DNS failed; other paths may work")

        # Rule 4: Multiple independent endpoints fail simultaneously = strong upstream evidence
        elif self.evidence_inputs["multiple_external_endpoints"] >= 2:
            classification["evidence_confidence"] = "probable-upstream"
            classification["classification"] = "likely-upstream"
            classification["reasoning"].append(
                f"{self.evidence_inputs['multiple_external_endpoints']} independent endpoints affected",
            )

        # Rule 5: Single endpoint failure without gateway issue
        else:
            classification["evidence_confidence"] = "insufficient-evidence"
            classification["classification"] = "endpoint-specific-failure"
            classification["reasoning"].append(
                "Single endpoint failed; may be target-specific",
            )

        return classification

    def clear_evidence(self) -> None:
        """Clear evidence inputs for next outage."""
        self.evidence_inputs = {
            "gateway_packet_loss": False,
            "external_packet_loss": False,
            "multiple_external_endpoints": 0,
            "dns_failure": False,
            "https_failure": False,
            "ethernet_vs_wifi": "unknown",
            "public_ip_change": False,
        }

    # Configurable rules (exposed for customization)
    _config = {
        "required_targets_for_upstream_failure": 2,
    }
