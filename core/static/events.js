function kildeLabel(kilde, frigatePlate) {
  let frigateStr, gptStr;
  switch(kilde) {
    case 'kjent':
    case 'frigate':   frigateStr = '✅'; gptStr = null; break;
    case 'gpt_verifisert':
      frigateStr = '❌' + (frigatePlate ? ` (${frigatePlate})` : ''); gptStr = '✅'; break;
    case 'gpt_fallback': frigateStr = '❌'; gptStr = '✅'; break;
    case 'frigate_gpt_feilet':
      frigateStr = '❌' + (frigatePlate ? ` (${frigatePlate})` : ''); gptStr = '❌'; break;
    case 'kjent_gpt_enig':
    case 'frigate_gpt_enig':
      frigateStr = '✅'; gptStr = '✅'; break;
    case 'kjent_gpt_uenig':
    case 'frigate_gpt_uenig':
      frigateStr = '✅'; gptStr = `⚠️ uenig (${frigatePlate||''})`.trim(); break;
    case 'ukjent':
      frigateStr = frigatePlate ? `❌ (${frigatePlate})` : '❌'; gptStr = '❌'; break;
    default: frigateStr = kilde ? '✅' : '–'; gptStr = null;
  }
  let html = `<span style="display:block">Frigate ${frigateStr}</span>`;
  if (gptStr !== null) html += `<span style="display:block">GPT ${gptStr}</span>`;
  return html;
}

function updateEvents24h() {
  const showAll = visHistorikk;
  fetch('/api/events24h' + (showAll ? '?all=1' : ''))
    .then(r => r.json())
    .then(events => {
      const grid = document.getElementById('events-grid');
      if (!grid) return;
      const cnt = document.getElementById('events-count');
      if (cnt) cnt.textContent = events.length;
      if (!events.length) {
        grid.innerHTML = `<p class="no-data">Ingen deteksjoner ${showAll ? 'i historikken' : 'siste 24 timer'}</p>`;
        return;
      }
      grid.innerHTML = events.map(ev => {
        const snapSrc    = ev.local_snapshot || '/api/frigate_snapshot/' + ev.event_id;
        const plateTekst = ev.plate === 'ukjent' ? '🔍 Ukjent' : ev.plate;
        const navnHtml   = ev.navn
          ? `<div class="ukjente-card-kilde" style="color:var(--green);">${ev.navn}</div>` : '';
        const kildeTekst = kildeLabel(ev.kilde, ev.frigate_plate);
        const safeId     = ev.event_id.replace(/[^a-zA-Z0-9_-]/g, '_');
        const addForm    = (ev.plate !== 'ukjent' && !ev.navn)
          ? `<div id="add-ev-${safeId}" style="margin-top:8px;">
               <input type="text" id="name-ev-${safeId}" placeholder="Navn..."
                      style="width:100%;margin-bottom:4px;font-size:12px;">
               <button onclick="leggTilKjentEv('${ev.plate}','${safeId}')"
                       style="width:100%;font-size:11px;">+ Legg til som kjent</button>
             </div>` : '';
        return `<div class="ukjente-card">
          <img src="${snapSrc}" alt="snapshot" style="cursor:zoom-in"
               onclick="openLightbox('${snapSrc}')"
               onerror="this.parentElement.innerHTML='<div class=\\'ukjente-no-img\\'>Ingen bilde</div>'">
          <div class="ukjente-card-body">
            <div class="ukjente-card-plate">${plateTekst}${ev.camera ? `<span class='cam-badge'>${ev.camera}</span>` : ''}</div>
            ${navnHtml}
            <div class="ukjente-card-time">${ev.tidspunkt}</div>
            <div class="ukjente-card-kilde" style="line-height:1.6">${kildeTekst}</div>
            ${addForm}
          </div>
        </div>`;
      }).join('');
    })
    .catch(() => {});
}

function leggTilKjentEv(plate, safeId) {
  const nameEl = document.getElementById('name-ev-' + safeId);
  const name   = nameEl?.value?.trim();
  if (!name) return;
  fetch('/', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: `action=add&plate=${encodeURIComponent(plate)}&name=${encodeURIComponent(name)}`,
    redirect: 'manual'
  }).then(() => {
    document.getElementById('add-ev-' + safeId).innerHTML =
      '<span style="color:var(--green)">✅ Lagt til i kjente biler</span>';
    setTimeout(updateEvents24h, 500);
  });
}

window.addEventListener('DOMContentLoaded', updateEvents24h);
setInterval(updateEvents24h, 30000);
