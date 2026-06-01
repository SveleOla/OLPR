function showSubTab(name) {
  ['logg','kjente','statistikk','innstillinger'].forEach(t => {
    document.getElementById('sub-' + t).classList.add('hidden');
    document.getElementById('btn-sub-' + t).classList.remove('sub-active');
  });
  document.getElementById('sub-' + name).classList.remove('hidden');
  document.getElementById('btn-sub-' + name).classList.add('sub-active');
  const url = new URL(window.location);
  url.searchParams.set('sub', name);
  history.replaceState(null, '', url);
  if (name === 'logg') {
    if (typeof updateLogg === 'function') updateLogg();
    if (typeof updateUkjente === 'function') updateUkjente();
    if (typeof updateEvents24h === 'function') updateEvents24h();
  }
  if (name === 'statistikk') {
    if (typeof updateStatistikk === 'function') updateStatistikk();
  }
  if (name === 'innstillinger') {
    if (typeof loadSkiltSettings === 'function') loadSkiltSettings();
  }
}

function showTab(name) {
  ['skiltgjenkjenning','innstillinger','dok'].forEach(t => {
    document.getElementById(t).classList.add('hidden');
    document.getElementById('btn-' + t).classList.remove('active');
  });
  // Tilbakestill underfaner når vi forlater skiltgjenkjenning
  ['logg','kjente','statistikk','innstillinger'].forEach(t => {
    const el = document.getElementById('sub-' + t);
    if (el) el.classList.add('hidden');
  });
  document.getElementById(name).classList.remove('hidden');
  document.getElementById('btn-' + name).classList.add('active');
  const _url = new URL(window.location);
  _url.searchParams.set('tab', name);
  history.replaceState(null, '', _url);
  if (name === 'skiltgjenkjenning') showSubTab('logg');
  if (name === 'innstillinger') { if (typeof loadSettingsPage === 'function') loadSettingsPage(); }
  if (name === 'dok') { if (typeof loadDocs === 'function') loadDocs(); }
}

const params  = new URLSearchParams(window.location.search);
const initTab = params.get('tab');
const initSub = params.get('sub') || 'logg';
if (initTab && ['skiltgjenkjenning','innstillinger','dok'].includes(initTab)) {
  window.addEventListener('DOMContentLoaded', () => {
    showTab(initTab);
    if (initTab === 'skiltgjenkjenning') showSubTab(initSub);
  });
} else {
  window.addEventListener('DOMContentLoaded', () => showSubTab('logg'));
}

const showAll = params.get('all') === '1';
setInterval(() => {
  const onLogg = document.getElementById('sub-logg') && !document.getElementById('sub-logg').classList.contains('hidden') && !document.getElementById('skiltgjenkjenning').classList.contains('hidden');
  if (onLogg && !showAll && !document.querySelector('input:focus')) {
    if (typeof updateLogg === 'function') updateLogg();
  }
}, 30000);

function setBar(id, pct) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.width = pct + '%';
  el.style.backgroundColor = pct > 85 ? '#c0392b' : '#3a7bd5';
}

function updateDashboard() {
  fetch('/api/status')
    .then(r => r.json())
    .then(d => {
      document.getElementById('stat-load').textContent = d.load;
      document.getElementById('stat-ram').textContent  = d.ram;
      document.getElementById('stat-disk').textContent = d.disk;
      setBar('bar-ram',  d.ram_pct);
      setBar('bar-disk', d.disk_pct);
    })
    .catch(() => {});
}

function updateStorm() {
  fetch('/api/storm')
    .then(r => r.json())
    .then(d => {
      const banner = document.getElementById('storm-banner');
      if (d.storm === 1) {
        banner.classList.add('active');
      } else {
        banner.classList.remove('active');
      }
    })
    .catch(() => {});
}

window.addEventListener('DOMContentLoaded', updateDashboard);
window.addEventListener('DOMContentLoaded', updateStorm);
setInterval(updateDashboard, 15000);
setInterval(updateStorm, 3000);
