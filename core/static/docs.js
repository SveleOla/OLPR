function lastNedSkript(path) {
  fetch('/api/script?path=' + encodeURIComponent(path))
    .then(r => r.blob())
    .then(b => { const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = path.split('/').pop(); a.click(); })
    .catch(() => alert('Nedlasting feilet'));
}

const API_ENDPOINTS = [
  { method: 'GET',  path: '/api/status',                desc: 'Server-statistikk (load, RAM, disk)' },
  { method: 'GET',  path: '/api/settings',              desc: 'Alle innstillinger' },
  { method: 'POST', path: '/api/settings',              desc: 'Lagre innstillinger' },
  { method: 'GET',  path: '/api/cameras',               desc: 'Kameraliste' },
  { method: 'POST', path: '/api/cameras',               desc: 'Lagre kameraliste' },
  { method: 'GET',  path: '/api/camera/test',           desc: 'Test RTSP-tilkobling (?ip=&user=&pass=&path=)' },
  { method: 'GET',  path: '/api/gpt/test',              desc: 'Test GPT API-nøkkel' },
  { method: 'GET',  path: '/api/logg',                  desc: 'LPR-logg (?all=1 for historikk)' },
  { method: 'POST', path: '/api/logg/slett',            desc: 'Slett logg-linje' },
  { method: 'GET',  path: '/api/ukjente',               desc: 'Ukjente kjøretøy fra database' },
  { method: 'GET',  path: '/api/ukjente/slett',         desc: 'Slett ukjent kjøretøy (?id=)' },
  { method: 'GET',  path: '/api/events24h',             desc: 'Alle bil-events siste 24 timer' },
  { method: 'GET',  path: '/api/statistikk',            desc: 'Besøksstatistikk' },

  { method: 'GET',  path: '/api/frigate_snapshot/:id',  desc: 'Proxy Frigate snapshot' },
  { method: 'GET',  path: '/snapshot/:filnavn',         desc: 'Server lokalt snapshot' },
  { method: 'GET',  path: '/api/docs',                  desc: 'Denne dokumentasjonen' },
];

const PIPELINE_STEPS = [
  { icon: '🚗', title: 'Bil detektert',       desc: 'Frigate oppdager bil på LPR-kamera via Coral TPU. 10-sekunders timer startes.' },
  { icon: '📸', title: 'Snapshot',             desc: 'go2rtc-frame captures 1 sekund etter deteksjon mens bilen er godt synlig.' },
  { icon: '🔢', title: 'Stemme-innsamling',   desc: 'Frigate sender LPR-lesinger via MQTT. Stemmer samles i 1.5 sekunder.' },
  { icon: '🏆', title: 'Vinner velges',        desc: '≥80% konfidens → Frigate-lesing brukes direkte. <80% → GPT-4o verifiserer.' },
  { icon: '📡', title: 'MQTT publisering',     desc: 'Skilt og eier publiseres til konfigurerbart MQTT-topic (QoS 1, retain). Blankes etter reset_seconds.' },
  { icon: '🗄️', title: 'Database',            desc: 'Ukjente biler lagres med snapshot, kilde og frigate_plate for sporbarhet.' },
];

function loadDocs() {
  fetch('/api/docs')
    .then(r => r.json())
    .then(d => renderDocs(d))
    .catch(() => {});
}

function renderDocs(d) {
  const el = document.getElementById('docs-container');
  if (!el) return;

  const sys = d.system || {};
  const lpr = d.lpr || {};
  const cameras = d.cameras || [];
  const services = d.services || {};
  const lprCams = cameras.filter(c => c.lpr);

  // Hent Frigate-config og flett inn faktisk oppløsning/fps/objekter
  fetch('/api/frigate_config').then(r => r.json()).then(fc => {
    cameras.forEach(c => {
      const fd = fc[c.name];
      if (fd) {
        c.detect_width  = fd.width;
        c.detect_height = fd.height;
        c.detect_fps    = fd.fps;
        c.objects = fd.objects || [];
        c.record  = fd.record;
      }
    });
    renderCameraTable(cameras);
  }).catch(() => renderCameraTable(cameras));

  // Tjenestestatus
  const svcHtml = Object.entries(services).map(([name, svc]) => {
    const status  = typeof svc === 'object' ? svc.status  : svc;
    const exec    = typeof svc === 'object' ? svc.exec    : '';
    const started = typeof svc === 'object' ? svc.started : '';
    const ok = status === 'active';
    const startedStr = started ? started.replace('EET ', '').replace('CEST ', '') : '';
    return `<tr>
      <td><b>${name}</b></td>
      <td><span style="color:${ok ? 'var(--green)' : 'var(--red)'}">${ok ? '✅ Kjører' : '❌ ' + status}</span></td>
      <td style="color:var(--text-dim);font-size:12px"><code>${exec || '–'}</code></td>
      <td style="color:var(--muted);font-size:12px">${startedStr}</td>
    </tr>`;
  }).join('');

  // LPR-kameraer med topics
  const lprCamHtml = lprCams.length
    ? lprCams.map(c => `<tr>
        <td><b>${c.display_name || c.name}</b></td>
        <td>${c.ip}</td>
        <td><code style="color:var(--green)">loxone/${c.name}/resultat</code>
          <button class="cam-copy-btn" onclick="copyTopic('loxone/${c.name}/resultat', this)">📋</button></td>
        <td><code style="color:var(--accent-2)">loxone/${c.name}/skilt</code></td>
      </tr>`).join('')
    : '<tr><td colspan="4" style="color:var(--muted)">Ingen LPR-kameraer aktivert</td></tr>';

  // Alle kameraer
  function renderCameraTable(cams) {
    const tbody = document.getElementById('all-cameras-tbody');
    if (!tbody) return;
    tbody.innerHTML = cams.map(c => {
      const main    = c.width && c.height ? `${c.width}×${c.height} ${c.fps||'?'}fps` : '–';
      const detect  = c.detect_width && c.detect_height ? `<span style="color:var(--muted);font-size:11px"><br>detect: ${c.detect_width}×${c.detect_height} ${c.detect_fps||'?'}fps</span>` : '';
      return `<tr>
        <td><b>${c.display_name || c.name}</b></td>
        <td>${c.ip}</td>
        <td>${main}${detect}</td>
        <td>${c.codec?.toUpperCase() || '?'}</td>
        <td>${c.lpr ? '<span style="color:var(--green)">✅ LPR</span>' : '–'}</td>
        <td>${(c.objects || []).length ? c.objects.join(', ') : '–'}</td>
        <td>${c.record ? '✅' : '–'}</td>
      </tr>`;
    }).join('');
  }
  const allCamHtml = '<tbody id="all-cameras-tbody"></tbody>';

  // Innstillinger
  const settingsHtml = [
    ['Konfidens-terskel', lpr.confidence_threshold],
    ['GPT aktivert', lpr.gpt_enabled ? 'Ja' : 'Nei'],
    ['GPT-modell', lpr.gpt_model],
    ['Ventetid', lpr.wait_seconds + 's'],
    ['Reset-tid', lpr.reset_seconds + 's'],
    ['Commit-vindu', lpr.commit_window + 's'],
    ['Snapshot-retensjon', lpr.snapshot_retention_days + ' dager'],
    ['MQTT host', lpr.mqtt_host + ':' + lpr.mqtt_port],
  ].map(([k, v]) => `<tr><td>${k}</td><td><b>${v}</b></td></tr>`).join('');

  // Pipeline
  const pipelineHtml = PIPELINE_STEPS.map((s, i) => `
    <div class="pipeline-step">
      <div class="pipeline-icon">${s.icon}</div>
      <div class="pipeline-content">
        <div class="pipeline-title">${i + 1}. ${s.title}</div>
        <div class="pipeline-desc">${s.desc}</div>
      </div>
      ${i < PIPELINE_STEPS.length - 1 ? '<div class="pipeline-arrow">↓</div>' : ''}
    </div>`).join('');

  // API
  const apiHtml = API_ENDPOINTS.map(e => `<tr>
    <td><span class="method-badge method-${e.method.toLowerCase()}">${e.method}</span></td>
    <td><code>${e.path}</code></td>
    <td style="color:var(--text-dim)">${e.desc}</td>
  </tr>`).join('');

  el.innerHTML = `
    <div class="doc-grid">
      <div class="card">
        <h2>🖥️ Tjenestestatus</h2>
        <button onclick="restartAlt()" style="margin-bottom:12px">🔄 Restart alle tjenester</button>
        <span id="restart-status" class="settings-status" style="margin-left:8px"></span>
        <table>
          <thead><tr><th>Tjeneste</th><th>Status</th><th>Skript</th><th>Startet</th></tr></thead>
          <tbody>${svcHtml}</tbody>
        </table>
      </div>
      <div class="card">
        <h2>⚙️ System</h2>
        <table><tbody>
          <tr><td>Navn</td><td><b>${sys.name || '–'}</b></td></tr>
          <tr><td>Frigate</td><td><a href="${sys.frigate_url||'#'}" target="_blank" style="color:var(--accent-2)">${sys.frigate_url||'–'}</a></td></tr>
          <tr><td>Portainer</td><td><a href="${sys.portainer_url||'#'}" target="_blank" style="color:var(--accent-2)">${sys.portainer_url||'–'}</a></td></tr>
        </tbody></table>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>📡 Aktive LPR-kameraer & MQTT topics</h2>
      <table><thead><tr><th>Kamera</th><th>IP</th><th>Resultat-topic</th><th>Skilt-topic</th></tr></thead>
      <tbody>${lprCamHtml}</tbody></table>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h2>📹 Alle kameraer</h2>
      <table><thead><tr><th>Navn</th><th>IP</th><th>Oppløsning</th><th>Codec</th><th>LPR</th><th>Objekter</th><th>Opptak</th></tr></thead>
      ${allCamHtml}</table>
    </div>

    <div class="doc-grid" style="margin-bottom:16px">
      <div class="card">
        <h2>🔧 LPR-innstillinger</h2>
        <table><tbody>${settingsHtml}</tbody></table>
      </div>
      <div class="card">
        <h2>🔄 Pipeline-flyt</h2>
        <div class="pipeline">${pipelineHtml}</div>
      </div>
    </div>

    <div class="card">
      <h2>🔌 API-endepunkter</h2>
      <table><thead><tr><th>Metode</th><th>Endepunkt</th><th>Beskrivelse</th></tr></thead>
      <tbody>${apiHtml}</tbody></table>
    </div>`;
}

function restartAlt() {
  const st = document.getElementById('restart-status');
  if (st) st.textContent = '⏳ Restarter...';
  fetch('/api/restart/all', { method: 'POST' })
    .then(r => r.json())
    .then(() => { if (st) { st.textContent = '✅ Ferdig – siden laster om...'; setTimeout(() => location.reload(), 5000); }})
    .catch(() => { if (st) st.textContent = '✅ Ferdig – siden laster om...'; setTimeout(() => location.reload(), 5000); });
}
