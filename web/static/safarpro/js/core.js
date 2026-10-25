'use strict';
/* =========================================================
   Nexora SafarPro — client core: formatting, lookups, server state.
   All business data comes from the local Django server (SQLite).
   Balances, payment status and seat counts are computed on the server.
   ========================================================= */
let TODAY = new Date().toISOString().slice(0, 10);
const UIKEY = 'nexora-safarpro-ui-v1';
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const int = n => Math.round(Number(n) || 0);
const num = n => int(n).toLocaleString('en-US');
const pk = n => (int(n) < 0 ? '−' : '') + 'PKR ' + Math.abs(int(n)).toLocaleString('en-US');
const short = n => { const a = Math.abs(n); return a >= 1e6 ? (n/1e6).toFixed(a>=1e7?0:1)+'M' : a >= 1e3 ? Math.round(n/1e3)+'K' : String(Math.round(n)); };
const sum = (a, f) => Math.round(a.reduce((s, x) => s + (f ? f(x) : x), 0) * 100) / 100;
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const fd = d => { if (!d) return '—'; const [y, m, dd] = d.slice(0,10).split('-'); return `${+dd} ${MON[m-1]} ${y}`; };
const fdt = t => t ? `${fd(t)}, ${t.slice(11,16)}` : '—';
const addDays = (d, n) => { const t = new Date(d + 'T00:00:00Z'); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0,10); };
const ddiff = (a, b) => Math.round((new Date(a + 'T00:00:00Z') - new Date(b + 'T00:00:00Z')) / 864e5);
const uid = () => { try { return crypto.randomUUID(); } catch (e) { return 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36); } };
const ic = (n, c = '') => `<svg class="ic ${c}" aria-hidden="true"><use href="#i-${n}"></use></svg>`;
const initials = n => String(n||'?').replace(/\(.*?\)/g,'').split(/\s+/).filter(Boolean).slice(0,2).map(w => w[0]).join('').toUpperCase();
const pad = (n, l) => String(n).padStart(l, '0');
function words(n) {
  n = Math.abs(int(n)); if (!n) return 'Zero';
  const a = ['','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten','Eleven','Twelve','Thirteen','Fourteen','Fifteen','Sixteen','Seventeen','Eighteen','Nineteen'];
  const t = ['','','Twenty','Thirty','Forty','Fifty','Sixty','Seventy','Eighty','Ninety'];
  const two = x => x < 20 ? a[x] : t[Math.floor(x/10)] + (x % 10 ? ' ' + a[x % 10] : '');
  const three = x => x >= 100 ? a[Math.floor(x/100)] + ' Hundred' + (x % 100 ? ' ' + two(x % 100) : '') : two(x);
  const out = []; const cr = Math.floor(n/1e7); n %= 1e7; const lk = Math.floor(n/1e5); n %= 1e5; const th = Math.floor(n/1000); n %= 1000;
  if (cr) out.push(three(cr) + ' Crore'); if (lk) out.push(two(lk) + ' Lakh'); if (th) out.push(two(th) + ' Thousand'); if (n) out.push(three(n));
  return out.join(' ');
}

/* ---------- Reference lists (mirrors the server) ---------- */
const SERVICES = ['Air Ticket','Visa','Umrah','Tour','Hotel','Transport','Other'];
const SVC = { 'Air Ticket':{ic:'plane'}, 'Visa':{ic:'stamp'}, 'Umrah':{ic:'moon'}, 'Tour':{ic:'mountain'}, 'Hotel':{ic:'bed-double'}, 'Transport':{ic:'bus'}, 'Other':{ic:'package'} };
const EXP_CATS = {'Office Rent':'6000','Salaries':'6010','Utilities':'6020','Marketing':'6030','Transport':'6040','Software':'6050','Other':'6090'};
const METHODS = ['Cash','Bank Transfer','Card','Digital Payment'];
const VISA_STAGES = ['New Enquiry','Documents Pending','Documents Verified','Ready to Submit','Submitted','Processing','Additional Information Required','Approved','Rejected','Passport Returned','Closed'];
const REFUND_STAGES = ['Requested','Under Review','Awaiting Approval','Approved','Processing','Completed'];
const ENQ_STAGES = ['New','Contacted','Quotation Sent','Follow-up Required','Converted','Lost'];
const ROLES = ['Owner','Administrator','Branch Manager','Accountant','Ticketing Officer','Visa Officer','Tour Operations Officer','Receptionist','Read-Only Auditor'];
const SUP_CATS = ['Airline / Consolidator','Hotel','Transport Provider','Visa Service Provider','Umrah Package Supplier','Tour Operator','Other Service Provider'];
let ACCOUNTS = [], ACC = {}, CASH_ACCTS = [], BR_CASH = {};

/* ---------- State ---------- */
let S = null;
const UI = { route:'dashboard', params:{}, branch:'all', range:'month', collapsed:false, t:{}, tabs:{}, view:{}, closedGroups:{}, dashHide:{}, rep:'pl', setSec:'general', fseq:0, serverUp:true };
function saveUI() { try { localStorage.setItem(UIKEY, JSON.stringify({ route:UI.route, params:UI.params, branch:UI.branch, range:UI.range, collapsed:UI.collapsed, closedGroups:UI.closedGroups, dashHide:UI.dashHide })); } catch (e) {} }
function loadUI() { try { const u = JSON.parse(localStorage.getItem(UIKEY) || 'null'); if (u) Object.assign(UI, u); } catch (e) {} }
function applyState(st) {
  S = st; TODAY = st.today;
  S.activity = (st.audit || []).map(a => ({ at:a.at, text:`${a.action}${a.ref ? ' · ' + a.ref : ''}`, by:a.user, icon:(typeof MOD_IC !== 'undefined' && MOD_IC[a.module]) || 'circle' }));
  ACCOUNTS = st.accounts; ACC = Object.fromEntries(ACCOUNTS.map(a => [a.code, a]));
  CASH_ACCTS = ACCOUNTS.filter(a => a.group === 'Cash' || a.group === 'Bank').map(a => a.code);
  BR_CASH = Object.fromEntries(st.branches.map(b => [b.id, b.cashAccount]));
  if (UI.branch !== 'all' && !st.branches.some(b => b.id === UI.branch)) UI.branch = 'all';
}

/* ---------- Lookups ---------- */
const byId = (arr, id) => arr.find(x => x.id === String(id));
const cust = id => byId(S.customers, id);
const emp = id => byId(S.employees, id);
const sup = id => byId(S.suppliers, id);
const agentOf = id => byId(S.agents, id);
const bk = id => byId(S.bookings, id);
const empName = id => emp(id)?.name || '—';
const supName = id => sup(id)?.name || '—';
const partyName = b => !b ? '—' : b.customerId ? (cust(b.customerId)?.name || '—') : b.agentId ? (agentOf(b.agentId)?.name || '—') : '—';
const brName = id => byId(S.branches, id)?.name || 'All branches';
const inB = x => UI.branch === 'all' || x.branch === UI.branch;
const me = () => S.me;
const can = p => S.perms.includes(p);
const closedUntil = () => S.periods.filter(p => p.status === 'Closed').reduce((m, p) => p.to > m ? p.to : m, '0000-00-00');

/* ---------- Booking figures (computed by the server) ---------- */
const POSTED = ['Confirmed','Completed','Cancelled','Refunded'];
const paidOf = b => b.paid;
const refundOf = b => b.refunded;
const charged = b => b.charged;
const balOf = b => b.balance;
const dueOf = b => b.due;
const marginOf = b => b.price - b.cost;
const payStatus = b => b.payStatus;
const outstandingFor = b => b.outstanding;
const custBal = id => sum(S.bookings.filter(b => b.customerId === id), balOf);
const agentBal = a => a.balance;
const depBooked = depId => byId(S.deps, depId)?.booked || 0;

/* ---------- Supplier ledger (same rules as finance/ledger.py) ---------- */
function supLedger(s) {
  const inv = S.bookings.filter(b => b.supplierId === s.id && b.postedOn && b.cost > 0).map(b => ({ b, date:b.postedOn, due:addDays(b.postedOn, s.terms), amount:b.cost }));
  const credits = S.bookings.filter(b => b.supplierId === s.id && b.cancel && b.cancel.supplierCredit > 0 && b.postedOn).map(b => ({ b, date:b.cancel.date, amount:b.cancel.supplierCredit }));
  const pays = S.supplierPayments.filter(p => p.supplierId === s.id);
  const invT = sum(inv, i => i.amount), crT = sum(credits, c => c.amount), payT = sum(pays, p => p.amount);
  let pool = payT + crT, overdue = 0, dueSoon = 0;
  inv.sort((a, b) => a.due < b.due ? -1 : 1).forEach(i => { const ap = Math.min(pool, i.amount); pool -= ap; i.open = i.amount - ap; if (i.open > 0) { if (i.due < TODAY) overdue += i.open; else if (ddiff(i.due, TODAY) <= 7) dueSoon += i.open; } });
  const last = [...inv.map(i => i.date), ...pays.map(p => p.date)].sort().pop() || null;
  return { inv, credits, pays, invT, payT, crT, balance: invT - crT - payT, overdue, dueSoon, last };
}

/* ---------- Journal (posted entries from the server) ---------- */
const getJ = () => S.journal;
function acctBal(code, from = '0000', to = '9999') { let d = 0, c = 0; S.journal.forEach(e => { if (e.date < from || e.date > to) return; e.lines.forEach(l => { if (l[0] === code) { d += l[1]; c += l[2]; } }); }); return { d, c, net: d - c }; }
const natural = (code, from, to) => { const a = ACC[code]; if (!a) return 0; const b = acctBal(code, from, to); return (a.type === 'Asset' || a.type === 'Expense') ? b.d - b.c : b.c - b.d; };
function pl(from, to) {
  const rows = ACCOUNTS.filter(a => a.type === 'Income' || a.type === 'Expense').map(a => ({ ...a, amt: natural(a.code, from, to) }));
  const inc = rows.filter(r => r.type === 'Income'), dc = rows.filter(r => r.group === 'Direct cost'), op = rows.filter(r => r.group === 'Operating');
  const ti = sum(inc, r => r.amt), tdc = sum(dc, r => r.amt), top = sum(op, r => r.amt);
  return { inc, dc, op, ti, tdc, gp: ti - tdc, top, np: ti - tdc - top };
}
function subledgerAR() {
  let pos = 0, adv = 0, overdue = 0, cnt = 0, ocnt = 0; const items = [];
  S.bookings.forEach(b => { const v = balOf(b); if (v > 0) { pos += v; cnt++; if (payStatus(b) === 'Overdue') { overdue += v; ocnt++; } items.push(b); } else if (v < 0) adv += -v; });
  const agentOpen = sum(S.agents, a => a.opening);
  return { pos: pos + agentOpen, adv, overdue, cnt, ocnt, agentOpen, items };
}
