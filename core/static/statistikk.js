let statCharts = {};

function destroyCharts() {
  Object.values(statCharts).forEach(c => c.destroy());
  statCharts = {};
}

function updateStatistikk() {
  fetch('/api/statistikk')
    .then(r => r.json())
    .then(d => {
      if (!d.total) return;
      destroyCharts();

      document.getElementById('stat-total').textContent      = d.total;
      document.getElementById('stat-unike').textContent      = d.unike;
      document.getElementById('stat-ukjente').textContent    = d.ukjente_count;

      // Top 5
      document.getElementById('stat-top5-body').innerHTML = d.top5.map(v =>
        `<tr><td><b>${v.plate}</b></td><td>${v.navn}</td>
         <td>${v.count}</td><td>${v.last.slice(0,10)}</td>
         <td>${v.avg_days ? 'hver ' + v.avg_days + ' dag' : '–'}</td>
         <td>${(v.top_hours||[]).map(h=>h+':00').join(' / ')||'–'}</td></tr>`
      ).join('');

      // Daglig graf
      const dCtx = document.getElementById('chart-daily').getContext('2d');
      statCharts.daily = new Chart(dCtx, {
        type: 'bar',
        data: {
          labels: d.daily.map(x => x.label),
          datasets: [
            { label: 'Unike', data: d.daily.map(x => x.unique),
              backgroundColor: cssVar('--accent'), borderRadius: 3 },
            { label: 'Totalt', data: d.daily.map(x => x.total),
              backgroundColor: cssVarA('--accent', 0.30), borderRadius: 3 },
          ]
        },
        options: { responsive: true,
          plugins: { legend: { labels: { color: cssVar('--text-dim') } } },
          scales: { x: { ticks: { color: cssVar('--muted'), maxRotation: 45 } },
                    y: { ticks: { color: cssVar('--muted') }, beginAtZero: true } } }
      });

      // Ukedag
      const wCtx = document.getElementById('chart-weekday').getContext('2d');
      statCharts.weekday = new Chart(wCtx, {
        type: 'bar',
        data: {
          labels: d.weekday.map(x => x.day),
          datasets: [{ label: 'Passeringer', data: d.weekday.map(x => x.count),
            backgroundColor: cssVarA('--green', 0.60), borderRadius: 3 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { ticks: { color: cssVar('--muted') } },
                    y: { ticks: { color: cssVar('--muted') }, beginAtZero: true } } }
      });

      // Timefordeling
      const hCtx = document.getElementById('chart-hourly').getContext('2d');
      statCharts.hourly = new Chart(hCtx, {
        type: 'bar',
        data: {
          labels: d.hourly.map(x => x.hour),
          datasets: [{ label: 'Passeringer', data: d.hourly.map(x => x.count),
            backgroundColor: cssVarA('--accent-2', 0.60), borderRadius: 2 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { ticks: { color: cssVar('--muted'), font: { size: 10 } } },
                    y: { ticks: { color: cssVar('--muted') }, beginAtZero: true } } }
      });

      // Alle besøkende
      window._alleData = d.vehicle_stats;
      window._alleSort = {col: 'count', asc: false};
      renderAlle();
    })
    .catch(() => {});
}




function renderAlle() {
  const data = [...(window._alleData || [])];
  const {col, asc} = window._alleSort;
  data.sort((a, b) => {
    let va = a[col], vb = b[col];
    const nullA = va === null || va === undefined;
    const nullB = vb === null || vb === undefined;
    if (nullA && nullB) return 0;
    if (nullA) return 1;
    if (nullB) return -1;
    if (typeof va === 'string') return asc ? va.localeCompare(vb) : vb.localeCompare(va);
    return asc ? va - vb : vb - va;
  });
  document.getElementById('stat-alle-body').innerHTML = data.map(v =>
    `<tr><td><b>${v.plate}</b></td><td>${v.navn}</td>
     <td>${v.count}</td>
     <td>${v.avg_days ? 'hver ' + v.avg_days + ' dag' : '–'}</td>
     <td>${(v.top_hours||[]).map(h=>h+':00').join(' / ') || '–'}</td></tr>`
  ).join('');
}

function sortAlle(col) {
  if (!window._alleSort) return;
  if (window._alleSort.col === col) {
    window._alleSort.asc = !window._alleSort.asc;
  } else {
    // avg_days: lav = hyppig = øverst = ascending som standard
    window._alleSort.asc = (col === 'avg_days');
  }
  window._alleSort.col = col;
  renderAlle();
}
