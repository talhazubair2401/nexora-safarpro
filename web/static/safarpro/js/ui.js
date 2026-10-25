/* =========================================================
   SafarPro demo — UI infrastructure: components, shell, forms, sync
   ========================================================= */
const TONE = {
  ok:['Confirmed','Completed','Paid','Approved','Active','Posted','Verified','Issued','Flown','Balanced','Converted','Valid','Received','Passport Returned','Documents Verified','Matched','Synced','Open','Netted in cost','Reconciled','Connected','Delivered','Scheduled'],
  warn:['Pending','Partially Paid','Documents Pending','Awaiting Approval','Under Review','Requested','Follow-up Required','Pending approval','Pending verification','Processing','Expiring','Partial','Additional Information Required','Discrepancy — pending review','Pending confirmation','Unpaid','Pending documents','Applied','Advance received','Documents in progress','Seasonal','Registration open','On Hold','Credit due','Due soon','Unreconciled','Not reconciled','Approved — awaiting payment'],
  err:['Overdue','Rejected','Cancelled','Lost','Failed','Missing','Suspended','Void','Reversed','Conflict','Offline','Over limit'],
  info:['Submitted','In Process','Quotation Sent','Contacted','New','New Enquiry','Ready to Submit','Refunded','Synchronizing','Not invoiced','Duplicate','Included in booking'],
  demo:['Demo','Simulated']
};
const TONE_MAP = {}; Object.entries(TONE).forEach(([t, l]) => l.forEach(s => TONE_MAP[s] = t));
const tone = s => TONE_MAP[s] || '';
const pill = (s, t) => `<span class="pill ${t ?? tone(s)}">${esc(s)}</span>`;
const ph = (title, sub, acts = '', demo = false) => `<div class="ph"><div><h1>${title}${demo ? `<span class="demo-tag">${ic('flask-conical')}Demo data</span>` : ''}</h1><p>${sub}</p></div><div class="ph-a">${acts}</div></div>`;
const kpi = o => `<button class="kpi" ${o.r ? `data-a="go" data-r="${o.r}"` : 'data-a="noop" tabindex="-1"'} ${o.p ? `data-preset="${esc(o.p)}"` : ''} ${o.id ? `data-id="${o.id}"` : ''} ${o.tab ? `data-tab="${o.tab}"` : ''}><div class="kpi-h"><span class="kpi-i ${o.t || ''}">${ic(o.i || 'circle')}</span><span class="kpi-l">${o.l}</span>${o.r ? ic('arrow-up-right', 'kpi-go') : ''}</div><div class="kpi-v">${o.v}</div>${o.s ? `<div class="kpi-s">${o.s}</div>` : ''}</button>`;
const money = n => Math.abs(n) >= 1e6 ? `<span data-tip="${pk(n)}"><small>PKR</small>${(n / 1e6).toFixed(2)}M</span>` : `<small>PKR</small>${num(n)}`;
const card = (title, body, o = {}) => `<section class="card ${o.cls || ''}" ${o.id ? `id="${o.id}"` : ''}>${title ? `<div class="ch"><div><h3>${title}</h3>${o.sub ? `<p>${o.sub}</p>` : ''}</div>${o.right ? `<div class="r">${o.right}</div>` : ''}</div>` : ''}<div class="cb ${o.np ? 'np' : ''}">${body}</div></section>`;
const empty = (icon, title, text, action = '') => `<div class="empty"><div class="ei">${ic(icon)}</div><h4>${title}</h4><p>${text}</p>${action}</div>`;
function btn(label, a, o = {}) {
  const locked = o.perm && !can(o.perm);
  return `<button class="btn ${o.cls || ''} ${locked ? 'locked' : ''}" data-a="${locked ? 'locked' : a}" ${o.data || ''} ${locked ? `data-perm="${o.perm}" title="Not available for the ${S.me.role} role"` : o.title ? `title="${esc(o.title)}"` : ''} ${o.dis ? 'disabled' : ''}>${o.icon || locked ? ic(locked ? 'lock' : o.icon) : ''}${label ? `<span>${label}</span>` : ''}</button>`;
}
const sbtn = (label, a, o = {}) => btn(label, a, { ...o, cls:'btn-sm ' + (o.cls || '') });
const tabs = (key, list, def) => { const cur = UI.tabs[key] || def || list[0][0]; return `<div class="tabs" role="tablist">${list.map(([v, l, c]) => `<button role="tab" aria-selected="${cur === v}" class="${cur === v ? 'on' : ''}" data-a="tab" data-k="${key}" data-v="${v}">${l}${c != null ? `<span class="tc">${c}</span>` : ''}</button>`).join('')}</div>`; };
const curTab = (key, def) => UI.tabs[key] || def;
const kv = rows => `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v ?? '—'}</dd>`).join('')}</dl>`;
const bar = (p, cls = '') => `<div class="bar ${cls}"><i style="width:${Math.max(0, Math.min(100, p))}%"></i></div>`;
const note = (text, t = '', i = 'info') => `<div class="note ${t}">${ic(i)}<div>${text}</div></div>`;
const amt = (n, o = {}) => `<span class="${o.neg && n > 0 ? 'neg' : o.pos && n > 0 ? 'pos' : ''}">${pk(n)}</span>`;
const link = (label, r, id) => `<button class="lnk" data-a="go" data-r="${r}" ${id ? `data-id="${id}"` : ''}>${esc(label)}</button>`;
const icons = () => {};

/* ---------- Toasts ---------- */
function toast(msg, t = 'ok') {
  const el = document.createElement('div'); el.className = 'toast ' + t;
  el.innerHTML = ic({ ok:'circle-check', err:'circle-x', warn:'triangle-alert', info:'info' }[t] || 'info') + `<div>${msg}</div>`;
  $('#toasts').appendChild(el); icons(); setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 320); }, t === 'err' ? 6000 : 3800);
}
const savedMsg = m => m;

/* ---------- Modals, drawers, popovers ---------- */
function openModal(title, body, o = {}) {
  const el = document.createElement('div'); el.className = 'mback';
  el.innerHTML = `<div class="modal ${o.wide ? 'wide' : ''} ${o.xl ? 'xl' : ''} ${o.cls || ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}" tabindex="-1"><div class="mhead"><div><h3>${title}</h3>${o.sub ? `<p>${o.sub}</p>` : ''}</div><button class="ib" data-a="mclose" aria-label="Close">${ic('x')}</button></div><div class="mbody">${body}</div></div>`;
  el.addEventListener('mousedown', e => { if (e.target === el) el.remove(); });
  $('#modals').appendChild(el); icons();
  setTimeout(() => { const f = el.querySelector('input:not([type=hidden]):not([readonly]):not([type=checkbox]),select,textarea'); (f || el.querySelector('.modal')).focus(); }, 20);
  return el;
}
function openDrawer(title, body, o = {}) {
  closeDrawer();
  const bg = document.createElement('div'); bg.className = 'dback'; bg.id = 'dback'; bg.onclick = closeDrawer;
  const el = document.createElement('aside'); el.className = 'drawer'; el.id = 'drawer'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', title);
  el.innerHTML = `<div class="mhead"><div><h3>${title}</h3>${o.sub ? `<p>${o.sub}</p>` : ''}</div><button class="ib" data-a="dclose" aria-label="Close">${ic('x')}</button></div><div class="mbody">${body}</div>`;
  document.body.append(bg, el); icons(); el.querySelector('.ib').focus();
}
function closeDrawer() { $('#drawer')?.remove(); $('#dback')?.remove(); }
function closeTop() { const m = [...document.querySelectorAll('.mback')].pop(); if (m) { m.remove(); return true; } if ($('#drawer')) { closeDrawer(); return true; } if ($('#pops').innerHTML) { closePops(); return true; } return false; }
function confirmBox(title, text, okLabel, onOk, o = {}) {
  const el = openModal(title, `<p class="mut" style="font-size:13.5px">${text}</p>${o.reason ? `<div class="fld full mt"><label for="cf-reason">${o.reasonLabel || 'Reason'} <span class="req">*</span></label><textarea id="cf-reason" rows="3" placeholder="${o.ph || 'Explain why — this is stored in the audit trail.'}"></textarea><small class="err" hidden>A reason is required.</small></div>` : ''}<div class="mfoot"><button class="btn" data-a="mclose">Cancel</button><button class="btn ${o.danger ? 'btn-dd' : 'btn-p'}" id="cf-ok">${okLabel}</button></div>`);
  el.querySelector('#cf-ok').onclick = () => { let r = ''; if (o.reason) { r = el.querySelector('#cf-reason').value.trim(); if (!r) { el.querySelector('.err').hidden = false; el.querySelector('.fld').classList.add('bad'); return; } } el.remove(); onOk(r); };
}
function closePops() { $('#pops').innerHTML = ''; }
function openPop(anchor, html, o = {}) {
  closePops(); const r = anchor.getBoundingClientRect(); const p = document.createElement('div'); p.className = 'pop ' + (o.cls || ''); p.innerHTML = html; $('#pops').appendChild(p);
  const w = p.offsetWidth; let left = o.left ? r.left : r.right - w; left = Math.max(12, Math.min(left, innerWidth - w - 12));
  p.style.left = left + 'px'; p.style.top = Math.min(r.bottom + 6, innerHeight - p.offsetHeight - 12) + 'px'; icons(); return p;
}
function downloadFile(name, text, mime = 'text/csv;charset=utf-8') { const blob = new Blob(['\ufeff' + text], { type:mime }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function textOut(title, text, sub = '', o = {}) {
  const el = openModal(title, `<textarea class="textout" id="to-text" readonly>${esc(text)}</textarea><div class="mfoot"><span class="l mut" style="font-size:12px;align-self:center">Paste into Excel, WhatsApp or email.</span><button class="btn" data-a="mclose">Close</button>${o.file ? `<button class="btn" id="to-dl">${ic('download')}Download ${esc(o.file.split('.').pop().toUpperCase())}</button>` : ''}<button class="btn btn-p" id="to-copy">${ic('copy')}Copy to clipboard</button></div>`, { wide:true, sub });
  if (o.file) el.querySelector('#to-dl').onclick = () => downloadFile(o.file, text);
  el.querySelector('#to-copy').onclick = () => { const ta = el.querySelector('#to-text'); const done = () => toast('Copied to clipboard.'); try { navigator.clipboard.writeText(text).then(done, () => { ta.select(); toast('Text selected — press Ctrl+C to copy.', 'info'); }); } catch (e) { ta.select(); toast('Text selected — press Ctrl+C to copy.', 'info'); } };
  icons();
}
const csv = (cols, rows) => [cols.map(c => c.h), ...rows.map(r => cols.map(c => { const v = c.v ? c.v(r) : ''; return v == null ? '' : v; }))].map(r => r.map(x => { const s = String(x); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(',')).join('\n');

/* ---------- Data table ---------- */
UI.tCfg = {};
function table(key, cfg) {
  const st = UI.t[key] = UI.t[key] || { q:'', sort:null, dir:1, page:0, f:{}, sel:[] };
  UI.tCfg[key] = cfg;
  let rows = cfg.rows;
  if (st.q && cfg.search) { const q = st.q.toLowerCase(); rows = rows.filter(r => cfg.search(r).toLowerCase().includes(q)); }
  (cfg.filters || []).forEach(f => { const v = st.f[f.k]; if (v) rows = rows.filter(r => f.test ? f.test(r, v) : String(f.get(r)) === v); });
  if (st.sort != null && cfg.cols[st.sort]) { const c = cfg.cols[st.sort]; const g = c.s || c.v; rows = [...rows].sort((a, b) => { const x = g(a), y = g(b); return (x > y ? 1 : x < y ? -1 : 0) * st.dir; }); }
  UI.t[key].rows = rows;
  const ps = cfg.ps || 10, pages = Math.max(1, Math.ceil(rows.length / ps)); if (st.page >= pages) st.page = pages - 1;
  const view = cfg.noPage ? rows : rows.slice(st.page * ps, st.page * ps + ps);
  const selN = st.sel.length;
  const fl = (cfg.filters || []).map(f => `<select class="inp" aria-label="${f.l}" data-ch="tf" data-k="${key}" data-fk="${f.k}"><option value="">${f.l}: All</option>${f.opts.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(v)}" ${st.f[f.k] === String(v) ? 'selected' : ''}>${esc(l)}</option>`; }).join('')}</select>`).join('');
  const anyF = st.q || Object.values(st.f).some(Boolean);
  const bar_ = cfg.bare ? '' : `<div class="tbar">${cfg.search ? `<div class="tsearch">${ic('search')}<input class="inp" id="tq-${key}" data-tq="${key}" value="${esc(st.q)}" placeholder="${cfg.ph || 'Search…'}" aria-label="Search table"></div>` : ''}${fl}${anyF ? `<button class="btn btn-sm btn-g" data-a="tclear" data-k="${key}">${ic('x')}Clear</button>` : ''}<span class="sp"></span>${cfg.tools || ''}${cfg.exp !== false ? btn('Export', 'texport', { cls:'btn-sm', icon:'download', data:`data-k="${key}"`, perm:(cfg.perm || 'booking') + '.export' }) : ''}</div>`;
  const sb = cfg.select && selN ? `<div class="selbar">${selN} selected <button class="btn btn-sm" data-a="texport" data-k="${key}" data-sel="1">${ic('download')}Export selected</button><button class="btn btn-sm btn-g" data-a="tselclear" data-k="${key}">Clear selection</button>${cfg.bulk || ''}</div>` : '';
  const allSel = view.length && view.every(r => st.sel.includes(r.id));
  const head = `<tr>${cfg.select ? `<th class="cbx"><input type="checkbox" aria-label="Select all on page" data-ch="tselall" data-k="${key}" ${allSel ? 'checked' : ''}></th>` : ''}${cfg.cols.map((c, i) => `<th class="${c.al || ''} ${c.v && c.sort !== false ? 's' : ''}" ${c.v && c.sort !== false ? `data-a="tsort" data-k="${key}" data-i="${i}"` : ''} ${st.sort === i ? `aria-sort="${st.dir > 0 ? 'ascending' : 'descending'}"` : ''}>${c.h}${st.sort === i ? ic(st.dir > 0 ? 'arrow-up' : 'arrow-down') : ''}</th>`).join('')}</tr>`;
  const body = view.map(r => `<tr ${cfg.open ? `class="click" ${cfg.open(r)}` : ''}>${cfg.select ? `<td class="cbx"><input type="checkbox" aria-label="Select row" data-ch="tsel" data-k="${key}" data-id="${r.id}" ${st.sel.includes(r.id) ? 'checked' : ''}></td>` : ''}${cfg.cols.map(c => `<td class="${c.al || ''} ${c.cls || ''}">${c.r ? c.r(r) : esc(c.v ? c.v(r) : '')}</td>`).join('')}</tr>`).join('');
  const foot = cfg.foot ? `<tfoot><tr>${cfg.select ? '<td></td>' : ''}${cfg.foot(rows)}</tr></tfoot>` : '';
  const emp_ = !rows.length ? (anyF ? empty('search-x', 'No matching records', 'Try a different search or clear the filters.', `<button class="btn" data-a="tclear" data-k="${key}">Clear filters</button>`) : (cfg.empty || empty('inbox', 'Nothing here yet', 'Records you add will appear here.'))) : '';
  const pag = !cfg.noPage && rows.length > ps ? `<div class="tpag">Showing ${st.page * ps + 1}–${Math.min(rows.length, (st.page + 1) * ps)} of ${rows.length}<div class="r"><button class="btn btn-sm" data-a="tpage" data-k="${key}" data-d="-1" ${st.page === 0 ? 'disabled' : ''}>${ic('chevron-left')}Previous</button><button class="btn btn-sm" data-a="tpage" data-k="${key}" data-d="1" ${st.page >= pages - 1 ? 'disabled' : ''}>Next${ic('chevron-right')}</button></div></div>` : rows.length ? `<div class="tpag">${rows.length} record${rows.length === 1 ? '' : 's'}${cfg.footNote ? ' · ' + cfg.footNote : ''}</div>` : '';
  return `${bar_}${sb}${rows.length ? `<div class="tw"><table class="tbl">${'<thead>' + head + '</thead>'}<tbody>${body}</tbody>${foot}</table></div>` : emp_}${pag}`;
}
function presetTable(p) { if (!p) return; const [key, kvp] = p.split('|'); const st = UI.t[key] = { q:'', sort:null, dir:1, page:0, f:{}, sel:[] }; if (kvp) kvp.split('&').forEach(x => { const [k, v] = x.split('='); if (k === 'q') st.q = v; else st.f[k] = v; }); }

/* ---------- Forms ---------- */
function fieldHtml(f, val, fid) {
  if (f.type === 'sec') return `<div class="fsec">${f.l}</div>`;
  if (f.type === 'html') return `<div class="fld full" data-fk="${f.k || ''}">${f.html}</div>`;
  const id = `${fid}-${f.k}`, v = val ?? f.def ?? '';
  let inp;
  if (f.type === 'select') inp = `<select id="${id}" name="${f.k}">${f.ph !== false ? `<option value="">${f.ph || 'Select…'}</option>` : ''}${(f.opts || []).map(o => { const [ov, ol] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(ov)}" ${String(ov) === String(v) ? 'selected' : ''}>${esc(ol)}</option>`; }).join('')}</select>`;
  else if (f.type === 'textarea') inp = `<textarea id="${id}" name="${f.k}" rows="${f.rows || 3}" placeholder="${esc(f.ph || '')}">${esc(v)}</textarea>`;
  else if (f.type === 'checkbox') inp = `<label class="chk"><input type="checkbox" id="${id}" name="${f.k}" ${v ? 'checked' : ''}> ${esc(f.cl || '')}</label>`;
  else if (f.type === 'file') inp = `<input type="file" id="${id}" name="${f.k}" accept="${f.accept || ''}">`;
  else inp = `<input id="${id}" name="${f.k}" type="${f.type === 'money' || f.type === 'number' ? 'number' : (f.type || 'text')}" value="${esc(v)}" ${f.type === 'money' ? 'step="1" min="0" inputmode="numeric"' : ''} ${f.type === 'number' ? `step="${f.step || 1}" min="${f.min ?? 0}"` : ''} placeholder="${esc(f.ph || '')}" ${f.ro ? 'readonly' : ''} autocomplete="off">`;
  return `<div class="fld ${f.full ? 'full' : ''}" data-fk="${f.k}" ${f.hide ? 'hidden' : ''}>${f.type === 'checkbox' ? '' : `<label for="${id}">${esc(f.l)}${f.req ? ' <span class="req">*</span>' : ''}${f.opt ? ' <span class="mut3" style="font-weight:400">(optional)</span>' : ''}</label>`}${f.type === 'money' ? `<div class="money"><span>PKR</span>${inp}</div>` : inp}${f.help ? `<small class="help">${f.help}</small>` : ''}<small class="err" hidden></small></div>`;
}
function readForm(form, fields) {
  const v = {}; fields.forEach(f => { if (!f.k || f.type === 'sec' || f.type === 'html') return; const el = form.elements[f.k]; if (!el) return;
    if (f.type === 'checkbox') v[f.k] = el.checked; else if (f.type === 'file') v[f.k] = el.files && el.files[0] || null;
    else if (f.type === 'money' || f.type === 'number') v[f.k] = el.value === '' ? null : Number(el.value); else v[f.k] = el.value.trim(); });
  return v;
}
function validate(fields, v, form) {
  const err = {};
  fields.forEach(f => { if (!f.k || f.type === 'sec' || f.type === 'html') return; const box = form.querySelector(`[data-fk="${f.k}"]`); if (box && box.hidden) return; const x = v[f.k];
    if (f.req && (x === '' || x == null || x === false)) { err[f.k] = 'This field is required.'; return; }
    if ((f.type === 'money' || f.type === 'number') && x != null) { if (!Number.isFinite(x)) err[f.k] = 'Enter a valid number.'; else if (f.type === 'money' && !Number.isInteger(x)) err[f.k] = 'Enter a whole rupee amount (no decimals).'; else if (x < (f.min ?? 0)) err[f.k] = `Must be at least ${f.min ?? 0}.`; else if (f.max != null && x > f.max) err[f.k] = `Must not exceed ${num(f.max)}.`; }
    if (f.type === 'date' && x && !/^\d{4}-\d{2}-\d{2}$/.test(x)) err[f.k] = 'Enter a valid date.';
    if (f.type === 'email' && x && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(x)) err[f.k] = 'Enter a valid email address.';
    if (f.check && !err[f.k]) { const m = f.check(x, v); if (m) err[f.k] = m; } });
  return err;
}
function showErrors(form, err) {
  form.querySelectorAll('.fld').forEach(b => { const k = b.dataset.fk; const e = b.querySelector('.err'); if (!e) return; if (err[k]) { e.hidden = false; e.textContent = err[k]; b.classList.add('bad'); } else { e.hidden = true; b.classList.remove('bad'); } });
  const first = form.querySelector('.fld.bad input,.fld.bad select,.fld.bad textarea'); first && first.focus();
  if (err._) toast(err._, 'err');
}
function openForm(cfg) {
  const fid = 'f' + (++UI.fseq);
  const body = `<form id="${fid}" novalidate>${cfg.intro || ''}<div class="fgrid">${cfg.fields.map(f => fieldHtml(f, cfg.values?.[f.k], fid)).join('')}</div><div class="fprev" id="${fid}-prev"></div><div class="mfoot">${cfg.footLeft ? `<span class="l">${cfg.footLeft}</span>` : ''}<button type="button" class="btn" data-a="mclose">Cancel</button><button class="btn btn-p" type="submit">${cfg.submitLabel || 'Save'}</button></div></form>`;
  const m = openModal(cfg.title, body, { sub:cfg.sub, wide:cfg.wide });
  const form = m.querySelector('form');
  const upd = (e) => { const v = readForm(form, cfg.fields); if (cfg.onChange) cfg.onChange(v, form, e && e.target); if (cfg.preview) form.querySelector('.fprev').innerHTML = cfg.preview(readForm(form, cfg.fields), form) || ''; icons(); };
  form.addEventListener('input', upd); form.addEventListener('change', upd); upd();
  form.addEventListener('submit', async e => {
    e.preventDefault(); if (form.dataset.busy) return; const v = readForm(form, cfg.fields); let err = validate(cfg.fields, v, form);
    if (!Object.keys(err).length && cfg.submit) {
      form.dataset.busy = '1'; const sb = form.querySelector('[type=submit]'); sb.disabled = true; const lbl = sb.innerHTML; sb.innerHTML = 'Saving…';
      let r; try { r = await cfg.submit(v, form); } catch (x) { console.error(x); r = { _:'Something went wrong while saving. Nothing was recorded.' }; }
      delete form.dataset.busy; sb.disabled = false; sb.innerHTML = lbl;
      if (r && typeof r === 'object' && 'ok' in r) { if (r.ok) { m.remove(); return; } err = Object.keys(r.errors || {}).length ? r.errors : { _:r.message || 'Could not save.' }; if (r.errors && r.message && !Object.keys(r.errors).some(k => form.querySelector(`[data-fk="${k}"]`))) err._ = Object.values(r.errors)[0] || r.message; }
      else if (r && typeof r === 'object') err = r; else if (r !== false) { m.remove(); return; } else return;
    }
    showErrors(form, err);
  });
  return m;
}
const setOpts = (sel, opts, keep) => { if (!sel) return; const cur = keep ? sel.value : ''; sel.innerHTML = `<option value="">Select…</option>` + opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join(''); if (cur && opts.some(o => o[0] === cur)) sel.value = cur; };
const showFld = (form, k, on) => { const b = form.querySelector(`[data-fk="${k}"]`); if (b) b.hidden = !on; };
const closedCheck = d => d && d <= closedUntil() ? `This date falls in a closed financial period (closed up to ${fd(closedUntil())}).` : null;
const futureCheck = d => d && d > TODAY ? 'Transactions cannot be dated in the future.' : null;

/* ---------- Server API ---------- */
const MOD_IC = { Customers:'user', Enquiries:'inbox', Bookings:'calendar-check', 'Air Tickets':'plane', Visa:'stamp', Umrah:'moon', Tours:'mountain', Hotels:'bed-double', Suppliers:'building-2', Payments:'receipt', Expenses:'wallet', Accounting:'book-open', Refunds:'undo-2', Commissions:'percent', 'Cash & Bank':'landmark', Employees:'user-cog', Branches:'store', 'Sub-Agents':'handshake', Documents:'folder-open', Settings:'settings' };
const CSRF = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
async function api(name, data = {}, file) {
  let body, headers = { 'X-CSRFToken':CSRF(), 'X-Requested-With':'fetch' };
  if (file) { body = new FormData(); body.append('payload', JSON.stringify(data)); body.append('file', file); }
  else { body = JSON.stringify(data); headers['Content-Type'] = 'application/json'; }
  let res;
  try { res = await fetch('/api/action/' + encodeURIComponent(name), { method:'POST', headers, body, credentials:'same-origin' }); }
  catch (e) { UI.serverUp = false; renderHeader(); renderBanners(); const j = { ok:false, message:'Cannot reach the SafarPro server. Make sure the SafarPro window (run_safarpro.bat) is still open.' }; toast(j.message, 'err'); return j; }
  UI.serverUp = true;
  let j; try { j = await res.json(); } catch (e) { j = { ok:false, message:`Unexpected response from the server (${res.status}).` }; }
  if (j.login) { toast(j.message, 'err'); setTimeout(() => location.href = '/login/', 1200); return j; }
  if (j.state) { applyState(j.state); render(); }
  if (j.ok && j.result && j.result.message) toast(j.result.message, /No change|No changes/.test(j.result.message) ? 'info' : 'ok');
  if (!j.ok && (!j.errors || !Object.keys(j.errors).length)) toast(j.message || 'Could not complete the action.', 'err');
  if (j.ok && j.duplicate) toast('This was already saved — the duplicate submission was ignored.', 'info');
  return j;
}
async function refreshState() {
  try { const r = await fetch('/api/state', { credentials:'same-origin' }); if (r.status === 401) { location.href = '/login/'; return; } const j = await r.json(); UI.serverUp = true; applyState(j.state); render(); }
  catch (e) { UI.serverUp = false; renderHeader(); renderBanners(); }
}
async function pingServer() { const was = UI.serverUp; try { const r = await fetch('/api/ping', { cache:'no-store' }); UI.serverUp = r.ok; } catch (e) { UI.serverUp = false; } if (was !== UI.serverUp && S) { renderHeader(); renderBanners(); if (UI.serverUp) toast('Reconnected to the SafarPro server.', 'info'); } }
setInterval(pingServer, 20000);

/* ---------- Shell ---------- */
const NAV = [
  ['Overview', [['dashboard','Dashboard','layout-dashboard']]],
  ['Operations', [['customers','Customers','users'],['enquiries','Enquiries','inbox'],['bookings','Bookings','calendar-check'],['tickets','Air Tickets','plane'],['visas','Visa Management','stamp'],['umrah','Umrah & Hajj','moon'],['tours','Tours & Packages','mountain'],['hotels','Hotels & Transport','bed-double'],['suppliers','Suppliers','building-2']]],
  ['Finance', [['payments','Payments & Receipts','receipt'],['expenses','Expenses','wallet'],['accounting','Accounting','book-open'],['refunds','Refunds','undo-2'],['commissions','Commissions','percent'],['cashbank','Cash & Bank','landmark']]],
  ['Management', [['employees','Employees & Roles','user-cog'],['branches','Branches','store'],['subagents','Sub-Agents','handshake'],['documents','Documents','folder-open'],['reports','Reports & Analytics','activity'],['audit','Audit Trail','scroll-text']]],
  ['System', [['data','Data & Backups','database'],['notifications','Notifications','bell'],['settings','Settings','settings'],['help','Help & Support','life-buoy']]]
];
const PARENT = { customer:'customers', booking:'bookings', visa:'visas', umrahgroup:'umrah', tour:'tours', supplier:'suppliers', subagent:'subagents' };
const PAGE_NAME = {}; const PAGE_GROUP = {}; NAV.forEach(([g, items]) => items.forEach(([k, l]) => { PAGE_NAME[k] = l; PAGE_GROUP[k] = g; }));
const PAGE_PERM = { customers:'customer.view', customer:'customer.view', enquiries:'enquiry.view', bookings:'booking.view', booking:'booking.view', tickets:'ticket.view', visas:'visa.view', visa:'visa.view', umrah:'umrah.view', umrahgroup:'umrah.view', tours:'umrah.view', tour:'umrah.view', hotels:'umrah.view', suppliers:'supplier.view', supplier:'supplier.view', payments:'payment.view', expenses:'expense.view', accounting:'journal.view', refunds:'refund.view', commissions:'commission.view', cashbank:'cash.view', employees:'settings.view', branches:'settings.view', subagents:'agent.view', subagent:'agent.view', documents:'customer.view', reports:'journal.view', audit:'settings.view', data:'settings.view', settings:'settings.view' };
const allowed = r => !PAGE_PERM[r] || can(PAGE_PERM[r]);
function navBadge(k) {
  if (k === 'enquiries') { const n = S.enquiries.filter(e => e.stage === 'New').length; return n ? `<span class="bd">${n}</span>` : ''; }
  if (k === 'refunds') { const n = S.refunds.filter(r => r.status === 'Awaiting Approval').length; return n ? `<span class="bd w">${n}</span>` : ''; }
  if (k === 'data') { const h = S.system?.health; return h && !h.ok ? `<span class="bd w">!</span>` : ''; }
  if (k === 'notifications') { const n = S.notifications.filter(x => !x.read).length; return n ? `<span class="bd">${n}</span>` : ''; }
  if (k === 'subagents') { const n = S.agentReqs.filter(x => x.status === 'Pending').length; return n ? `<span class="bd">${n}</span>` : ''; }
  return '';
}
function renderSidebar() {
  const active = PARENT[UI.route] || UI.route;
  $('#sb').innerHTML = `<div class="brand"><div class="logo"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 17c4.5-1 8-4.5 11-10"/><path d="M14 7l-3.2-.6M14 7l.4 3.3"/><path d="M4 21h16"/><circle cx="18.5" cy="5.5" r="1.6" fill="#9FE2C8" stroke="none"/></svg></div><div><div class="bname">SafarPro</div><div class="btag">BY NEXORA</div></div></div>
  <button class="org" data-a="branchmenu" data-pop="1" title="Switch organization branch"><span class="org-av">${esc(initials(S.org.name))}</span><div><b>${esc(S.org.name)}</b><small>${UI.branch === 'all' ? 'All branches · Pakistan' : esc(brName(UI.branch))}</small></div>${ic('chevrons-up-down')}</button>
  <nav class="nav">${NAV.map(([g, items]) => [g, items.filter(([k]) => allowed(k))]).filter(([g, items]) => items.length).map(([g, items]) => `<div class="ng ${UI.closedGroups[g] ? 'closed' : ''}">${g !== 'Overview' ? `<button class="ng-h" data-a="navgroup" data-g="${g}" aria-expanded="${!UI.closedGroups[g]}"><span>${g}</span>${ic('chevron-down')}</button>` : `<div class="ng-h"><span>${g}</span></div>`}${items.map(([k, l, i]) => `<button class="ni ${active === k ? 'on' : ''}" data-a="go" data-r="${k}" ${active === k ? 'aria-current="page"' : ''} ${UI.collapsed ? `data-tip="${l}"` : ''}>${ic(i)}<span>${l}</span>${navBadge(k)}</button>`).join('')}</div>`).join('')}</nav>
  <div class="sb-foot">${S.app.demo ? `<span class="demo" title="Public online demo with fictional data">${ic('globe')} ONLINE DEMO · v${esc(S.app.version)}</span>` : `<span class="demo" title="Data is stored in a local database on this PC">${ic('hard-drive')} LOCAL · v${esc(S.app.version)}</span>`}<button data-a="collapse" aria-label="${UI.collapsed ? 'Expand' : 'Collapse'} sidebar" data-tip="${UI.collapsed ? 'Expand' : 'Collapse'} sidebar">${ic(UI.collapsed ? 'panel-left-open' : 'panel-left-close')}</button></div>`;
  document.body.classList.toggle('col', !!UI.collapsed);
}
function renderHeader() {
  const r = UI.route, par = PARENT[r] || r;
  const unread = S.notifications.filter(n => !n.read).length;
  const det = PARENT[r] ? (detailTitle() || '') : '';
  const up = UI.serverUp;
  $('#hd').innerHTML = `<button class="ib hamb" data-a="mnav" aria-label="Open menu">${ic('menu')}</button>
  <div class="crumbs"><div class="bc"><button data-a="go" data-r="dashboard">Nexora SafarPro</button>${ic('chevron-right')}<span>${PAGE_GROUP[par] || ''}</span>${det ? ic('chevron-right') + `<button data-a="go" data-r="${par}">${PAGE_NAME[par]}</button>` : ''}</div><div class="pt">${esc(det || PAGE_NAME[par] || '')}</div></div>
  <div class="gs">${ic('search')}<input id="gsearch" placeholder="Search customers, bookings, tickets..." aria-label="Global search" autocomplete="off"><kbd>Ctrl K</kbd></div>
  <div class="hd-r">
   <button class="ib gs-btn" data-a="palette" aria-label="Search">${ic('search')}</button>
   <button class="btn btn-p" data-a="createmenu" data-pop="1" aria-haspopup="menu">${ic('plus')}<span class="create-lbl">Create New</span></button>
   <button class="conn ${up ? '' : 'off'}" data-a="go" data-r="${can('settings.view') ? 'data' : 'dashboard'}" title="${up ? (S.app.demo ? 'Connected to the demo server. Changes are saved until the next demo reset.' : 'Connected to the SafarPro server on this PC. Records are saved in the local database.') : 'The SafarPro server is not responding.'}"><span class="dot"></span><span class="lbl">${up ? (S.app.demo ? 'Demo · saved' : 'Local · saved') : (S.app.demo ? 'Server unreachable' : 'Server stopped')}</span></button>
   <button class="ib" data-a="notifmenu" data-pop="1" aria-label="Notifications (${unread} unread)">${ic('bell')}${unread ? `<span class="cnt">${unread}</span>` : ''}</button>
   <button class="ib help-btn" data-a="go" data-r="help" aria-label="Help">${ic('circle-help')}</button>
   <button class="user" data-a="usermenu" data-pop="1" aria-haspopup="menu"><span class="av">${esc(initials(S.me.name))}</span><span class="ut"><b>${esc(S.me.name)}</b><small>${esc(S.me.role || '')}</small></span>${ic('chevron-down')}</button>
  </div>`;
}
function renderBanners() {
  let h = '';
  if (!UI.serverUp) h += `<div class="banner off">${ic('server-off')}<span><b>The SafarPro server is not responding.</b> Your saved records are safe in the database. Start <b>run_safarpro.bat</b> again, then reload this page.</span><button class="btn btn-sm" data-a="reload">${ic('rotate-ccw')}Reload</button></div>`;
  if (S.app.demo) h += `<div class="banner role">${ic('flask-conical')}<span><b>Public demo — fictional data.</b> Explore freely: changes are shared with other visitors and wiped at the next reset${S.app.demo.nextReset ? ` (${fdt(S.app.demo.nextReset)} PKT)` : ''}. Sign out to try another role.</span></div>`;
  else if (S.org.sampleData) h += `<div class="banner role">${ic('flask-conical')}<span><b>Sample data is loaded.</b> These fictional records are for trying SafarPro. For real use, start with a fresh database (see README → “Starting fresh”).</span></div>`;
  $('#banners').innerHTML = h;
}
function detailTitle() {
  const p = UI.params || {}; const r = UI.route;
  if (r === 'customer') return cust(p.id)?.name; if (r === 'booking') return bk(p.id)?.ref; if (r === 'visa') return byId(S.visas, p.id)?.ref;
  if (r === 'umrahgroup') return byId(S.groups, p.id)?.ref; if (r === 'tour') return byId(S.tours, p.id)?.name; if (r === 'supplier') return sup(p.id)?.name; if (r === 'subagent') return agentOf(p.id)?.name;
}
function go(route, params = {}) {
  if (!PAGES[route] || !allowed(route)) route = 'dashboard';
  if (params.preset) presetTable(params.preset);
  if (params.tab) UI.tabs[route] = params.tab;
  else if (PARENT[route] && (UI.route !== route || UI.params?.id !== params.id)) delete UI.tabs[route];
  if (params.sec) UI.setSec = params.sec;
  UI.route = route; UI.params = { id:params.id };
  closePops(); closeDrawer(); $('#sb').classList.remove('open'); $('#ov').classList.remove('show');
  try { history.replaceState(null, '', '#' + (PARENT[route] || route)); } catch (e) {}
  render(); window.scrollTo(0, 0);
}
const PAGES = {};
function render() {
  const ae = document.activeElement; const fid = ae && ae.id && $('#mn').contains(ae) ? ae.id : null;
  const sel = fid && typeof ae.selectionStart === 'number' ? [ae.selectionStart, ae.selectionEnd] : null;
  if (!S) return;
  if (!allowed(UI.route)) { UI.route = 'dashboard'; UI.params = {}; }
  let html; try { html = (PAGES[UI.route] || PAGES.dashboard)(UI.params || {}); } catch (e) { console.error(e); html = card('', empty('triangle-alert', 'This page could not be displayed', 'Something went wrong while building this view. Your data is safe in the database. Try another page or reload.', btn('Go to dashboard', 'go', { data:'data-r="dashboard"' }))); }
  $('#mn').innerHTML = html; renderSidebar(); renderHeader(); renderBanners(); icons();
  if (fid) { const el = document.getElementById(fid); if (el) { el.focus(); if (sel) try { el.setSelectionRange(sel[0], sel[1]); } catch (e) {} } }
  saveUI();
}

/* ---------- Global search / command palette ---------- */
function searchAll(q) {
  q = q.trim().toLowerCase(); const G = [];
  const pages = Object.entries(PAGE_NAME).filter(([k, l]) => !q || l.toLowerCase().includes(q)).slice(0, q ? 4 : 6).map(([k, l]) => ({ r:k, t:l, s:'Go to page', i:'arrow-right' }));
  if (pages.length) G.push(['Pages', pages]);
  if (q.length < 2) return G;
  const m = (s) => String(s || '').toLowerCase().includes(q);
  const add = (name, list) => { if (list.length) G.push([name, list.slice(0, 5)]); };
  if (q.length < 2) return G;
  add('Customers', S.customers.filter(c => m(c.name) || m(c.code) || m(c.phone) || m(c.email)).map(c => ({ r:'customer', id:c.id, t:c.name, s:`${c.code} · ${c.phone}`, i:'user' })));
  add('Bookings', S.bookings.filter(b => m(b.ref) || m(partyName(b)) || m(b.destination)).map(b => ({ r:'booking', id:b.id, t:`${b.ref} · ${partyName(b)}`, s:`${b.service} · ${b.destination}`, i:'calendar-check' })));
  add('Air tickets', S.tickets.filter(t => m(t.no) || m(t.pnr) || m(t.passenger)).map(t => ({ r:'booking', id:t.bookingId, t:`${t.no} · ${t.passenger}`, s:`PNR ${t.pnr} · ${t.from}–${t.to}`, i:'plane' })));
  add('Visa applications', S.visas.filter(v => m(v.ref) || m(cust(v.customerId)?.name) || m(v.country)).map(v => ({ r:'visa', id:v.id, t:`${v.ref} · ${cust(v.customerId)?.name}`, s:`${v.country} · ${v.status}`, i:'stamp' })));
  add('Suppliers', S.suppliers.filter(s => m(s.name) || m(s.code)).map(s => ({ r:'supplier', id:s.id, t:s.name, s:s.cat, i:'building-2' })));
  add('Receipts & payment references', S.payments.filter(p => m(p.ref) || m(p.txRef)).map(p => ({ r:'booking', id:p.bookingId, t:`${p.ref} · ${pk(p.amount)}`, s:`${p.method}${p.txRef ? ' · ' + p.txRef : ''} · ${fd(p.date)}`, i:'receipt' })));
  return G;
}
function openPalette(q = '') {
  if ($('.palm')) return;
  const el = openModal('Search', `<div class="pal-in">${ic('search')}<input id="pal-q" placeholder="Search customers, bookings, tickets, receipts…" value="${esc(q)}" autocomplete="off" aria-label="Search"></div><div id="pal-r" class="pal-r" role="listbox"></div><div class="pal-f"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span><span style="margin-left:auto">Searches your local database</span></div>`, { cls:'palm' });
  const inp = el.querySelector('#pal-q'), res = el.querySelector('#pal-r');
  const draw = () => { const G = searchAll(inp.value); res.innerHTML = G.length ? G.map(([g, items]) => `<div class="pal-g">${g}</div>` + items.map(it => `<button class="pal-item" data-a="palgo" data-r="${it.r}" ${it.id ? `data-id="${it.id}"` : ''} role="option">${ic(it.i)}<b>${esc(it.t)}</b><small>${esc(it.s)}</small></button>`).join('')).join('') : `<div class="pal-e">No results for “${esc(inp.value)}”.</div>`; const f = res.querySelector('.pal-item'); f && f.classList.add('sel'); icons(); };
  inp.addEventListener('input', draw);
  inp.addEventListener('keydown', e => { const items = [...res.querySelectorAll('.pal-item')]; let i = items.findIndex(x => x.classList.contains('sel'));
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); items[i]?.classList.remove('sel'); i = (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; items[i]?.classList.add('sel'); items[i]?.scrollIntoView({ block:'nearest' }); }
    if (e.key === 'Enter') { e.preventDefault(); items[i]?.click(); } });
  draw(); setTimeout(() => { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }, 30);
}

/* ---------- Charts ---------- */
function niceMax(v) { if (v <= 0) return 1; const p = Math.pow(10, Math.floor(Math.log10(v))); const n = v / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p; }
function barChart(rows, series, H = 250, label = 'Chart') {
  const W = 720, pl = 54, pr = 10, pt = 14, pb = 30; const max = niceMax(Math.max(1, ...rows.flatMap(r => series.map(s => r[s.k]))));
  const iw = W - pl - pr, ih = H - pt - pb, gw = iw / rows.length, bw = Math.min(30, gw * .62 / series.length); let g = '';
  for (let i = 0; i <= 4; i++) { const v = max * i / 4, y = pt + ih - ih * i / 4; g += `<line x1="${pl}" x2="${W - pr}" y1="${y}" y2="${y}" class="grid"/><text x="${pl - 8}" y="${y + 4}" class="axl" text-anchor="end">${short(v)}</text>`; }
  rows.forEach((r, i) => { const cx = pl + gw * i + gw / 2, tw = series.length * bw + (series.length - 1) * 4;
    series.forEach((s, j) => { const v = Math.max(0, r[s.k]), h = ih * v / max, x = cx - tw / 2 + j * (bw + 4); g += `<rect x="${x.toFixed(1)}" y="${(pt + ih - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h, v ? 1 : 0).toFixed(1)}" rx="3" style="fill:${s.c}" data-tip="${esc(r.label)} · ${s.l}: ${pk(r[s.k])}"/>`; });
    g += `<text x="${cx}" y="${H - 9}" class="axl" text-anchor="middle">${r.label}</text>`; });
  return `<svg viewBox="0 0 ${W} ${H}" class="chart" role="img" aria-label="${esc(label)}">${g}</svg>`;
}
function donut(items, centerLabel = 'bookings') {
  const tot = sum(items, i => i.v); const r = 60, C = 2 * Math.PI * r; let off = 0, s = `<circle r="${r}" cx="80" cy="80" fill="none" style="stroke:var(--mut-bg)" stroke-width="22"/>`;
  items.forEach(it => { if (!it.v) return; const len = C * it.v / tot; s += `<circle r="${r}" cx="80" cy="80" fill="none" style="stroke:${it.c}" stroke-width="22" stroke-dasharray="${Math.max(0, len - 2).toFixed(2)} ${(C - len + 2).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" transform="rotate(-90 80 80)" data-tip="${esc(it.l)}: ${it.v} (${(it.v / tot * 100).toFixed(1)}%)"/>`; off += len; });
  return `<svg viewBox="0 0 160 160" class="donut" role="img" aria-label="Bookings by service">${s}<text x="80" y="80" text-anchor="middle" class="dn-v">${tot}</text><text x="80" y="99" text-anchor="middle" class="dn-l">${centerLabel}</text></svg>`;
}

/* ---------- Event wiring ---------- */
const A = {}; const CH = {};
document.addEventListener('click', e => {
  if (!e.target.closest('.pop') && !e.target.closest('[data-pop]')) closePops();
  const el = e.target.closest('[data-a]'); if (!el) return;
  if (el.tagName === 'TR' && e.target.closest('input,select,textarea,label,a')) return;
  const fn = A[el.dataset.a]; if (fn) { e.preventDefault(); fn(el.dataset, el, e); }
});
document.addEventListener('change', e => { const el = e.target; const c = el.dataset && el.dataset.ch; if (c && CH[c]) CH[c](el.type === 'checkbox' ? el.checked : el.value, el.dataset, el); });
document.addEventListener('input', e => {
  const el = e.target;
  if (el.dataset && el.dataset.tq) { const st = UI.t[el.dataset.tq]; st.q = el.value; st.page = 0; render(); }
  if (el.id === 'gsearch') { const v = el.value; el.value = ''; el.blur(); openPalette(v); }
});
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openPalette(); }
  else if (e.key === 'Escape') { if (closeTop()) e.preventDefault(); }
});
document.addEventListener('mouseover', e => { const t = e.target.closest && e.target.closest('[data-tip]'); const tip = $('#tip'); if (t) { tip.textContent = t.dataset.tip; tip.hidden = false; } else tip.hidden = true; });
document.addEventListener('mousemove', e => { const tip = $('#tip'); if (!tip.hidden) { const w = tip.offsetWidth; tip.style.left = Math.min(e.clientX + 12, innerWidth - w - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; } });
// drag & drop (enquiry kanban)
document.addEventListener('dragstart', e => { const c = e.target.closest && e.target.closest('[data-eid]'); if (c) { e.dataTransfer.setData('text/plain', c.dataset.eid); e.dataTransfer.effectAllowed = 'move'; } });
document.addEventListener('dragover', e => { const col = e.target.closest && e.target.closest('.kcol'); if (col) { e.preventDefault(); document.querySelectorAll('.kcol.over').forEach(x => x !== col && x.classList.remove('over')); col.classList.add('over'); } });
document.addEventListener('dragleave', e => { const col = e.target.closest && e.target.closest('.kcol'); if (col && !col.contains(e.relatedTarget)) col.classList.remove('over'); });
document.addEventListener('drop', e => { const col = e.target.closest && e.target.closest('.kcol'); if (col) { e.preventDefault(); col.classList.remove('over'); const id = e.dataTransfer.getData('text/plain'); if (id) moveEnquiry(id, col.dataset.stage); } });


/* generic shell actions */
A.noop = () => {};
A.go = d => { if (d.rep) UI.rep = d.rep; go(d.r, { id:d.id, preset:d.preset, tab:d.tab, sec:d.sec }); };
A.palgo = d => { closeTop(); go(d.r, { id:d.id }); };
A.palette = () => openPalette();
A.mclose = (d, el) => el.closest('.mback')?.remove();
A.dclose = () => closeDrawer();
A.locked = d => toast(`Your current role (${S.me.role}) doesn't have permission for this action.`, 'err');
A.tab = d => { UI.tabs[d.k] = d.v; render(); };
A.collapse = () => { UI.collapsed = !UI.collapsed; render(); };
A.navgroup = d => { UI.closedGroups[d.g] = !UI.closedGroups[d.g]; render(); };
A.mnav = () => { $('#sb').classList.add('open'); $('#ov').classList.add('show'); };
$('#ov').onclick = () => { $('#sb').classList.remove('open'); $('#ov').classList.remove('show'); };
A.tsort = d => { const st = UI.t[d.k]; const i = +d.i; if (st.sort === i) st.dir = -st.dir; else { st.sort = i; st.dir = 1; } render(); };
A.tpage = d => { UI.t[d.k].page += +d.d; render(); };
A.tclear = d => { const st = UI.t[d.k]; st.q = ''; st.f = {}; st.page = 0; render(); };
A.tselclear = d => { UI.t[d.k].sel = []; render(); };
A.texport = d => {
  const cfg = UI.tCfg[d.k], st = UI.t[d.k]; let rows = st.rows || cfg.rows; if (d.sel) rows = rows.filter(r => st.sel.includes(r.id));
  const cols = cfg.cols.filter(c => c.v && c.exp !== false); downloadFile(`safarpro-${d.k}-${TODAY}.csv`, csv(cols, rows)); toast(`Exported ${rows.length} row${rows.length === 1 ? '' : 's'} to CSV.`);
};
CH.tf = (v, d) => { const st = UI.t[d.k]; st.f[d.fk] = v; st.page = 0; render(); };
CH.tsel = (v, d) => { const st = UI.t[d.k]; st.sel = v ? [...new Set([...st.sel, d.id])] : st.sel.filter(x => x !== d.id); render(); };
CH.tselall = (v, d) => { const st = UI.t[d.k]; const cfg = UI.tCfg[d.k]; const ps = cfg.ps || 10; const view = (st.rows || []).slice(st.page * ps, st.page * ps + ps).map(r => r.id); st.sel = v ? [...new Set([...st.sel, ...view])] : st.sel.filter(x => !view.includes(x)); render(); };
CH.branch = v => { UI.branch = v; render(); };
CH.range = v => { UI.range = v; render(); };
A.branchmenu = (d, el) => openPop(el, `<div class="menu"><div class="mh">View data for</div>${[['all', 'All branches (consolidated)'], ...S.branches.map(b => [b.id, b.name])].map(([v, l]) => `<button class="${UI.branch === v ? 'on' : ''}" data-a="setbranch" data-v="${v}">${ic(v === 'all' ? 'layers' : 'store')}${l}</button>`).join('')}<hr><button data-a="go" data-r="branches">${ic('settings-2')}Manage branches</button></div>`, { left:true });
A.setbranch = d => { UI.branch = d.v; closePops(); toast(d.v === 'all' ? 'Showing consolidated data for all branches.' : `Showing data for ${brName(d.v)}.`, 'info'); render(); };
A.createmenu = (d, el) => openPop(el, `<div class="menu" role="menu">${[['newCustomer','New Customer','user-plus'],['newEnquiry','New Enquiry','inbox'],['newBooking','New Booking','calendar-plus'],['newTicket','New Air Ticket','plane'],['newVisa','New Visa Application','stamp'],['newUmrah','New Umrah Booking','moon'],['newTour','New Tour Booking','mountain'],null,['receivePayment','Receive Payment','hand-coins'],['newExpense','Record Expense','wallet'],['newQuote','Create Quotation','file-text']].map(x => x ? `<button role="menuitem" data-a="${x[0]}">${ic(x[2])}${x[1]}</button>` : '<hr>').join('')}</div>`);
A.notifmenu = (d, el) => {
  const list = [...S.notifications].sort((a, b) => a.at < b.at ? 1 : -1).slice(0, 7);
  openPop(el, `<div class="npanel"><div class="np-h"><h4>Notifications</h4><button class="lnk" style="margin-left:auto" data-a="readall">Mark all as read</button></div><div class="np-l">${list.map(n => `<button class="np-i ${n.read ? '' : 'unread'}" data-a="opennotif" data-id="${n.id}"><span class="fi ${n.tone}">${ic({ Payments:'banknote', 'Visa Deadlines':'stamp', 'Travel Departures':'plane-takeoff', 'Supplier Payments':'building-2', 'Booking Updates':'calendar-check', 'System Alerts':'shield-alert' }[n.cat] || 'bell')}</span><span><b>${esc(n.title)}</b><small>${esc(n.text)}</small><em>${n.cat} · ${fdt(n.at)}</em></span></button>`).join('')}</div><div class="np-f"><button class="lnk" data-a="go" data-r="notifications">View all notifications</button></div></div>`);
};
A.opennotif = d => { const n = byId(S.notifications, d.id); if (!n) return; closePops(); if (!n.read) { n.read = true; api('notif.read', { key:n.id }); } go(n.route, n.params || {}); };
A.readall = async () => { closePops(); await api('notif.read', { keys:S.notifications.map(n => n.id) }); toast('All notifications marked as read.'); };
A.usermenu = (d, el) => openPop(el, `<div class="menu" role="menu" style="min-width:250px"><div style="padding:10px 10px 8px;display:flex;gap:10px;align-items:center"><span class="av">${esc(initials(S.me.name))}</span><div><b style="font-size:13px">${esc(S.me.name)}</b><div class="mut" style="font-size:12px">${esc(S.me.username)} · ${esc(S.me.role || '')}</div></div></div><hr><button data-a="profile">${ic('user')}My Profile</button><button data-a="prefs">${ic('sliders-horizontal')}Preferences</button><button data-a="security">${ic('shield-check')}Change password</button><hr><button data-a="signout">${ic('log-out')}Sign out</button></div>`);
A.profile = () => { closePops(); const e = emp(S.me.id) || {}; openModal('My Profile', kv([['Name', esc(S.me.name)], ['Username', esc(S.me.username)], ['Employee ID', esc(e.code || '—')], ['Role', esc(S.me.role || '—')], ['Branch', esc(brName(S.me.branch))], ['Email', esc(S.me.email || '—')]]) + `<div class="mt">${note('Your role and branch are set by an administrator in Employees & Roles.', '', 'info')}</div><div class="mfoot"><button class="btn" data-a="mclose">Close</button></div>`); };
A.prefs = () => { closePops(); let cur = 'system'; try { cur = localStorage.getItem('safarpro-theme') || 'system'; } catch (e) {} openModal('Preferences', `<div class="srow"><div><b>Appearance</b><small>Match Windows or choose a theme. Saved on this PC.</small></div><div class="seg">${['system', 'light', 'dark'].map(t => `<button class="${cur === t ? 'on' : ''}" data-a="theme" data-v="${t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join('')}</div></div><div class="mfoot"><button class="btn btn-p" data-a="mclose">Done</button></div>`); };
A.theme = (d, el) => { if (d.v === 'system') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = d.v; try { localStorage.setItem('safarpro-theme', d.v); } catch (e) {} el.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === el)); };
A.security = () => { closePops(); openForm({ title:'Change password', sub:'Use at least 8 characters. Avoid common words.', fields:[{ k:'current', l:'Current password', type:'password', req:true, full:true }, { k:'new', l:'New password', type:'password', req:true }, { k:'confirm', l:'Repeat new password', type:'password', req:true }], submitLabel:'Change password', submit:async v => { const j = await api('me.password', v); if (j.ok && j.result.relogin) setTimeout(() => location.href = '/login/', 1500); return j; } }); };
A.signout = () => { closePops(); const f = document.createElement('form'); f.method = 'post'; f.action = '/logout/'; f.innerHTML = `<input type="hidden" name="csrfmiddlewaretoken" value="${esc(CSRF())}">`; document.body.appendChild(f); f.submit(); };
A.reload = () => location.reload();
