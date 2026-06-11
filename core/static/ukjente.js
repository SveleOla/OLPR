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
    case 'ukjent':
      frigateStr = frigatePlate ? `❌ (${frigatePlate})` : '❌'; gptStr = '❌'; break;
    default: frigateStr = '–'; gptStr = null;
  }
  let html = `<span style="display:block">Frigate ${frigateStr}</span>`;
  if (gptStr !== null) html += `<span style="display:block">GPT ${gptStr}</span>`;
  return html;
}

function updateUkjente() {
  const showAll = visHistorikk;
  fetch('/api/ukjente' + (showAll ? '?all=1' : ''))
    .then(r => r.json())
    .then(items => {
      const grid = document.getElementById('ukjente-grid');
      if (!grid) return;
      const cnt = document.getElementById('ukjente-count');
      if (cnt) cnt.textContent = items.length;
      if (!items.length) {
        grid.innerHTML = '<p class="no-data">Ingen ukjente kjøretøy registrert</p>';
        return;
      }
      grid.innerHTML = items.map(item => {
        const imgHtml = item.snapshot
          ? `<img src="${item.snapshot}" alt="snapshot" style="cursor:zoom-in"
               onclick="openLightbox('${item.snapshot}')"
               onerror="this.parentElement.innerHTML='<div class=\\'ukjente-no-img\\'>Ingen bilde</div>'">`
          : `<div class="ukjente-no-img">Ingen bilde</div>`;
        const plateTekst = item.plate === 'ukjent' ? '🔍 Ukjent' : esc(item.plate);
        const kildeTekst = kildeLabel(item.kilde, item.frigate_plate);
        const addForm = (item.plate !== 'ukjent')
          ? `<div id="add-${item.id}" style="margin-top:8px;">
               <input type="text" id="name-${item.id}" placeholder="Navn..."
                      style="width:100%;margin-bottom:4px;font-size:12px;">
               <button onclick="leggTilKjent('${esc(item.plate.replace(/['\\]/g, ''))}', ${item.id})"
                       style="width:100%;font-size:11px;margin-bottom:4px;">+ Legg til som kjent</button>
             </div>`
          : '';
        return `<div class="ukjente-card" id="ukjente-${item.id}">
          ${imgHtml}
          <div class="ukjente-card-body">
            <div class="ukjente-card-plate">${plateTekst}${item.camera ? `<span class='cam-badge'>${esc(item.camera)}</span>` : ''}</div>
            <div class="ukjente-card-time">${item.tidspunkt}</div>
            <div class="ukjente-card-kilde" style="line-height:1.6">${kildeTekst}</div>
            ${addForm}
            <button class="del" onclick="slettUkjent(${item.id})"
                    style="width:100%;font-size:11px;margin-top:4px;">Slett</button>
          </div>
        </div>`;
      }).join('');
    })
    .catch(() => {});
}

function leggTilKjent(plate, id) {
  const nameEl = document.getElementById('name-' + id);
  const name   = nameEl?.value?.trim();
  if (!name) return;
  fetch('/api/kjente', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: 'add', plate, name})
  }).then(r => r.json()).then(d => {
    if (d.ok) {
      document.getElementById('add-' + id).innerHTML =
        '<span style="color:var(--green)">✅ Lagt til i kjente biler</span>';
      setTimeout(updateEvents24h, 500);
      if (typeof updateKjenteBiler === 'function') updateKjenteBiler();
    }
  }).catch(() => {});
}

function slettUkjent(id) {
  if (!confirm('Slette denne oppføringen?')) return;
  fetch('/api/ukjente/slett?id=' + id)
    .then(r => r.json())
    .then(d => {
      if (d.ok) {
        const el = document.getElementById('ukjente-' + id);
        if (el) el.remove();
        const cnt = document.getElementById('ukjente-count');
        if (cnt) cnt.textContent = parseInt(cnt.textContent) - 1;
      }
    })
    .catch(() => {});
}

window.addEventListener('DOMContentLoaded', updateUkjente);
setInterval(updateUkjente, 30000);
