// Polls the overview API and refreshes the state banner, ICMP table, and live job status grid in
// place — near real-time without a full page reload (see docs/ARCHITECTURE.md non-blocking design).
(function () {
    const script = document.currentScript;
    const family = script.dataset.family && script.dataset.family !== 'all' ? script.dataset.family : '';
    const POLL_MS = 5000;

    function badgeClass(status) {
        if (status === 'ok') return 'badge-ok';
        if (status === 'overdue' || status === 'error') return 'badge-danger';
        if (status === 'pending') return 'badge-info';
        return 'badge-muted';
    }

    function renderJobCard(job) {
        const lastRun = job.last_run ? `${Math.round(job.seconds_since_last_run)}s ago` : 'never';
        const recent = job.recent_count !== null && job.recent_count !== undefined
            ? `<strong>${job.recent_count}</strong> recent sample(s)${job.error_count ? `, <strong>${job.error_count}</strong> errored` : ''}`
            : '';
        return `
            <div class="job-card" data-task-type="${job.task_type}">
                <div class="job-card-header">
                    <span class="job-name">${job.label}</span>
                    <span class="badge job-status-badge ${badgeClass(job.status)}" data-status="${job.status}">${job.status}</span>
                </div>
                <div class="job-meta job-last-run">Last run: <strong>${lastRun}</strong></div>
                <div class="job-meta">Every ${job.interval_seconds}s</div>
                <div class="job-meta job-recent-count">${recent}</div>
            </div>
        `;
    }

    function refresh() {
        const url = '/api/overview/' + (family ? `?family=${encodeURIComponent(family)}` : '');
        fetch(url)
            .then((response) => response.json())
            .then((data) => {
                const stateValue = document.getElementById('state-value');
                const uptimeValue = document.getElementById('uptime-value');
                const banner = document.getElementById('state-banner');
                const activeIncidentValue = document.getElementById('active-incident-value');
                const slaViolationValue = document.getElementById('sla-violation-value');
                if (stateValue) stateValue.textContent = data.state.toUpperCase();
                if (uptimeValue && data.uptime_pct !== null) uptimeValue.textContent = data.uptime_pct.toFixed(2);
                if (banner) banner.className = `state-banner state-${data.state}`;
                if (activeIncidentValue) activeIncidentValue.textContent = data.active_incident_count;
                if (slaViolationValue) slaViolationValue.textContent = data.sla_violation_count;

                const tbody = document.querySelector('#icmp-table tbody');
                if (tbody && data.targets.length) {
                    tbody.innerHTML = data.targets.map((t) => `
                        <tr>
                            <td>${t.name}</td>
                            <td>${t.address}</td>
                            <td>${t.loss_pct ?? '—'}</td>
                            <td>${t.avg_rtt_ms !== null ? t.avg_rtt_ms.toFixed(1) : '—'}</td>
                            <td>${t.timestamp ?? 'no data yet'}</td>
                        </tr>
                    `).join('');
                }

                const jobGrid = document.getElementById('job-grid');
                if (jobGrid && data.jobs) {
                    jobGrid.innerHTML = data.jobs.map(renderJobCard).join('');
                }

                const updated = document.getElementById('jobs-updated');
                if (updated) updated.textContent = 'just now';
            })
            .catch(() => { /* transient fetch failures are expected if the worker is briefly behind */ });
    }

    refresh();
    setInterval(refresh, POLL_MS);
})();

