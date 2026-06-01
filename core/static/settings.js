const SETTINGS_SCHEMA = [
  {
    key: 'system', label: 'System', icon: '🏠',
    restart: null, restartLabel: 'Lagre',
    fields: [
      { key: 'name', label: 'System-navn', type: 'text',
        tip: 'Navnet som vises i nettleserfanen og øverst på siden.' },
      { key: 'frigate_url', label: 'Frigate URL', type: 'text',
        tip: 'Nettadressen til Frigate NVR-grensesnittet.' },
      { key: 'portainer_url', label: 'Portainer URL', type: 'text',
        tip: 'Nettadressen til Portainer Docker-administrasjon.' },
    ]
  },
  {
    key: 'mqtt', label: 'MQTT', icon: '📡',
    restart: 'lpr-bridge', restartLabel: 'Lagre & restart LPR-bridge',
    fields: [
      { key: 'result_topic', label: 'Resultat-topic', type: 'text',
        tip: 'MQTT-topic for kjøretøynavn. Bruk {camera} som plassholder.' },
      { key: 'plate_topic', label: 'Skilt-topic', type: 'text',
        tip: 'MQTT-topic for skiltnummer. Bruk {camera} som plassholder.' },
    ]
  },
  {
    key: 'web', label: 'Dashboard', icon: '🖥️',
    restart: null, restartLabel: 'Lagre',
    fields: [
      { key: 'max_log_lines', label: 'Maks logglinjer', type: 'number', min: 100, max: 10000, step: 100,
        tip: 'Maks antall linjer som vises i LPR-loggen.' },
      { key: 'stats_refresh_sec', label: 'Server-refresh (sek)', type: 'number', min: 5, max: 60, step: 5,
        tip: 'Hvor ofte server-statistikk oppdateres. Trer i kraft ved neste sideinnlasting.' },
    ]
  }
];

let currentSettings = {};

function loadSettingsPage() {
  fetch('/api/settings')
    .then(r => r.json())
    .then(data => { currentSettings = data; renderSettings(data); })
    .catch(() => {});
}

function renderSettingsFieldInput(section, field, val) {
  const id = `s-${section}-${field.key}`;
  if (field.type === 'boolean')
    return `<label class="toggle-label"><input type="checkbox" id="${id}" ${val ? 'checked' : ''}><span class="toggle-slider"></span></label>`;
  if (field.type === 'text')
    return `<input type="text" id="${id}" value="${val||''}" class="settings-input" style="width:200px">`;
  if (field.type === 'password')
    return `<input type="password" id="${id}" value="${val||''}" class="settings-input" style="width:200px">`;
  if (field.type === 'select')
    return `<select id="${id}" class="settings-input" style="width:160px">${(field.options||[]).map(o=>`<option value="${o.value}" ${val===o.value?'selected':''}>${o.label}</option>`).join('')}</select>`;
  return `<input type="number" id="${id}" value="${val??''}" min="${field.min}" max="${field.max}" step="${field.step}" class="settings-input">`;
}

function getFieldValue(section, field) {
  const el = document.getElementById(`s-${section}-${field.key}`);
  if (!el) return currentSettings[section]?.[field.key] ?? null;
  if (field.type === 'boolean') return el.checked;
  if (field.type === 'number') return parseFloat(el.value);
  return el.value;
}

function renderSettings(data) {
  const container = document.getElementById('settings-container');
  if (!container) return;
  container.innerHTML = SETTINGS_SCHEMA.map(section => {
    const sData = data[section.key] || {};
    const fields = section.fields.map(field => `
      <div class="settings-field">
        <div class="settings-field-label">${field.label}<span class="settings-tip" data-tip="${field.tip}">?</span></div>
        <div class="settings-field-input">${renderSettingsFieldInput(section.key, field, sData[field.key])}</div>
      </div>`).join('');
    const warning = section.restart ? `<div class="settings-restart-warning">⚠️ Lagring restarter ${section.restart}</div>` : '';
    return `<div class="settings-section card">
      <h2>${section.icon} ${section.label}</h2>
      ${fields}${warning}
      <div class="settings-actions">
        <button onclick="saveSection('${section.key}')" class="settings-save-btn">${section.restartLabel}</button>
        <span id="status-${section.key}" class="settings-status"></span>
      </div>
    </div>`;
  }).join('');
}

function saveSection(sectionKey) {
  const section = SETTINGS_SCHEMA.find(s => s.key === sectionKey);
  if (!section) return;
  const sectionData = {};
  section.fields.forEach(field => { sectionData[field.key] = getFieldValue(sectionKey, field); });
  const newSettings = { ...currentSettings, [sectionKey]: sectionData };
  const statusEl = document.getElementById(`status-${sectionKey}`);
  if (statusEl) statusEl.textContent = 'Lagrer...';
  fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newSettings)
  }).then(r => r.json()).then(d => {
    currentSettings = newSettings;
    if (statusEl) {
      const r = d.restarted && d.restarted.length ? ` (${d.restarted.join(', ')} restartet)` : '';
      statusEl.textContent = '✅ Lagret' + r;
      setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 4000);
    }
  }).catch(() => { if (statusEl) statusEl.textContent = '❌ Feil'; });
}
