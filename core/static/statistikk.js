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
              backgroundColor: '#3a7bd5', borderRadius: 3 },
            { label: 'Totalt', data: d.daily.map(x => x.total),
              backgroundColor: '#1a3a6a', borderRadius: 3 },
          ]
        },
        options: { responsive: true,
          plugins: { legend: { labels: { color: '#aac8ff' } } },
          scales: { x: { ticks: { color: '#4a6a8a', maxRotation: 45 } },
                    y: { ticks: { color: '#4a6a8a' }, beginAtZero: true } } }
      });

      // Ukedag
      const wCtx = document.getElementById('chart-weekday').getContext('2d');
      statCharts.weekday = new Chart(wCtx, {
        type: 'bar',
        data: {
          labels: d.weekday.map(x => x.day),
          datasets: [{ label: 'Passeringer', data: d.weekday.map(x => x.count),
            backgroundColor: '#2a6a4a', borderRadius: 3 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { ticks: { color: '#4a6a8a' } },
                    y: { ticks: { color: '#4a6a8a' }, beginAtZero: true } } }
      });

      // Timefordeling
      const hCtx = document.getElementById('chart-hourly').getContext('2d');
      statCharts.hourly = new Chart(hCtx, {
        type: 'bar',
        data: {
          labels: d.hourly.map(x => x.hour),
          datasets: [{ label: 'Passeringer', data: d.hourly.map(x => x.count),
            backgroundColor: '#6a3a7a', borderRadius: 2 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } },
          scales: { x: { ticks: { color: '#4a6a8a', font: { size: 10 } } },
                    y: { ticks: { color: '#4a6a8a' }, beginAtZero: true } } }
      });

      // Alle besøkende
      window._alleData = d.vehicle_stats;
      window._alleSort = {col: 'count', asc: false};
      renderAlle();
      renderHjemme(d.hjemme_stats);
    })
    .catch(() => {});
}


function renderHjemme(stats) {
  const el = document.getElementById('stat-hjemme-body');
  if (!el) return;
  if (!stats || !stats.length) {
    el.innerHTML = '<tr><td colspan="5" style="color:#666">Ingen data</td></tr>';
    return;
  }
  el.innerHTML = stats.map(v =>
    `<tr><td><b>${v.plate}</b></td><td>${v.navn}</td>
     <td>${v.count}</td>
     <td>${v.avg_days ? 'hver ' + v.avg_days + ' dag' : '–'}</td>
     <td>${(v.top_hours||[]).map(h=>h+':00').join(' / ')||'–'}</td></tr>`
  ).join('');
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
