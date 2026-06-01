const LPR_SCHEMA = {
  key: 'lpr', label: 'LPR-innstillinger', icon: '🔍',
  restart: 'lpr-bridge', restartLabel: 'Lagre & restart LPR-bridge',
  fields: [
    { key: 'confidence_threshold', label: 'Konfidens-terskel', type: 'number', min: 0.1, max: 1.0, step: 0.05,
      tip: 'Minimum andel stemmer som må peke på samme skilt (0.0–1.0). 0.8 = 80% av stemmene må stemme overens.' },
    { key: 'gpt_enabled', label: 'GPT – global av/på', type: 'boolean',
      tip: 'Masterbryter for GPT på hele systemet. Overstyrer per-kamera GPT-innstillinger – skrur av GPT på alle kameraer samtidig.' },
    { key: 'gpt_model', label: 'GPT-modell', type: 'select',
      options: [{value:'gpt-4o', label:'gpt-4o (best kvalitet)'}, {value:'gpt-4o-mini', label:'gpt-4o-mini (raskere/billigere)'}],
      tip: 'GPT-modell brukt til skiltlesing. gpt-4o-mini er billigere men noe dårligere på vanskelige bilder.' },
    { key: 'openai_api_key', label: 'OpenAI API-nøkkel', type: 'password',
      tip: 'API-nøkkel fra platform.openai.com. Brukes for GPT-fallback.' },
    { key: 'mqtt_host', label: 'MQTT host', type: 'text',
      tip: 'IP-adresse eller hostname til MQTT-brokeren. Vanligvis 127.0.0.1 for lokal Mosquitto.' },
    { key: 'mqtt_port', label: 'MQTT port', type: 'number', min: 1, max: 65535, step: 1,
      tip: 'Port til MQTT-brokeren. Standard er 1883.' },
    { key: 'wait_seconds', label: 'Ventetid (sek)', type: 'number', min: 5, max: 60, step: 1,
      tip: 'Maks ventetid fra bil detekteres til GPT-fallback trigges.' },
    { key: 'reset_seconds', label: 'Reset-tid (sek)', type: 'number', min: 1, max: 30, step: 1,
      tip: 'Antall sekunder etter publisering før MQTT-topicen nullstilles.' },
    { key: 'commit_window', label: 'Commit-vindu (sek)', type: 'number', min: 0.5, max: 5.0, step: 0.5,
      tip: 'Antall sekunder å vente på flere stemmer etter siste LPR-lesing.' },
    { key: 'snapshot_delay', label: 'Snapshot-forsinkelse (sek)', type: 'number', min: 0.5, max: 5.0, step: 0.5,
      tip: 'Antall sekunder etter bildeteksjon før snapshot tas.' },
    { key: 'snapshot_retention_days', label: 'Snapshot-retensjon (dager)', type: 'number', min: 7, max: 365, step: 1,
      tip: 'Antall dager snapshots lagres på disk.' },
  ]
};

let skiltSettings = {};
let cameras = [];
let systemName = 'olpr';
let editingCamera = null;

const CAM_FIELDS = [
  { key: 'display_name', label: 'Visningsnavn',  type: 'text', tip: 'Navnet som vises i dashboardet.' },
  { key: 'name',         label: 'Internt navn',  type: 'text', tip: 'Teknisk navn brukt i Frigate config og MQTT. Kun bokstaver, tall og understrek.' },
  { key: 'ip',           label: 'IP-adresse',    type: 'text', tip: 'IP-adressen til kameraet på lokalt nettverk.' },
  { key: 'user',         label: 'RTSP bruker',   type: 'text', tip: 'Brukernavn for RTSP-tilkobling.' },
  { key: 'pass',         label: 'RTSP passord',  type: 'password', tip: 'Passord for RTSP-tilkobling.' },
  { key: 'main_path',    label: 'Hoved-sti',     type: 'text', tip: 'RTSP-sti for hovedstrøm (høy oppløsning, brukes til opptak og LPR).' },
  { key: 'sub_path',     label: 'Sub-sti',       type: 'text', tip: 'RTSP-sti for substrøm (lav oppløsning, brukes til deteksjon). La stå tom for kameraer som kun har én RTSP-strøm.' },
  { key: 'detect_stream', label: 'Detect-strøm', type: 'select',
    options: [
      { value: 'sub',  label: 'Substrøm' },
      { value: 'main', label: 'Hovedstrøm' },
    ],
    tip: 'H.264 støttes av all hardware. H.265 gir bedre kvalitet ved lavere båndbredde, men krever Intel 6th gen+ eller dedikert GPU for VAAPI-dekoding. Sjekk codec med Test-knappen.' },
  { key: 'width',        label: 'Bredde (px)',   type: 'number', min: 320, max: 3840, step: 1, tip: 'Deteksjonsoppløsning bredde. Hentes automatisk ved Test tilkobling.' },
  { key: 'height',       label: 'Høyde (px)',    type: 'number', min: 180, max: 2160, step: 1, tip: 'Deteksjonsoppløsning høyde. Hentes automatisk ved Test tilkobling.' },
  { key: 'fps',          label: 'FPS',           type: 'number', min: 1, max: 30, step: 1, tip: 'Bilder per sekund for deteksjon. Hentes automatisk ved Test tilkobling.' },
];

function loadSkiltSettings() {
  Promise.all([
    fetch('/api/settings').then(r => r.json()),
    fetch('/api/cameras').then(r => r.json())
  ]).then(([settings, cams]) => {
    skiltSettings = settings;
    cameras = cams;
    systemName = (settings.system?.name || 'olpr').toLowerCase().replace(/ /g, '-');
    renderLPRSettings(settings);
    renderCameras();
  }).catch(() => {});
}

function renderFieldInput(key, field, val) {
  const id = `lpr-${key}`;
  if (field.type === 'boolean')
    return `<label class="toggle-label"><input type="checkbox" id="${id}" ${val ? 'checked' : ''}><span class="toggle-slider"></span></label>`;
  if (field.type === 'camera_select')
    return `<select id="${id}" class="settings-input" style="width:160px">${cameras.map(c=>`<option value="${c.name}" ${val===c.name?'selected':''}>${c.display_name}</option>`).join('')}</select>`;
  if (field.type === 'select')
    return `<select id="${id}" class="settings-input" style="width:200px">${(field.options||[]).map(o=>`<option value="${o.value}" ${val===o.value?'selected':''}>${o.label}</option>`).join('')}</select>`;
  if (field.type === 'text')
    return `<input type="text" id="${id}" value="${val||''}" class="settings-input" style="width:180px">`;
  if (field.type === 'password')
    return `<input type="password" id="${id}" value="${val||''}" class="settings-input" style="width:180px">`;
  return `<input type="number" id="${id}" value="${val??''}" min="${field.min}" max="${field.max}" step="${field.step}" class="settings-input">`;
}

function renderLPRSettings(data) {
  const el = document.getElementById('lpr-settings-section');
  if (!el) return;
  const sData = data['lpr'] || {};
  const fields = LPR_SCHEMA.fields.map(field => `
    <div class="settings-field">
      <div class="settings-field-label">${field.label}<span class="settings-tip" data-tip="${field.tip}">?</span></div>
      <div class="settings-field-input">${renderFieldInput(field.key, field, sData[field.key])}</div>
    </div>`).join('');
  el.innerHTML = `
    <h2>${LPR_SCHEMA.icon} ${LPR_SCHEMA.label}</h2>
    ${fields}
    <div class="settings-actions" style="margin-bottom:8px;">
      <button onclick="testGPT()">🤖 Test GPT</button>
      <span id="gpt-test-status" class="settings-status"></span>
    </div>
    <div class="settings-restart-warning">⚠️ Lagring restarter lpr-bridge</div>
    <div class="settings-actions">
      <button onclick="saveLPRSettings()" class="settings-save-btn">${LPR_SCHEMA.restartLabel}</button>
      <span id="lpr-status" class="settings-status"></span>
    </div>`;
}

function saveLPRSettings() {
  const sectionData = {};
  LPR_SCHEMA.fields.forEach(field => {
    const el = document.getElementById(`lpr-${field.key}`);
    if (!el) return;
    if (field.type === 'boolean') sectionData[field.key] = el.checked;
    else if (field.type === 'number') sectionData[field.key] = parseFloat(el.value);
    else sectionData[field.key] = el.value;
  });
  const newSettings = { ...skiltSettings, lpr: sectionData };
  const statusEl = document.getElementById('lpr-status');
  if (statusEl) statusEl.textContent = 'Lagrer...';
  fetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(newSettings)
  }).then(r => r.json()).then(() => {
    skiltSettings = newSettings;
    if (statusEl) {
      statusEl.textContent = '✅ Lagret (lpr-bridge restartet)';
      setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 4000);
    }
  }).catch(() => { if (statusEl) statusEl.textContent = '❌ Feil'; });
}

function renderCameras() {
  const el = document.getElementById('cameras-section');
  if (!el) return;
  const cards = cameras.map((cam, i) => `
    <div class="camera-card" id="cam-card-${i}">
      <div class="camera-card-header">
        <span class="camera-name">📷 ${cam.display_name || cam.name}</span>
        <span class="camera-ip">${cam.ip}</span>
      </div>
      <div class="camera-info">${cam.codec ? cam.codec.toUpperCase() : '?'} · ${cam.width}×${cam.height} · ${cam.fps} fps</div>
      <div class="camera-tags">
        ${cam.lpr ? '<span class="cam-tag cam-tag-lpr">LPR</span>' : ''}
        ${(cam.objects||[]).map(o => `<span class="cam-tag">${o}</span>`).join('')}
        ${cam.record ? '<span class="cam-tag cam-tag-rec">●REC</span>' : ''}
      </div>
      ${cam.lpr ? `<div class="cam-mqtt">
        <span class="cam-mqtt-label">MQTT</span>
        <code class="cam-mqtt-topic">${systemName}/${cam.name}/resultat</code>
        <button class="cam-copy-btn" onclick="copyTopic('${systemName}/${cam.name}/resultat', this)" title="Kopier">📋</button>
      </div>` : ''}
      <div class="camera-actions">
        <button onclick="testCamera(${i})">Test</button>
        <button onclick="editCamera(${i})">Rediger</button>
        <button class="del" onclick="deleteCamera(${i})">Slett</button>
      </div>
      <div id="cam-status-${i}" class="cam-test-result"></div>
    </div>`).join('');

  el.innerHTML = `
    <h2>📹 Kameraer</h2>
    <div class="camera-grid">${cards}</div>
    <button onclick="addCamera()" style="margin-top:12px">+ Legg til kamera</button>
    <div id="camera-edit-modal" class="camera-edit-modal hidden"></div>`;
}

function camFormField(field, val) {
  const id = `edit-${field.key}`;
  let input;
  if (field.type === 'select')
    input = `<select id="${id}" class="settings-input" style="width:200px">${(field.options||[]).map(o=>`<option value="${o.value}" ${val===o.value?'selected':''}>${o.label}</option>`).join('')}</select>`;
  else if (field.type === 'password')
    input = `<input type="password" id="${id}" value="${val||''}" class="settings-input" style="width:180px">`;
  else if (field.type === 'number')
    input = `<input type="number" id="${id}" value="${val??''}" min="${field.min}" max="${field.max}" step="${field.step}" class="settings-input">`;
  else
    input = `<input type="text" id="${id}" value="${val||''}" class="settings-input" style="width:180px">`;
  return `<div class="settings-field">
    <div class="settings-field-label">${field.label}<span class="settings-tip" data-tip="${field.tip}">?</span></div>
    <div class="settings-field-input">${input}</div>
  </div>`;
}

function editCamera(i) {
  editingCamera = i;
  const cam = cameras[i];
  const modal = document.getElementById('camera-edit-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  setTimeout(() => {
    const lprToggle = document.getElementById('edit-lpr');
    if (lprToggle) lprToggle.addEventListener('change', function() {
      const s = document.getElementById('gpt-section');
      if (s) { s.style.opacity = this.checked ? '1' : '0.4'; s.style.pointerEvents = this.checked ? '' : 'none'; }
    });
  }, 50);

  const fieldHtml = CAM_FIELDS.map(f => camFormField(f, cam[f.key])).join('');
  const objHtml = ['person','car','cat'].map(o =>
    `<label style="color:#a8c0e0;font-size:13px"><input type="checkbox" id="edit-obj-${o}" ${(cam.objects||[]).includes(o)?'checked':''}> ${o}</label>`
  ).join(' ');

  modal.innerHTML = `<div class="camera-edit-form card">
    <h2>✏️ ${cam.display_name || 'Nytt kamera'}</h2>
    ${fieldHtml}
    <div class="settings-field">
      <div class="settings-field-label">LPR aktivert<span class="settings-tip" data-tip="Aktiver skiltgjenkjenning for dette kameraet.">?</span></div>
      <label class="toggle-label"><input type="checkbox" id="edit-lpr" ${cam.lpr?'checked':''}><span class="toggle-slider"></span></label>
    </div>
    <div class="settings-field">
      <div class="settings-field-label">Opptak<span class="settings-tip" data-tip="Aktiver videoopptak for dette kameraet.">?</span></div>
      <label class="toggle-label"><input type="checkbox" id="edit-record" ${cam.record?'checked':''}><span class="toggle-slider"></span></label>
    </div>
    <div id="gpt-section" style="${cam.lpr ? '' : 'opacity:0.4;pointer-events:none'}">
      <div class="settings-field">
        <div class="settings-field-label">GPT fallback<span class="settings-tip" data-tip="Kjør GPT hvis Frigate ikke leser platen innen timeout.">?</span></div>
        <label class="toggle-label"><input type="checkbox" id="edit-gpt_enabled" ${cam.gpt_enabled?'checked':''}><span class="toggle-slider"></span></label>
      </div>
      <div class="settings-field">
        <div class="settings-field-label">GPT dobbeltsjekk<span class="settings-tip" data-tip="Kjør alltid GPT i tillegg til Frigate for å verifisere lesingen. Logger hvis de er uenige.">?</span></div>
        <label class="toggle-label"><input type="checkbox" id="edit-gpt_verify" ${cam.gpt_verify?'checked':''}><span class="toggle-slider"></span></label>
      </div>
    </div>
    <div class="settings-field">
      <div class="settings-field-label">Objekter<span class="settings-tip" data-tip="Velg hvilke objekttyper Frigate skal detektere på dette kameraet.">?</span></div>
      <div style="display:flex;gap:12px">${objHtml}</div>
    </div>
    <div style="margin-top:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <button onclick="testEditCamera()">🔌 Test tilkobling</button>
      <button onclick="saveEditCamera()" class="settings-save-btn">Lagre</button>
      <button onclick="closeEditCamera()">Avbryt</button>
      <span id="edit-test-result" class="settings-status"></span>
    </div>
  </div>`;
}

function testCamera(i) {
  const cam = cameras[i];
  const statusEl = document.getElementById(`cam-status-${i}`);
  if (statusEl) statusEl.innerHTML = '⏳ Tester...';
  fetch('/api/camera/test?' + new URLSearchParams({ip: cam.ip, user: cam.user, pass: cam.pass, path: cam.main_path}))
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        cameras[i] = {...cameras[i], codec: d.codec, width: d.width, height: d.height, fps: d.fps};
        if (statusEl) statusEl.innerHTML = `✅ ${d.codec.toUpperCase()} · ${d.width}×${d.height} · ${d.fps} fps`;
        renderCameras();
      } else {
        if (statusEl) statusEl.innerHTML = `❌ ${d.error}`;
      }
    }).catch(() => { if (statusEl) statusEl.innerHTML = '❌ Feil'; });
}

function testEditCamera() {
  const ip   = document.getElementById('edit-ip').value;
  const user = document.getElementById('edit-user').value;
  const pass = document.getElementById('edit-pass').value;
  const path = document.getElementById('edit-main_path').value;
  const el   = document.getElementById('edit-test-result');
  if (el) el.textContent = '⏳ Tester...';
  fetch('/api/camera/test?' + new URLSearchParams({ip, user, pass, path}))
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        document.getElementById('edit-width').value  = d.width;
        document.getElementById('edit-height').value = d.height;
        document.getElementById('edit-fps').value    = d.fps;
        if (el) el.textContent = `✅ ${d.codec.toUpperCase()} · ${d.width}×${d.height} · ${d.fps} fps`;
      } else {
        if (el) el.textContent = `❌ ${d.error}`;
      }
    }).catch(() => { if (el) el.textContent = '❌ Feil'; });
}

function saveEditCamera() {
  const objects = ['person','car','cat'].filter(o => document.getElementById(`edit-obj-${o}`)?.checked);
  const updated = {};
  CAM_FIELDS.forEach(f => {
    const el = document.getElementById(`edit-${f.key}`);
    if (!el) return;
    updated[f.key] = f.type === 'number' ? parseInt(el.value) : el.value;
  });
  updated.lpr        = document.getElementById('edit-lpr').checked;
  updated.record     = document.getElementById('edit-record').checked;
  updated.gpt_enabled = document.getElementById('edit-gpt_enabled')?.checked || false;
  updated.gpt_verify  = document.getElementById('edit-gpt_verify')?.checked || false;
  updated.objects    = objects;
  updated.codec  = cameras[editingCamera]?.codec || 'h264';

  if (editingCamera === null) cameras.push(updated);
  else cameras[editingCamera] = updated;
  saveCameras();
  closeEditCamera();
}

function addCamera() {
  editingCamera = null;
  cameras.push({name:'', display_name:'Nytt kamera', ip:'', user:'frigate',
    pass:'', main_path:'/Streaming/Channels/101', sub_path:'/Streaming/Channels/102', detect_stream:'sub',
    lpr:false, objects:['person','car'], record:true, width:640, height:360, fps:5, codec:'h264'});
  editCamera(cameras.length - 1);
}

function deleteCamera(i) {
  if (!confirm(`Slette ${cameras[i].display_name}?`)) return;
  cameras.splice(i, 1);
  saveCameras();
}

function closeEditCamera() {
  const modal = document.getElementById('camera-edit-modal');
  if (modal) modal.classList.add('hidden');
  editingCamera = null;
}

function saveCameras() {
  fetch('/api/cameras', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(cameras)
  }).then(r => r.json()).then(() => renderCameras()).catch(() => {});
}

function testGPT() {
  const statusEl = document.getElementById('gpt-test-status');
  if (statusEl) statusEl.textContent = '⏳ Tester...';
  fetch('/api/gpt/test')
    .then(r => r.json())
    .then(d => {
      if (statusEl) {
        statusEl.textContent = d.ok
          ? `✅ ${d.model} svarte: "${d.response}"`
          : `❌ ${d.error}`;
      }
    })
    .catch(() => { if (statusEl) statusEl.textContent = '❌ Nettverksfeil'; });
}

function copyTopic(topic, btn) {
  navigator.clipboard.writeText(topic).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✅';
    setTimeout(() => { btn.textContent = orig; }, 2000);
  }).catch(() => {
    btn.textContent = '❌';
    setTimeout(() => { btn.textContent = '📋'; }, 2000);
  });
}
