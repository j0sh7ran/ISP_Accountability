// Renders the historical graphs page's Chart.js line charts from the /api/timeseries/ endpoint.
(function () {
    const script = document.currentScript;
    const range = script.dataset.range || '24h';
    const family = script.dataset.family && script.dataset.family !== 'all' ? script.dataset.family : '';
    const customStart = script.dataset.start || '';
    const customEnd = script.dataset.end || '';

    const METRICS = ['latency_ms', 'packet_loss_pct', 'jitter_ms', 'dns_resolution_ms'];

    // Short/long range: show time-of-day; long range: show the date instead.
    function formatTick(iso) {
        const d = new Date(iso);
        if (range === '7d' || range === '30d') {
            return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        }
        return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    }

    function loadMetric(metric) {
        const params = new URLSearchParams({ metric, range });
        if (family) params.set('family', family);
        if (range === 'custom' && customStart && customEnd) {
            params.set('start', new Date(customStart).toISOString());
            params.set('end', new Date(customEnd).toISOString());
        }
        fetch(`/api/timeseries/?${params.toString()}`)
            .then((response) => response.json())
            .then((data) => {
                const canvas = document.getElementById(`chart-${metric}`);
                if (!canvas) return;
                const labels = data.points.map((p) => p.timestamp);
                new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels,
                        datasets: [{
                            label: metric,
                            data: data.points.map((p) => p.value),
                            borderColor: '#4f6df5',
                            backgroundColor: 'rgba(79, 109, 245, 0.08)',
                            fill: true,
                            borderWidth: 1.5,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointHitRadius: 12,
                            tension: 0.15,
                        }],
                    },
                    options: {
                        animation: false,
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    title: (items) => (items.length ? new Date(items[0].label).toLocaleString() : ''),
                                },
                            },
                        },
                        scales: {
                            x: {
                                display: true,
                                ticks: {
                                    maxTicksLimit: 8,
                                    autoSkip: true,
                                    callback: function (value) {
                                        const label = this.getLabelForValue(value);
                                        return label ? formatTick(label) : label;
                                    },
                                },
                            },
                            y: { display: true, beginAtZero: true },
                        },
                    },
                });
            })
            .catch(() => { /* leave the canvas blank if this metric has no data yet */ });
    }

    METRICS.forEach(loadMetric);
})();

