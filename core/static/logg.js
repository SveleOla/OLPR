function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('active');
}
function closeLightbox() {
  document.getElementById('lightbox').classList.remove('active');
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

function slettLoggRad(btn, linje) {
  if (!confirm('Slette denne raden?')) return;
  fetch('/api/logg/slett', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'linje=' + encodeURIComponent(linje)
  }).then(r => r.json()).then(d => {
    if (d.ok) btn.closest('tr').remove();
  }).catch(() => {});
}

let loggPage = 1;
let loggPerPage = 20;
let visHistorikk = false;

function toggleHistorikk() {
  visHistorikk = !visHistorikk;
  const btn = document.getElementById('btn-historikk');
  if (btn) btn.textContent = visHistorikk ? '📅 Vis kun i dag' : '📅 Vis historikk';
  loggPage = 1;
  updateLogg(1);
  updateUkjente();
  updateEvents24h();
}
let visGalleri = true;

function toggleVisning() {
  visGalleri = !visGalleri;
  const btn = document.getElementById('btn-visning');
  if (btn) btn.textContent = visGalleri ? '☰ Vis liste' : '⊞ Vis galleri';
  updateLogg(1);
}

function renderGalleri(items) {
  if (!items.length) return '<p class="no-data">Ingen registreringer ennå</p>';
  return items.map(item => {
    const imgHtml = item.snapshot
      ? `<img src="${item.snapshot}" alt="snapshot" style="cursor:zoom-in;width:100%;border-radius:6px 6px 0 0"
           onclick="openLightbox('${item.snapshot}')"
           onerror="this.parentElement.innerHTML='<div class=\\'ukjente-no-img\\'>Ingen bilde</div>'">`
      : `<div class="ukjente-no-img">Ingen bilde</div>`;

    const navnHtml = item.navn
      ? `<span class="kjent">${esc(item.navn)}</span>`
      : `<div id="add-logg-${item.linje.replace(/[^a-zA-Z0-9]/g,'_')}" style="margin-top:6px">
           <input type="text" id="name-logg-${item.linje.replace(/[^a-zA-Z0-9]/g,'_')}" 
                  placeholder="Navn..." style="width:100%;margin-bottom:4px;font-size:12px">
           <button onclick="leggTilFraLogg('${esc(item.plate.replace(/['\\]/g, ''))}','${item.linje.replace(/[^a-zA-Z0-9]/g,'_')}')"
                   style="width:100%;font-size:11px">+ Legg til som kjent</button>
         </div>`;

    const kildeHtml = item.kilde
      ? kildeLabel(item.kilde, item.frigate_plate)
      : '<span style="color:var(--muted)">–</span>';

    const linje = item.linje.replace(/'/g, "\\'");

    return `<div class="ukjente-card">
      ${imgHtml}
      <div class="ukjente-card-body">
        <div class="ukjente-card-plate">${esc(item.plate)}
          ${item.camera ? `<span class='cam-badge'>${esc(item.camera)}</span>` : ''}
        </div>
        <div class="ukjente-card-time">${item.dato} ${item.tid}</div>
        ${navnHtml}
        <div class="ukjente-card-kilde" style="line-height:1.6;margin-top:4px">${kildeHtml}</div>
        <button class="del" onclick="slettLoggRad(this,'${linje}')"
                style="width:100%;font-size:11px;margin-top:6px">Slett</button>
      </div>
    </div>`;
  }).join('');
}

function leggTilFraLogg(plate, safeId) {
  const nameEl = document.getElementById('name-logg-' + safeId);
  const name = nameEl?.value?.trim();
  if (!name) return;
  fetch('/', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: `action=add&plate=${encodeURIComponent(plate)}&name=${encodeURIComponent(name)}`,
    redirect: 'manual'
  }).then(() => {
    document.getElementById('add-logg-' + safeId).innerHTML =
      '<span style="color:var(--green)">✅ Lagt til</span>';
    setTimeout(() => updateLogg(loggPage), 500);
  });
}


function updateLogg(page) {
  if (page) loggPage = page;
  const showAll = visHistorikk;
  fetch(`/api/logg?page=${loggPage}&per_page=${loggPerPage}${showAll ? '&all=1' : ''}`)
    .then(r => r.json())
    .then(data => {
      const tbody     = document.getElementById('logg-tbody');
      const btnLogg   = document.getElementById('btn-sub-logg');
      const galleriEl = document.getElementById('logg-galleri');
      const tabelEl   = document.getElementById('logg-tabell');

      if (btnLogg) {
        btnLogg.textContent = visHistorikk ? `Logg (${data.total} – historikk)` : `Logg (${data.today_total})`;
      }

      if (!data.lines.length) {
        if (visGalleri) {
          if (tabelEl) tabelEl.style.display = 'none';
          if (galleriEl) { galleriEl.style.display = ''; galleriEl.innerHTML = '<p class="no-data">Ingen registreringer ennå</p>'; }
        } else {
          if (tabelEl) tabelEl.style.display = '';
          if (galleriEl) galleriEl.style.display = 'none';
          if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted);text-align:center;">Ingen registreringer ennå</td></tr>';
        }
        renderPagination(data);
        return;
      }

      if (visGalleri) {
        if (tabelEl) tabelEl.style.display = 'none';
        if (galleriEl) { galleriEl.style.display = ''; galleriEl.innerHTML = renderGalleri(data.lines); }
      } else {
        if (tabelEl) tabelEl.style.display = '';
        if (galleriEl) galleriEl.style.display = 'none';
        let html = '';
        data.lines.forEach(item => {
          const camera  = esc(item.camera || '');
          const plate   = esc(item.plate);
          const eier    = esc(item.navn||"");
          const linje   = item.linje.replace(/'/g, "\\'");
          const eierHtml = item.navn
            ? `<span class="kjent">${eier}</span>`
            : `<form method="POST" class="inline">
                 <input type="hidden" name="action" value="add">
                 <input type="hidden" name="plate" value="${plate}">
                 <input type="text" name="name" placeholder="Navn..." required>
                 <button type="submit">+ Legg til</button>
               </form>`;
          html += `<tr>
            <td>${item.dato}</td><td>${item.tid}</td>
            <td><b>${plate}</b>${camera ? `<span class='cam-badge'>${camera}</span>` : ""}</td>
            <td>${eierHtml}</td>
            <td><button class="del" onclick="slettLoggRad(this,'${linje}')">&#x2715;</button></td>
          </tr>`;
        });
        if (tbody) tbody.innerHTML = html;
      }
      renderPagination(data);
    })
    .catch(() => {});
}

function renderPagination(data) {
  const el = document.getElementById('logg-pagination');
  if (!el) return;
  if (data.total === 0) { el.innerHTML = ''; return; }
  let html = `<div style="display:flex;gap:8px;align-items:center;margin-top:12px;justify-content:center;flex-wrap:wrap">`;
  html += `<select onchange="loggPerPage=parseInt(this.value);updateLogg(1)" style="background:var(--surface-3);color:var(--text);border:1px solid var(--border-strong);padding:4px 8px;border-radius:4px">`;
  [10,20,50,100].forEach(n => {
    html += `<option value="${n}" ${n === loggPerPage ? 'selected' : ''}>${n} per side</option>`;
  });
  html += `</select>`;
  if (data.pages > 1) {
    html += `<button onclick="updateLogg(1)" ${data.page === 1 ? 'disabled' : ''}>⟨⟨</button>`;
    html += `<button onclick="updateLogg(${data.page - 1})" ${data.page === 1 ? 'disabled' : ''}>⟨</button>`;
    html += `<span style="color:var(--text-dim)">Side ${data.page} av ${data.pages} (${data.total} totalt)</span>`;
    html += `<button onclick="updateLogg(${data.page + 1})" ${data.page === data.pages ? 'disabled' : ''}>⟩</button>`;
    html += `<button onclick="updateLogg(${data.pages})" ${data.page === data.pages ? 'disabled' : ''}>⟩⟩</button>`;
  } else {
    html += `<span style="color:var(--text-dim)">${data.total} totalt</span>`;
  }
  html += `</div>`;
  el.innerHTML = html;
}

window.addEventListener('DOMContentLoaded', () => updateLogg(1));

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btn-historikk');
  if (btn) btn.addEventListener('click', toggleHistorikk);
  const btnVisning = document.getElementById('btn-visning');
  if (btnVisning) btnVisning.addEventListener('click', toggleVisning);
});
