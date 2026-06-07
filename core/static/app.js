function showSubTab(name) {
  ['logg','kjente','statistikk','innstillinger','dok'].forEach(t => {
    const _el = document.getElementById('sub-' + t);
    const _btn = document.getElementById('btn-sub-' + t);
    if (_el) _el.classList.add('hidden');
    if (_btn) _btn.classList.remove('sub-active');
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
  if (name === 'kjente') {
    updateKjenteBiler();
  }
  if (name === 'innstillinger') {
    if (typeof loadSkiltSettings === 'function') loadSkiltSettings();
    if (typeof loadSettingsPage === 'function') loadSettingsPage();
  }
  if (name === 'dok') {
    if (typeof loadDocs === 'function') loadDocs();
  }
}

function updateKjenteBiler() {
  fetch('/api/kjente')
    .then(r => r.json())
    .then(data => {
      const tbody = document.getElementById('kjente-tbody');
      if (!tbody) return;
      const btn = document.getElementById('btn-sub-kjente');
      if (btn) btn.textContent = `Kjente biler (${data.length})`;
      let html = `<tr class="add-row"><td colspan="3">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="text" id="ny-plate" placeholder="AB12345" style="text-transform:uppercase;width:110px;">
          <input type="text" id="ny-navn" placeholder="Eier / kallenavn" style="flex:1;min-width:140px;">
          <button onclick="kjenteLeggTilNy()">+ Legg til</button>
          <span id="ny-status" style="font-size:12px;color:#80c880"></span>
        </div></td></tr>`;
      data.forEach(({plate, name}) => {
        const safePlate = plate.replace(/'/g, "\\'");
        const safeName  = name.replace(/'/g, "\\'");
        html += `<tr>
          <td><b>${plate}</b></td>
          <td style="display:flex;gap:6px;align-items:center;">
            <input type="text" id="edit-${plate}" value="${name}" style="flex:1;">
            <button onclick="kjenteLagreRad('${safePlate}')">Lagre</button>
          </td>
          <td><button class="del" onclick="kjenteSlettRad('${safePlate}','${safeName}')">Slett</button></td>
        </tr>`;
      });
      tbody.innerHTML = html;
    })
    .catch(() => {});
}

function kjenteLeggTilNy() {
  const plateEl = document.getElementById('ny-plate');
  const navnEl  = document.getElementById('ny-navn');
  const status  = document.getElementById('ny-status');
  const plate = plateEl?.value?.trim().toUpperCase();
  const name  = navnEl?.value?.trim();
  if (!plate || !name) return;
  fetch('/api/kjente', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'add', plate, name})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      if (plateEl) plateEl.value = '';
      if (navnEl)  navnEl.value  = '';
      if (status)  { status.textContent = '✅ Lagt til'; setTimeout(() => { status.textContent = ''; }, 2000); }
      updateKjenteBiler();
    }
  }).catch(() => {});
}

function kjenteLagreRad(plate) {
  const name = document.getElementById('edit-' + plate)?.value?.trim();
  if (!name) return;
  fetch('/api/kjente', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'edit', plate, name})
  }).then(r => r.json()).then(d => {
    if (d.ok) updateKjenteBiler();
  }).catch(() => {});
}

function kjenteSlettRad(plate, name) {
  if (!confirm(`Slette ${plate} (${name})?`)) return;
  fetch('/api/kjente', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'delete', plate})
  }).then(r => r.json()).then(d => {
    if (d.ok) updateKjenteBiler();
  }).catch(() => {});
}

function showTab(name) {
  showSubTab(name);
}

const params  = new URLSearchParams(window.location.search);
const initSub = params.get('sub') || 'statistikk';
const validSubs = ['logg','kjente','statistikk','innstillinger','dok'];
window.addEventListener('DOMContentLoaded', () => {
  showSubTab(validSubs.includes(initSub) ? initSub : 'statistikk');
});

const showAll = params.get('all') === '1';
setInterval(() => {
  const onLogg = document.getElementById('sub-logg') && !document.getElementById('sub-logg').classList.contains('hidden');
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
