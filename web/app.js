// ISP Accountability Monitor - Dashboard client-side JavaScript

const API_BASE = window.location.origin;

// Fetch current status
async function fetchStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data = await response.json();

        // Update gateway status
        const gwEl = document.getElementById('gatewayStatus');
        if (data.latest_icmp_measurement) {
            gwEl.textContent = `${data.latest_icmp_measurement.success ? 'OK' : 'FAIL'} • ${data.latest_icmp_measurement.rtt_ms || 0}ms`;
            gwEl.className = `metric-value ${data.latest_icmp_measurement.success ? 'success' : 'critical'}`;
        } else {
            gwEl.textContent = 'N/A';
        }

        // Update external status
        const extEl = document.getElementById('externalStatus');
        if (data.latest_icmp_measurement && !data.latest_icmp_measurement.success) {
            extEl.textContent = 'UNREACHABLE';
            extEl.className = 'metric-value critical';
        } else if (data.latest_icmp_measurement) {
            extEl.textContent = 'OK';
            extEl.className = 'metric-value success';
        }

        // Update DNS status
        const dnsEl = document.getElementById('dnsStatus');
        dnsEl.textContent = data.latest_icmp_measurement ? 'OK' : 'Unknown';
        dnsEl.className = 'metric-value success';

        // Update interface type
        const ifaceEl = document.getElementById('interfaceType');
        ifaceEl.textContent = data.latest_icmp_measurement?.interface_type || 'Unknown';

        // Update status indicator
        const statusIndicator = document.getElementById('statusIndicator');
        if (data.current_outage) {
            statusIndicator.className = 'status-indicator status-outage';
            document.getElementById('statusText').textContent = `Outage: ${formatDuration(data.current_outage.duration_seconds || 0)}`;
        } else {
            statusIndicator.className = 'status-indicator status-healthy';
            document.getElementById('statusText').textContent = 'Monitoring Active';
        }

        // Load outages
        loadOutages();

    } catch (error) {
        console.error('Status fetch error:', error);
    }
}

// Fetch and display outages
async function loadOutages() {
    try {
        const response = await fetch(`${API_BASE}/api/outages?limit=10`);
        const data = await response.json();

        const outageList = document.getElementById('outageList');

        if (data.outages.length === 0) {
            outageList.innerHTML = '<div class="loading">No outages detected</div>';
            return;
        }

        let html = '';
        for (const outage of data.outages) {
            const severityClass = outage.severity || 'minor';
            const formattedStart = new Date(outage.start_timestamp_utc).toLocaleString();

            html += `
                <div class="outage-item ${severityClass}">
                    <div class="outage-header">
                        <span>Start: ${formattedStart}</span>
                        <span class="outage-duration">${formatDuration(outage.duration_seconds || 0)}</span>
                    </div>
                    <div class="outage-severity">${outage.severity || 'Minor'}</div>
                    <div class="outage-details">
                        ${outage.classification_reason || ''}
                    </div>
                </div>
            `;
        }

        outageList.innerHTML = html;

    } catch (error) {
        console.error('Outages fetch error:', error);
    }
}

// Manual test trigger
async function triggerProbes() {
    try {
        // Trigger gateway probe
        const response = await fetch(`${API_BASE}/api/probe/gateway`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            console.log('Gateway probe result:', data.result);
            alert(`Gateway probe complete: ${data.result.success ? 'OK' : 'Failed'} - ${data.result.error_message || ''}`);
        }

    } catch (error) {
        console.error('Probe trigger error:', error);
    }
}

// Generate report
async function generateReport() {
    try {
        const now = new Date();
        const start = new Date(now - 30 * 24 * 60 * 60 * 1000); // 30 days ago

        const response = await fetch(`${API_BASE}/api/report?period_start=${encodeURIComponent(start.toISOString())}&period_end=${encodeURIComponent(now.toISOString())}`);
        const data = await response.json();

        if (data.report_generated) {
            console.log('Report:', data);

            // In a full implementation, we'd generate PDF here
            alert(`Report generated:\n- Period: ${data.period.start} to ${data.period.end}\n- Total Outages: ${data.summary.total_outages}\n- Total Downtime: ${formatDuration(data.summary.total_duration_seconds)}`);

            // Download as JSON (simplified - full implementation would generate PDF)
            downloadReportJSON(data);

        }

    } catch (error) {
        console.error('Report generation error:', error);
    }
}

// Download report as JSON
function downloadReportJSON(data) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sla-report-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
}

// Format duration in human-readable format
function formatDuration(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    return `${Math.round(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
}

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async () => {
    // Poll status every 5 seconds
    setInterval(fetchStatus, 5000);

    // Initial fetch
    await fetchStatus();
});
