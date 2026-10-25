/* =========================================================
   Nexora SafarPro — workflows. Every form submits to the Django server,
   which validates, enforces permissions, saves to SQLite and posts the
   accounting entries. The screen then refreshes from the saved data.
   ========================================================= */
const custOpts = (all) => S.customers.filter(c => all || c.status === 'Active').map(c => [c.id, `${c.name} · ${c.code}`]);
const empOpts = () => S.employees.filter(e => e.status === 'Active').map(e => [e.id, `${e.name} · ${e.role}`]);
const supOpts = (cat) => S.suppliers.filter(s => (!cat || s.cat === cat) && s.status === 'Active').map(s => [s.id, `${s.name} · ${s.cat}`]);
const brOpts = () => S.branches.map(b => [b.id, b.name]);
const cashOpts = (only) => CASH_ACCTS.filter(c => !only || ACC[c].group === only).map(c => [c, `${c} · ${ACC[c].name}`]);
const normPhone = p => String(p || '').replace(/\D/g, '').replace(/^92/, '0');
const guard = p => { if (can(p)) return true; A.locked(); return false; };
const myBranch = () => UI.branch !== 'all' ? UI.branch : S.me.branch;
function calcBox(items) { return `<div class="calc">${items.map(([l, v, cls]) => `<div><small>${l}</small><b class="${cls || ''}">${v}</b></div>`).join('')}</div>`; }
const withKey = v => ({ ...v, _key:uid() });
const noSupplierHint = cat => S.suppliers.some(s => !cat || s.cat === cat) ? '' : `No ${cat ? cat.toLowerCase() + ' ' : ''}suppliers yet — add one under Suppliers.`;

/* ---------- Customers ---------- */
function customerForm(c) {
  const edit = !!c;
  openForm({ title: edit ? 'Edit customer' : 'New customer', sub: edit ? c.code : 'Passport and CNIC are optional and stored masked.', wide:true,
    values: edit ? { ...c, passportNo:'', passportExpiry:c.passport?.expiry || '', cnic:'' } : { country:'Pakistan', type:'Individual', branch:myBranch() },
    fields:[
      { type:'sec', l:'Contact' },
      { k:'name', l:'Full name', req:true, ph:'e.g. Ayesha Malik' },
      { k:'phone', l:'Phone number', req:true, ph:'0300-5551234' },
      { k:'email', l:'Email', type:'email', opt:true, ph:'name@example.com' },
      { k:'type', l:'Customer type', type:'select', req:true, opts:['Individual','Corporate','Group Organizer'], ph:false },
      { k:'country', l:'Country', req:true }, { k:'city', l:'City', req:true },
      ...(edit ? [] : [{ k:'branch', l:'Branch', type:'select', opts:brOpts(), ph:false }]),
      { k:'address', l:'Address', full:!edit, opt:true },
      { type:'sec', l:'Identification (optional)' },
      { k:'cnic', l: edit && c.cnic ? `CNIC (on file: ${c.cnic})` : 'CNIC', opt:true, ph:'35202-1234567-1', help:'Only the last digit is stored.' },
      { k:'passportNo', l: edit && c.passport ? `Passport number (on file: ${c.passport.no})` : 'Passport number', opt:true, ph:'AB1234567', help:'Only the last three characters are stored.' },
      { k:'passportExpiry', l:'Passport expiry', type:'date', opt:true },
      { k:'notes', l:'Notes', type:'textarea', full:true, opt:true, ph:'Travel preferences, family members, special requirements…' }
    ],
    submitLabel: edit ? 'Save changes' : 'Create customer',
    submit: async v => { const j = await api('customer.save', withKey({ ...v, id:c?.id })); if (j.ok && !edit && j.result.id) go('customer', { id:j.result.id }); return j; } });
}
A.newCustomer = () => { closePops(); if (guard('customer.create')) customerForm(); };
A.editCustomer = d => { if (guard('customer.edit')) customerForm(cust(d.id)); };
A.custStatus = d => { const c = cust(d.id); if (!guard('customer.edit')) return; const next = c.status === 'Active' ? 'Inactive' : 'Active'; confirmBox(`Mark ${esc(c.name)} as ${next.toLowerCase()}?`, next === 'Inactive' ? 'Inactive customers keep their full history but are hidden from booking forms.' : 'The customer will appear in booking forms again.', `Mark ${next.toLowerCase()}`, () => api('customer.status', { id:c.id })); };
A.importCustomers = () => {
  if (!guard('customer.create')) return;
  const m = openModal('Import customers', `<p class="mut" style="font-size:13px">Paste rows in the format <span class="mono">name, phone, email, type, city</span> (or open a CSV file). Rows whose phone number already exists are skipped, so no duplicates are created.</p><div class="fld full mt"><label for="imp-f">CSV file (optional)</label><input type="file" id="imp-f" accept=".csv,.txt"></div><div class="fld full mt"><label for="imp-t">Rows</label><textarea id="imp-t" rows="7" class="textout" style="min-height:150px" placeholder="Rizwan Haider, 0301-5557001, rizwan@example.com, Individual, Lahore"></textarea></div><div class="mfoot"><button class="btn" data-a="mclose">Cancel</button><button class="btn btn-p" id="imp-go">${ic('upload')}Import rows</button></div>`, { wide:true });
  m.querySelector('#imp-f').onchange = e => { const f = e.target.files[0]; if (!f) return; if (f.size > 2e6) { toast('File is larger than 2 MB.', 'err'); return; } const r = new FileReader(); r.onload = () => m.querySelector('#imp-t').value = String(r.result).replace(/^﻿/, ''); r.readAsText(f); };
  m.querySelector('#imp-go').onclick = async () => {
    const rows = m.querySelector('#imp-t').value.split(/\r?\n/).map(l => l.trim()).filter(Boolean).filter(l => !/^name\s*,/i.test(l)).map(l => { const [name, phone, email, type, city] = l.split(',').map(x => (x || '').trim()); return { name, phone, email, type, city }; });
    if (!rows.length) { toast('Paste at least one row.', 'err'); return; }
    const j = await api('customer.import', { rows }); if (j.ok) m.remove();
  };
};
A.addComm = async d => {
  const f = $('#comm-form'); const text = f.querySelector('textarea').value.trim(); const ch = f.querySelector('select').value;
  if (!text) { toast('Write a note before saving.', 'err'); return; }
  await api('comm.add', { customerId:d.id, channel:ch, text });
};

/* ---------- Enquiries ---------- */
function enquiryForm(e) {
  const edit = !!e;
  openForm({ title: edit ? 'Edit enquiry' : 'New enquiry', wide:true, values: edit ? { ...e, who: e.customerId ? 'existing' : 'lead' } : { who:'existing', emp:S.me.id, source:'WhatsApp', nextFollow:addDays(TODAY, 1), service:'Air Ticket' },
    fields:[
      { k:'who', l:'Enquiry from', type:'select', opts:[['existing','Existing customer'],['lead','New lead (not yet a customer)']], ph:false },
      { k:'customerId', l:'Customer', type:'select', opts:custOpts(), req:true },
      { k:'lead', l:'Lead name', req:true, hide:true, ph:'e.g. Kashif Mehmood' },
      { k:'phone', l:'Lead phone', req:true, hide:true, ph:'0300-5551234' },
      { k:'service', l:'Requested service', type:'select', opts:SERVICES, req:true, ph:false },
      { k:'dest', l:'Destination', req:true, ph:'e.g. Dubai, Hunza, United Kingdom' },
      { k:'travelDate', l:'Expected travel date', type:'date', req:true },
      { k:'value', l:'Estimated value', type:'money', req:true },
      { k:'emp', l:'Assigned to', type:'select', opts:empOpts(), req:true },
      { k:'source', l:'Source', type:'select', opts:['WhatsApp','Walk-in','Phone','Facebook','Email','Referral','Website'], ph:false },
      { k:'nextFollow', l:'Next follow-up', type:'date', req:true }
    ],
    onChange:(v, form) => { const lead = v.who === 'lead'; showFld(form, 'customerId', !lead); showFld(form, 'lead', lead); showFld(form, 'phone', lead); },
    submitLabel: edit ? 'Save' : 'Create enquiry',
    submit: v => api('enquiry.save', withKey({ ...v, id:e?.id })) });
}
A.newEnquiry = () => { closePops(); if (guard('enquiry.create')) enquiryForm(); };
A.editEnquiry = d => { closeDrawer(); enquiryForm(byId(S.enquiries, d.id)); };
function moveEnquiry(id, stage) {
  const e = byId(S.enquiries, id); if (!e || e.stage === stage) return; if (!guard('enquiry.edit')) return;
  if (e.stage === 'Converted') { toast('This enquiry is already converted to a booking. Its history is preserved.', 'info'); return; }
  if (stage === 'Converted') return convertEnquiry(e);
  if (stage === 'Lost') return confirmBox('Mark enquiry as lost?', 'Lost enquiries stay in reports so you can review why sales were missed.', 'Mark as lost', r => { closeDrawer(); api('enquiry.stage', { id, stage, reason:r }); }, { reason:true, ph:'e.g. Chose a cheaper operator' });
  closeDrawer(); api('enquiry.stage', { id, stage });
}
CH.enqStage = (v, d) => moveEnquiry(d.id, v);
A.enqFollow = d => { const e = byId(S.enquiries, d.id); closeDrawer(); openForm({ title:'Add follow-up', sub:e.ref, values:{ date:addDays(TODAY, 2) }, fields:[{ k:'date', l:'Follow-up date', type:'date', req:true }, { k:'note', l:'What to discuss', type:'textarea', full:true, req:true }], submitLabel:'Save follow-up', submit:v => api('enquiry.followup', { ...v, id:e.id }) }); };
A.enqAssign = d => { const e = byId(S.enquiries, d.id); closeDrawer(); openForm({ title:'Assign employee', sub:e.ref, values:{ emp:e.emp }, fields:[{ k:'emp', l:'Assigned to', type:'select', opts:empOpts(), req:true, full:true }], submitLabel:'Assign', submit:v => api('enquiry.assign', { ...v, id:e.id }) }); };
A.enqLost = d => moveEnquiry(d.id, 'Lost');
A.enqConvert = d => { closeDrawer(); convertEnquiry(byId(S.enquiries, d.id)); };
A.openEnquiry = d => {
  const e = byId(S.enquiries, d.id); const who = e.customerId ? cust(e.customerId)?.name : e.lead + ' (lead)';
  const late = e.nextFollow && e.nextFollow < TODAY && !['Converted','Lost'].includes(e.stage);
  openDrawer(`${e.ref} · ${esc(who)}`, `${late ? note(`Follow-up was due on <b>${fd(e.nextFollow)}</b>.`, 'warn', 'clock') + '<div style="height:12px"></div>' : ''}${kv([['Stage', pill(e.stage)], ['Service', esc(e.service)], ['Destination', esc(e.dest)], ['Travel date', fd(e.travelDate)], ['Estimated value', pk(e.value)], ['Assigned to', empName(e.emp)], ['Source', e.source], ['Phone', esc(e.phone || '—')], ['Next follow-up', fd(e.nextFollow)], ['Linked booking', e.bookingId && bk(e.bookingId) ? link(bk(e.bookingId).ref, 'booking', e.bookingId) : '—'], ...(e.lostReason ? [['Lost reason', esc(e.lostReason)]] : [])])}
    <div class="mt" style="display:flex;gap:8px;flex-wrap:wrap">${['Converted','Lost'].includes(e.stage) ? '' : `<label class="fld" style="flex:1;min-width:160px"><span style="font-size:12px;font-weight:550">Move to stage</span><select class="inp" data-ch="enqStage" data-id="${e.id}">${ENQ_STAGES.map(s => `<option ${s === e.stage ? 'selected' : ''}>${s}</option>`).join('')}</select></label>`}</div>
    <div class="mt" style="display:flex;gap:8px;flex-wrap:wrap">${['Converted','Lost'].includes(e.stage) ? '' : btn('Convert to booking', 'enqConvert', { cls:'btn-p btn-sm', icon:'arrow-right-left', data:`data-id="${e.id}"`, perm:'booking.create' }) + sbtn('Create quotation', 'newQuote', { icon:'file-text', data:`data-id="${e.id}"`, perm:'enquiry.create' }) + sbtn('Add follow-up', 'enqFollow', { icon:'calendar-clock', data:`data-id="${e.id}"`, perm:'enquiry.edit' }) + sbtn('Assign', 'enqAssign', { icon:'user-check', data:`data-id="${e.id}"`, perm:'enquiry.edit' }) + sbtn('Edit', 'editEnquiry', { icon:'pencil', data:`data-id="${e.id}"`, perm:'enquiry.edit' }) + sbtn('Mark as lost', 'enqLost', { icon:'x', cls:'btn-d', data:`data-id="${e.id}"`, perm:'enquiry.edit' })}</div>
    <h4 class="mt" style="font-size:13px;margin-top:22px;margin-bottom:10px">History</h4><ul class="tl">${[...e.history].reverse().map(h => `<li><span class="td"></span><div><div class="tt">${esc(h.text)}</div><div class="tm">${fdt(h.at)} · ${esc(h.by)}</div></div></li>`).join('')}</ul>`);
};
async function convertEnquiry(e) {
  if (!guard('booking.create')) return;
  let cid = e.customerId;
  if (!cid) { const j = await api('enquiry.ensureCustomer', { id:e.id }); if (!j.ok) return; cid = j.result.customerId; }
  bookingForm({ customerId:cid, service:e.service, destination:e.dest, travelDate:e.travelDate, price:e.value, emp:e.emp, status:'Pending', enquiryId:e.id });
}

/* ---------- Quotations ---------- */
A.newQuote = d => {
  closePops(); closeDrawer(); if (!guard('enquiry.create')) return; const e = d && d.id ? byId(S.enquiries, d.id) : null;
  const who = e ? (e.customerId ? cust(e.customerId).name : e.lead) : '';
  openForm({ title:'Create quotation', sub: e ? `For ${e.ref}` : 'Share a priced quotation with a customer', wide:true,
    values:{ to:who, title: e ? `${e.service} — ${e.dest}` : '', valid:addDays(TODAY, 3), items: e ? `${e.service} — ${e.dest} | ${e.value}` : '', terms:'Fares are subject to availability until ticketed.' },
    fields:[{ k:'to', l:'Customer / lead', req:true }, { k:'title', l:'Quotation title', req:true }, { k:'items', l:'Line items (one per line: description | amount)', type:'textarea', rows:5, full:true, req:true, ph:'Return airfare LHE–DXB (2 adults) | 172000' }, { k:'valid', l:'Valid until', type:'date', req:true }, { k:'terms', l:'Terms' }],
    preview:v => { const items = (v.items || '').split('\n').filter(l => /\|\s*\d+\s*$/.test(l)); return calcBox([['Line items', items.length], ['Quotation total', pk(sum(items, l => +l.split('|').pop()))]]); },
    submitLabel:'Create quotation',
    submit: async v => {
      const j = await api('quote.create', withKey({ ...v, enquiryId:e?.id || '' }));
      if (j.ok) { const lines = v.items.split('\n').filter(Boolean); const txt = `${S.org.name} — Quotation ${j.result.ref}\nDate: ${fd(TODAY)} · Valid until ${fd(v.valid)}\nTo: ${v.to}\n${v.title}\n\n${lines.map(l => { const p = l.split('|'); return `• ${p.slice(0, -1).join('|').trim()}: PKR ${num(+p.pop())}`; }).join('\n')}\n\nTotal: PKR ${num(j.result.total)}\n${v.terms}\n\n${S.org.phone} · ${S.org.email}`; setTimeout(() => textOut(`Quotation ${j.result.ref}`, txt, 'Copy this into WhatsApp or email. SafarPro does not send messages itself.', { file:`quotation-${j.result.ref}.txt` }), 60); }
      return j;
    } });
};

/* ---------- Bookings ---------- */
function bookingForm(pre = {}) {
  if (!guard('booking.create')) return;
  const depOpts = () => S.deps.filter(d => d.date >= TODAY).map(d => { const t = byId(S.tours, d.tourId); return [d.id, `${t.name} · ${fd(d.date)} · ${d.capacity - d.booked} seats left`]; });
  openForm({ title:'New booking', sub:'Operational status and payment status are tracked separately.', wide:true,
    values:{ status:'Confirmed', pax:1, emp:S.me.id, ...pre },
    intro: !S.customers.length ? note('Add a customer first.', 'warn', 'user-plus') + '<div style="height:12px"></div>' : '',
    fields:[
      { k:'customerId', l:'Customer', type:'select', opts:custOpts(), req:true },
      { k:'service', l:'Service type', type:'select', opts:SERVICES, req:true, ph:false },
      { k:'depId', l:'Tour departure', type:'select', opts:depOpts(), req:true, hide:true, full:true, help: depOpts().length ? '' : 'No upcoming departures — schedule one under Tours & Packages.' },
      { k:'destination', l:'Destination / route', req:true, ph:'e.g. Dubai, LHE → JED' },
      { k:'travelDate', l:'Travel date', type:'date', req:true },
      { k:'pax', l:'Passengers', type:'number', min:1, req:true },
      { k:'passengers', l:'Passenger names', type:'textarea', rows:2, opt:true, ph:'One name per line', full:true },
      { k:'price', l:'Selling price (total)', type:'money', req:true },
      { k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), opt:true, help:noSupplierHint() },
      { k:'cost', l:'Supplier cost (total)', type:'money', def:0, help:'Direct cost of this booking — not an operating expense.' },
      { k:'status', l:'Booking status', type:'select', opts:[['Draft','Draft — not shared with customer'],['Pending','Pending — awaiting confirmation'],['Confirmed','Confirmed — invoice the customer']], ph:false },
      { k:'emp', l:'Assigned employee', type:'select', opts:empOpts(), req:true },
      { k:'override', l:'Override', type:'checkbox', cl:'Authorised capacity override (Administrator only)', hide:true },
      { k:'notes', l:'Notes', type:'textarea', rows:2, opt:true, full:true }
    ],
    onChange:(v, form, t) => {
      const tour = v.service === 'Tour'; showFld(form, 'depId', tour); showFld(form, 'override', tour);
      if (tour && v.depId && t && (t.name === 'depId' || t.name === 'pax' || t.name === 'service')) { const d = byId(S.deps, v.depId); const tr = byId(S.tours, d.tourId); form.elements.destination.value = tr.dest; form.elements.travelDate.value = d.date; form.elements.price.value = tr.price * (v.pax || 1); form.elements.cost.value = tr.cost * (v.pax || 1); if (tr.sup) form.elements.supplierId.value = tr.sup; }
    },
    preview:v => { const m = (v.price || 0) - (v.cost || 0); let cap = ''; if (v.service === 'Tour' && v.depId) { const d = byId(S.deps, v.depId); const left = d.capacity - d.booked; cap = (v.pax || 0) > left ? note(`Only <b>${left}</b> seats are left on this departure.`, 'err', 'circle-alert') : note(`${left} of ${d.capacity} seats available.`, '', 'users'); }
      return calcBox([['Selling price', pk(v.price || 0)], ['Supplier cost', pk(v.cost || 0)], ['Gross margin', pk(m), m < 0 ? 'neg' : 'pos'], ['Margin %', v.price ? (m / v.price * 100).toFixed(1) + '%' : '—']]) + (cap ? '<div style="height:10px"></div>' + cap : '') + (v.status === 'Confirmed' ? '<div style="height:10px"></div>' + note('Confirming posts the invoice to Accounts Receivable and the supplier cost to Accounts Payable.', '', 'book-open') : ''); },
    submitLabel:'Create booking',
    submit: async v => { const j = await api('booking.create', withKey({ ...v, enquiryId:pre.enquiryId || '' })); if (j.ok) go('booking', { id:j.result.id }); return j; } });
}
A.newBooking = d => { closePops(); bookingForm(d && d.cid ? { customerId:d.cid } : {}); };
A.newTour = d => { closePops(); bookingForm({ service:'Tour', depId:d && d.dep || '' }); };
A.confirmBooking = d => { const b = bk(d.id); if (!guard('booking.edit')) return; confirmBox(`Confirm ${b.ref}?`, `This invoices ${esc(partyName(b))} for <b>${pk(b.price)}</b>${b.cost ? ` and records <b>${pk(b.cost)}</b> payable to ${esc(supName(b.supplierId))}` : ''}.`, 'Confirm & invoice', () => api('booking.confirm', { id:b.id })); };
A.completeBooking = d => { if (guard('booking.edit')) api('booking.complete', { id:d.id }); };
A.cancelBooking = d => {
  const b = bk(d.id); if (!guard('booking.edit')) return; const paid = paidOf(b);
  openForm({ title:`Cancel ${b.ref}`, sub:`${partyName(b)} · ${b.service} · ${b.destination}`, values:{ fee:0, supplierCredit:0 },
    intro: note(b.postedOn ? `The invoice of ${pk(b.price)} is reduced to the cancellation fee you keep. ${paid ? `${pk(paid)} has been paid, so any excess becomes a credit to refund.` : ''}` : 'This booking was never invoiced, so no accounting entries are reversed.', '', 'info') + '<div style="height:14px"></div>',
    fields:[{ k:'fee', l:'Cancellation fee kept by agency', type:'money', max:b.price, hide:!b.postedOn }, { k:'supplierCredit', l:'Supplier credit / refund received', type:'money', max:b.cost, hide:!b.postedOn || !b.cost, help:`Up to ${pk(b.cost)}. Reduces what you owe the supplier.` }, { k:'reason', l:'Reason', type:'textarea', req:true, full:true }],
    preview:v => b.postedOn ? calcBox([['Revenue reversed', pk(b.price - (v.fee || 0))], ['Customer paid', pk(paid)], [paid - (v.fee || 0) > 0 ? 'Credit due to customer' : 'Customer still owes', pk(Math.abs(paid - (v.fee || 0))), paid - (v.fee || 0) > 0 ? 'pos' : 'neg'], ['Supplier still owed', pk(b.cost - (v.supplierCredit || 0))]]) : '',
    submitLabel:'Cancel booking', submit:v => api('booking.cancel', { ...v, id:b.id }) });
};
A.editBookingNotes = d => { const b = bk(d.id); openForm({ title:'Edit notes & itinerary', sub:b.ref, values:{ notes:b.notes, passengers:b.passengers.join('\n') }, fields:[{ k:'passengers', l:'Passenger names', type:'textarea', full:true, rows:3 }, { k:'notes', l:'Notes / itinerary', type:'textarea', full:true, rows:5 }], submit:v => api('booking.notes', { ...v, id:b.id }) }); };
A.changeCost = d => { const b = bk(d.id); if (!guard('booking.approve')) return; openForm({ title:'Change supplier cost', sub:`${b.ref} · posts an adjustment entry and is recorded in the audit trail`, values:{ cost:b.cost }, fields:[{ k:'cost', l:'New supplier cost', type:'money', req:true }, { k:'reason', l:'Reason', type:'textarea', req:true, full:true }], submitLabel:'Update cost', submit:v => api('booking.cost', { ...v, id:b.id }) }); };

/* ---------- Payments ---------- */
function paymentForm(pre = {}) {
  if (!guard('payment.create')) return;
  const bOpts = cid => S.bookings.filter(b => b.customerId === cid && !['Refunded','Draft'].includes(b.status) && outstandingFor(b) > 0).map(b => [b.id, `${b.ref} · ${b.service} · ${b.destination} · due ${pk(outstandingFor(b))}`]);
  openForm({ title:'Receive payment', sub:'Partial payments are supported. A receipt number is issued by the server.', wide:true,
    values:{ date:TODAY, method:'Cash', ...pre },
    fields:[
      { k:'customerId', l:'Customer', type:'select', opts:custOpts(true), req:true },
      { k:'bookingId', l:'Booking', type:'select', opts: pre.customerId ? bOpts(pre.customerId) : [], req:true, ph:'Select a booking with a balance' },
      { k:'date', l:'Payment date', type:'date', req:true },
      { k:'method', l:'Payment method', type:'select', opts:S.settings.methods, req:true, ph:false },
      { k:'amount', l:'Amount received', type:'money', req:true, min:1 },
      { k:'txRef', l:'Transaction reference', ph:'Bank / card / wallet reference', check:(v, all) => all.method !== 'Cash' && !v ? 'Required for non-cash payments.' : null },
      { k:'notes', l:'Notes', type:'textarea', rows:2, full:true, opt:true }
    ],
    onChange:(v, form, t) => { if (t && t.name === 'customerId') setOpts(form.elements.bookingId, bOpts(v.customerId)); if (t && t.name === 'bookingId' && v.bookingId && !form.elements.amount.value) form.elements.amount.value = outstandingFor(bk(v.bookingId)); },
    preview:v => { if (!v.bookingId) return v.customerId && !bOpts(v.customerId).length ? note('This customer has no bookings with an outstanding balance.', 'warn', 'circle-alert') : ''; const b = bk(v.bookingId); const out = outstandingFor(b); const a = v.amount || 0; return calcBox([['Booking total', pk(b.price)], ['Paid so far', pk(paidOf(b))], ['Outstanding now', pk(out), out ? 'neg' : ''], ['Remaining after this', pk(Math.max(0, out - a)), out - a > 0 ? 'neg' : 'pos']]) + (!b.postedOn ? '<div style="height:10px"></div>' + note('This booking is not invoiced yet, so this payment is held as a customer advance.', '', 'info') : ''); },
    submitLabel:'Record payment',
    submit: async v => { const j = await api('payment.create', withKey({ bookingId:v.bookingId, date:v.date, method:v.method, amount:v.amount, txRef:v.txRef, notes:v.notes })); if (j.ok && j.result.id) setTimeout(() => showReceipt(j.result.id), 60); return j; } });
}
A.receivePayment = d => { closePops(); const b = d && d.bid ? bk(d.bid) : null; if (b && b.agentId) return A.agentDeposit({ id:b.agentId }); paymentForm(b ? { customerId:b.customerId, bookingId:b.id } : d && d.cid ? { customerId:d.cid } : {}); };
function receiptText(p) { const b = bk(p.bookingId); return `${S.org.name}\n${S.org.address}\n${S.org.phone} · ${S.org.email}\n\nPAYMENT RECEIPT ${p.ref}${p.status === 'Reversed' ? ' (REVERSED)' : ''}\nDate: ${fd(p.date)}\nReceived from: ${partyName(b)}\nBooking: ${b.ref} · ${b.service} · ${b.destination}\nMethod: ${p.method}${p.txRef ? ' · Ref ' + p.txRef : ''}\nAmount: PKR ${num(p.amount)}\n(Rupees ${words(p.amount)} only)\nPrevious balance: PKR ${num(p.prevBal)}\nRemaining balance: PKR ${num(Math.max(0, p.newBal))}\nReceived by: ${empName(p.by)}\n${p.notes ? 'Notes: ' + p.notes + '\n' : ''}`; }
function showReceipt(id) {
  const p = byId(S.payments, id); if (!p) return; const b = bk(p.bookingId);
  const m = openModal(`Receipt ${p.ref}`, `<div class="rcpt" id="print-area"><div class="rc-h"><div><h4>${esc(S.org.name)}</h4><p>${esc(S.org.address)}<br>${esc(S.org.phone)}${S.org.email ? ' · ' + esc(S.org.email) : ''}${S.org.ntn ? '<br>NTN ' + esc(S.org.ntn) : ''}</p></div><div class="rc-t"><b>Payment receipt</b><div class="mono" style="font-size:13px;margin-top:4px">${p.ref}</div><div class="mut" style="font-size:12px">${fd(p.date)}</div></div></div>
   ${p.status === 'Reversed' ? '<div style="height:12px"></div>' + note(`<b>Reversed on ${fd(p.reversedOn)}.</b> ${esc(p.reverseReason)}`, 'err', 'undo-2') : ''}
   <div style="margin-top:14px">${kv([['Received from', esc(partyName(b))], ['Booking', `${b.ref} · ${esc(b.service)} · ${esc(b.destination)}`], ['Payment method', esc(p.method) + (p.txRef ? ` · <span class="mono">${esc(p.txRef)}</span>` : '')]])}</div>
   <div class="rc-amt"><div><small>Amount received</small><b>${pk(p.amount)}</b></div><small>Rupees ${words(p.amount)} only</small></div>
   ${kv([['Previous balance', pk(p.prevBal)], ['Remaining balance', pk(Math.max(0, p.newBal))], ['Received by', empName(p.by)], ['Notes', esc(p.notes || '—')], ['Status', pill(p.status)]])}
   <div class="rc-sig"><div>Customer signature</div><div>For ${esc(S.org.name)}</div></div><div class="rc-foot">Generated by Nexora SafarPro</div></div>
   <div class="mfoot"><span class="l mut" style="font-size:12px;align-self:center">Receipts can't be edited — use a reversal to correct them.</span><button class="btn" data-a="mclose">Close</button><button class="btn" id="rc-copy">${ic('copy')}Copy text</button><button class="btn btn-p" id="rc-print">${ic('printer')}Print</button></div>`, { wide:true, cls:'printable' });
  m.querySelector('#rc-copy').onclick = () => { m.remove(); textOut(`Receipt ${p.ref}`, receiptText(p), '', { file:`receipt-${p.ref}.txt` }); };
  m.querySelector('#rc-print').onclick = () => { document.body.classList.add('printing-modal'); window.print(); setTimeout(() => document.body.classList.remove('printing-modal'), 500); };
}
A.viewReceipt = d => showReceipt(d.id);
A.reversePayment = d => { const p = byId(S.payments, d.id); if (!guard('payment.reverse')) return; if (p.status !== 'Posted') { toast('This receipt is already reversed.', 'info'); return; } confirmBox(`Reverse receipt ${p.ref}?`, `The original receipt stays on record. A reversing entry of <b>${pk(p.amount)}</b> is posted today and the booking balance increases by the same amount.`, 'Reverse receipt', r => api('payment.reverse', { id:p.id, reason:r }), { reason:true, danger:true }); };

/* ---------- Air tickets ---------- */
A.newTicket = () => {
  closePops(); if (!guard('ticket.create')) return;
  openForm({ title:'New air ticket', sub:'Records a ticket issued through your consolidator or airline portal.', wide:true,
    intro: note('Live fares and ticket issuance need a connected airline, consolidator or GDS account — not included in this offline version. Enter the ticket details after issuing.', '', 'plug') + '<div style="height:14px"></div>',
    values:{ status:'Issued', commission:0, fee:0, emp:S.me.id },
    fields:[
      { type:'sec', l:'Passenger' }, { k:'customerId', l:'Customer', type:'select', opts:custOpts(), req:true }, { k:'passenger', l:'Passenger name (as on passport)', req:true },
      { type:'sec', l:'Flight' }, { k:'airline', l:'Airline', type:'select', opts:['PIA','Emirates','Qatar Airways','Saudia','Turkish Airlines','flydubai','Air Arabia','Airblue','Etihad','SereneAir','AirSial','Other'], req:true },
      { k:'from', l:'Origin (IATA)', req:true, ph:'LHE' }, { k:'to', l:'Destination (IATA)', req:true, ph:'DXB' },
      { k:'dep', l:'Departure date', type:'date', req:true }, { k:'ret', l:'Return date', type:'date', opt:true },
      { k:'pnr', l:'PNR', req:true, ph:'6 characters' }, { k:'no', l:'Ticket number', req:true, ph:'176-1234567890' },
      { type:'sec', l:'Pricing' }, { k:'supplierId', l:'Supplier', type:'select', opts:supOpts('Airline / Consolidator'), req:true, help:noSupplierHint('Airline / Consolidator') },
      { k:'cost', l:'Supplier cost (fare + taxes)', type:'money', req:true }, { k:'sell', l:'Selling price (fare)', type:'money', req:true },
      { k:'commission', l:'Commission from supplier', type:'money' }, { k:'fee', l:'Service fee', type:'money' },
      { k:'status', l:'Ticket status', type:'select', opts:[['Issued','Issued'],['On Hold','On hold (reserved, not issued)']], ph:false }, { k:'emp', l:'Ticketing officer', type:'select', opts:empOpts(), req:true },
      { k:'collect', l:'Collect cash payment now', type:'money', opt:true }, { k:'notes', l:'Notes', type:'textarea', rows:2, full:true, opt:true }
    ],
    onChange:(v, form, t) => { if (t && t.name === 'customerId' && !form.elements.passenger.value) { const c = cust(v.customerId); if (c && c.type === 'Individual') form.elements.passenger.value = c.name; } },
    preview:v => { const total = (v.sell || 0) + (v.fee || 0), m = total - (v.cost || 0) + (v.commission || 0); return calcBox([['Customer pays', pk(total)], ['Net cost (cost − commission)', pk((v.cost || 0) - (v.commission || 0))], ['Ticket margin', pk(m), m < 0 ? 'neg' : 'pos']]) + '<div style="height:8px"></div><small class="mut">Margin = selling price + service fee − supplier cost + supplier commission. The booking records the net cost.</small>'; },
    submitLabel:'Save ticket',
    submit: async v => { const j = await api('ticket.create', withKey(v)); if (j.ok) go('booking', { id:j.result.id }); return j; } });
};
A.viewTicket = d => {
  const t = byId(S.tickets, d.id); const b = bk(t.bookingId); const m = t.sell + t.fee - t.cost + t.comm;
  openDrawer(`Ticket ${t.no}`, `${kv([['Passenger', esc(t.passenger)], ['Airline', esc(t.airline)], ['Route', `${t.from} → ${t.to}${t.ret ? ' → ' + t.from : ''}`], ['Departure', fd(t.dep)], ['Return', fd(t.ret)], ['PNR', `<span class="mono">${t.pnr}</span>`], ['Status', pill(t.status)], ['Supplier', esc(supName(t.supplierId))], ['Booking', link(b.ref, 'booking', b.id)], ['Payment status', pill(payStatus(b))]])}
   <h4 style="font-size:13px;margin:20px 0 10px">Ticket profitability</h4>${calcBox([['Selling price', pk(t.sell)], ['Service fee', pk(t.fee)], ['Supplier cost', pk(t.cost)], ['Commission', pk(t.comm)], ['Margin', pk(m), m < 0 ? 'neg' : 'pos']])}
   <div class="mt" style="display:flex;gap:8px;flex-wrap:wrap">${outstandingFor(b) > 0 ? sbtn('Record payment', 'receivePayment', { icon:'hand-coins', data:`data-bid="${b.id}"`, perm:'payment.create' }) : ''}${sbtn('Ticket summary', 'ticketSummary', { icon:'file-text', data:`data-id="${t.id}"` })}${t.status === 'Issued' ? sbtn('Request refund', 'newRefund', { icon:'undo-2', data:`data-bid="${b.id}"`, perm:'refund.create' }) + sbtn('Void ticket', 'voidTicket', { icon:'ban', cls:'btn-d', data:`data-id="${t.id}"`, perm:'ticket.edit' }) : ''}</div>`);
};
A.ticketSummary = d => { const t = byId(S.tickets, d.id); textOut(`Ticket summary ${t.no}`, `${S.org.name} — E-ticket summary\nPassenger: ${t.passenger}\nAirline: ${t.airline}\nTicket: ${t.no} · PNR ${t.pnr}\nRoute: ${t.from} → ${t.to}${t.ret ? ' → ' + t.from : ''}\nDeparture: ${fd(t.dep)}${t.ret ? '\nReturn: ' + fd(t.ret) : ''}\nStatus: ${t.status}\n\nPlease reach the airport 3 hours before departure for international flights.`, '', { file:`ticket-${t.no}.txt` }); };
A.voidTicket = d => { const t = byId(S.tickets, d.id); if (!guard('ticket.edit')) return; confirmBox(`Void ticket ${t.no}?`, `Voiding cancels booking ${esc(bk(t.bookingId).ref)} and fully reverses its revenue and supplier cost (same-day void, supplier credit for the full cost).`, 'Void ticket', r => { closeDrawer(); api('ticket.void', { id:t.id, reason:r }); }, { reason:true, danger:true }); };

/* ---------- Visa ---------- */
A.newVisa = () => {
  closePops(); if (!guard('visa.create')) return;
  openForm({ title:'New visa application', sub:'Creates the application and a pending booking for the fees.', wide:true, values:{ officer:S.me.id, status:'Documents Pending', supplierId:S.suppliers.find(s => s.cat === 'Visa Service Provider')?.id || '' },
    fields:[{ k:'customerId', l:'Customer', type:'select', opts:custOpts(), req:true }, { k:'country', l:'Destination country', req:true, ph:'e.g. United Kingdom' },
      { k:'type', l:'Visa type', req:true, ph:'e.g. Visit, Tourist e-Visa, Business' }, { k:'travel', l:'Intended travel date', type:'date', req:true },
      { k:'emb', l:'Embassy / visa fee', type:'money', req:true, help:'Passed through to the embassy or visa centre.' }, { k:'svc', l:'Service fee', type:'money', req:true, help:'Your agency’s revenue.' },
      { k:'supplierId', l:'Visa service provider', type:'select', opts:supOpts('Visa Service Provider'), opt:true, help:'The embassy fee is owed to this provider.' },
      { k:'officer', l:'Assigned visa officer', type:'select', opts:empOpts(), req:true }, { k:'status', l:'Starting stage', type:'select', opts:['New Enquiry','Documents Pending'], ph:false }, { k:'notes', l:'Notes', type:'textarea', full:true, opt:true }],
    preview:v => { const c = v.customerId && cust(v.customerId); const warn = c && c.passport && v.travel && ddiff(c.passport.expiry, v.travel) < 180 ? note(`Passport expires on <b>${fd(c.passport.expiry)}</b> — less than 6 months after travel.`, 'warn', 'triangle-alert') + '<div style="height:10px"></div>' : c && !c.passport ? note('No passport on file for this customer. It will be marked missing on the checklist.', 'warn', 'triangle-alert') + '<div style="height:10px"></div>' : ''; return warn + calcBox([['Customer pays', pk((v.emb || 0) + (v.svc || 0))], ['Passed to embassy', pk(v.emb || 0)], ['Agency service fee', pk(v.svc || 0), 'pos']]); },
    submitLabel:'Create application',
    submit: async v => { const j = await api('visa.create', withKey(v)); if (j.ok) go('visa', { id:j.result.id }); return j; } });
};
CH.visaStatus = (v, d) => { if (!guard('visa.edit')) { render(); return; } api('visa.status', { id:d.id, status:v }).then(j => { if (!j.ok) render(); }); };
A.visaNext = d => { if (!guard('visa.edit')) return; const va = byId(S.visas, d.id); const i = VISA_STAGES.indexOf(va.status); const nx = { 'Additional Information Required':'Processing', 'Approved':'Passport Returned', 'Rejected':'Passport Returned', 'Passport Returned':'Closed' }[va.status] || VISA_STAGES[i + 1]; if (nx) api('visa.status', { id:va.id, status:nx }); };
A.visaDoc = d => { if (guard('visa.edit')) api('visa.doc', { id:d.id, i:d.i }); };
A.visaReminder = d => { const va = byId(S.visas, d.id); openForm({ title:'Add follow-up reminder', sub:va.ref, values:{ date:addDays(TODAY, 3) }, fields:[{ k:'date', l:'Remind on', type:'date', req:true }, { k:'text', l:'Reminder', req:true, full:true, ph:'e.g. Call VFS for tracking update' }], submit:v => api('visa.reminder', { ...v, id:va.id }) }); };
A.visaRemDone = d => api('visa.reminder', { id:d.id, toggle:d.i });
A.visaNote = d => { const va = byId(S.visas, d.id); openForm({ title:'Edit notes', sub:va.ref, values:{ notes:va.notes }, fields:[{ k:'notes', l:'Notes', type:'textarea', rows:5, full:true }], submit:v => api('visa.notes', { ...v, id:va.id }) }); };

/* ---------- Umrah ---------- */
A.newUmrahPkg = () => { if (!guard('umrah.create')) return; openForm({ title:'New Umrah package', wide:true, values:{ days:15, capacity:40, room:'Quad sharing' }, fields:[{ k:'name', l:'Package name', req:true, full:true }, { k:'days', l:'Duration (days)', type:'number', min:1, req:true }, { k:'capacity', l:'Seats per group', type:'number', min:1, req:true }, { k:'makkah', l:'Makkah hotel', req:true }, { k:'madinah', l:'Madinah hotel', req:true }, { k:'transport', l:'Transport' }, { k:'room', l:'Room type' }, { k:'flight', l:'Flights', full:true }, { k:'cost', l:'Cost per person', type:'money', req:true }, { k:'sell', l:'Selling price per person', type:'money', req:true }, { k:'inc', l:'Inclusions (one per line)', type:'textarea', full:true }, { k:'exc', l:'Exclusions (one per line)', type:'textarea', full:true }], submitLabel:'Create package', submit:v => api('umrah.package', withKey(v)) }); };
A.newUmrah = d => {
  closePops(); if (!guard('umrah.create')) return;
  if (!S.umrahPkgs.length) { toast('Create an Umrah package first.', 'info'); go('umrah', { tab:'packages' }); return; }
  openForm({ title:'New Umrah booking', sub:'Adds pilgrims to a group manifest and creates a pending booking.', wide:true, values:{ pkgId:S.umrahPkgs[0].id, groupId: d && d.gid || '', emp:S.me.id },
    fields:[{ k:'pkgId', l:'Package', type:'select', opts:S.umrahPkgs.map(p => [p.id, `${p.name} · ${pk(p.sell)} per person`]), req:true, ph:false }, { k:'groupId', l:'Group', type:'select', opts:[...S.groups.map(g => [g.id, `${g.ref} · ${g.name} · departs ${fd(g.dep)}`]), ['new', '+ Start a new group']], req:true },
      { k:'gname', l:'New group name', req:true, hide:true, ph:'e.g. Ravi Families — January' }, { k:'gdep', l:'New group departure', type:'date', req:true, hide:true },
      { k:'customerId', l:'Booking customer (payer)', type:'select', opts:custOpts(), req:true }, { k:'emp', l:'Handled by', type:'select', opts:empOpts(), req:true },
      { k:'pilgrims', l:'Pilgrim names (one per line)', type:'textarea', rows:4, full:true, req:true }],
    onChange:(v, form) => { const nw = v.groupId === 'new'; showFld(form, 'gname', nw); showFld(form, 'gdep', nw); },
    preview:v => { const p = byId(S.umrahPkgs, v.pkgId); const n = (v.pilgrims || '').split('\n').filter(x => x.trim()).length; const g = v.groupId && v.groupId !== 'new' ? byId(S.groups, v.groupId) : null; const used = g ? S.pilgrims.filter(x => x.groupId === g.id).length : 0; const left = p.capacity - used;
      return (g && g.pkgId !== p.id ? note(`This group uses <b>${esc(byId(S.umrahPkgs, g.pkgId).name)}</b>.`, 'warn', 'triangle-alert') + '<div style="height:10px"></div>' : '') + (n > left ? note(`Only ${left} places left in this group.`, 'err', 'circle-alert') + '<div style="height:10px"></div>' : '') + calcBox([['Pilgrims', n], ['Price per person', pk(p.sell)], ['Booking total', pk(n * p.sell)], ['Places left after', Math.max(0, left - n)]]); },
    submitLabel:'Create Umrah booking',
    submit: async v => { const j = await api('umrah.book', withKey(v)); if (j.ok) go('umrahgroup', { id:j.result.groupId }); return j; } });
};
A.editPilgrim = d => { const p = byId(S.pilgrims, d.id); if (!guard('umrah.edit')) return; openForm({ title:'Edit pilgrim', sub:p.name, wide:true, values:{ ...p }, fields:[{ k:'name', l:'Full name', req:true }, { k:'passport', l:'Passport status', type:'select', opts:['Valid','Expiring','Missing'], ph:false }, { k:'visa', l:'Visa status', type:'select', opts:['Pending documents','Applied','Approved','Rejected'], ph:false }, { k:'room', l:'Room assignment', ph:'Makkah Q-3 · Madinah Q-3' }, { k:'payment', l:'Payment status (organizer’s record)', type:'select', opts:['Paid','Partial','Pending'], ph:false }, { k:'emergency', l:'Emergency contact' }, { k:'special', l:'Special requirements', full:true }], submit:v => api('pilgrim.update', { ...v, id:p.id }) }); };
A.editGroup = d => { const g = byId(S.groups, d.id); openForm({ title:'Group details', sub:g.ref, values:{ ...g }, fields:[{ k:'flight', l:'Outbound flight', req:true, full:true }, { k:'retFlight', l:'Return flight', req:true, full:true }, { k:'leader', l:'Group leader', req:true }, { k:'status', l:'Status', type:'select', opts:['Registration open','Documents in progress','Ready to travel','Travelling','Completed'], ph:false }], submit:v => api('group.update', { ...v, id:g.id }) }); };
A.manifest = d => { const g = byId(S.groups, d.id); const list = S.pilgrims.filter(p => p.groupId === g.id); downloadFile(`manifest-${g.ref}.csv`, csv([{ h:'#', v:r => list.indexOf(r) + 1 }, { h:'Name', v:r => r.name }, { h:'Gender', v:r => r.gender }, { h:'Passport', v:r => r.passport }, { h:'Visa', v:r => r.visa }, { h:'Room', v:r => r.room }, { h:'Payment', v:r => r.payment }, { h:'Emergency contact', v:r => r.emergency }, { h:'Special requirements', v:r => r.special }], list)); toast('Manifest exported.'); };

/* ---------- Suppliers ---------- */
A.supplierForm = d => { const s = d && d.id ? sup(d.id) : null; if (!guard(s ? 'supplier.edit' : 'supplier.create')) return; openForm({ title: s ? 'Edit supplier' : 'New supplier', wide:true, values: s ? { ...s } : { terms:15, cat:'Airline / Consolidator' }, fields:[{ k:'name', l:'Supplier name', req:true }, { k:'cat', l:'Category', type:'select', opts:SUP_CATS, ph:false }, { k:'terms', l:'Credit terms (days)', type:'number', min:0, req:true }, { k:'contact', l:'Contact person' }, { k:'phone', l:'Phone' }, { k:'email', l:'Email' }, { k:'ntn', l:'NTN / tax ID' }], submitLabel: s ? 'Save' : 'Create supplier', submit:v => api('supplier.save', withKey({ ...v, id:s?.id })) }); };
A.paySupplier = d => {
  if (!guard('supplier.create')) return;
  openForm({ title:'Pay supplier', sub:'Records a payment against the supplier’s outstanding invoices.', values:{ supplierId:d && d.id || '', date:TODAY, account:'1010', method:'Bank Transfer' },
    fields:[{ k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), req:true, full:true }, { k:'amount', l:'Amount', type:'money', req:true, min:1 }, { k:'date', l:'Date', type:'date', req:true }, { k:'account', l:'Paid from', type:'select', opts:cashOpts(), req:true, ph:false }, { k:'method', l:'Method', type:'select', opts:['Bank Transfer','Cash','Cheque'], ph:false }, { k:'txRef', l:'Reference', ph:'IBFT / cheque number' }, { k:'notes', l:'Notes', opt:true }],
    preview:v => { if (!v.supplierId) return ''; const l = supLedger(sup(v.supplierId)); return calcBox([['Payable now', pk(l.balance)], ['Overdue', pk(l.overdue), l.overdue ? 'neg' : ''], ['After payment', pk(l.balance - (v.amount || 0))], ['Account balance', pk(natural(v.account))]]); },
    submitLabel:'Record supplier payment', submit:v => api('supplierPayment.create', withKey(v)) });
};

/* ---------- Expenses ---------- */
A.newExpense = () => {
  closePops(); if (!guard('expense.create')) return;
  openForm({ title:'Record expense', sub:`Expenses above ${pk(S.settings.expenseLimit)} need approval before they post.`, wide:true, values:{ date:TODAY, method:'Cash', account:BR_CASH[myBranch()] || '1010', branch:myBranch() },
    fields:[{ k:'date', l:'Expense date', type:'date', req:true }, { k:'cat', l:'Category', type:'select', opts:Object.keys(EXP_CATS), req:true, help:'Supplier and hotel costs for a booking belong on that booking (as its supplier cost), not here.' }, { k:'desc', l:'Description', req:true, full:true }, { k:'amount', l:'Amount', type:'money', req:true, min:1 }, { k:'method', l:'Payment method', type:'select', opts:['Cash','Bank Transfer','Card'], ph:false }, { k:'account', l:'Paid from', type:'select', opts:cashOpts(), req:true, ph:false }, { k:'branch', l:'Branch', type:'select', opts:brOpts(), req:true, ph:false }, { k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), opt:true }, { k:'file', l:'Attachment (PDF/JPG/PNG, max 10 MB)', type:'file', accept:'.pdf,.jpg,.jpeg,.png', opt:true, full:true }],
    preview:v => v.amount ? note(v.amount > S.settings.expenseLimit ? `Above the ${pk(S.settings.expenseLimit)} limit — this expense will wait for approval.` : 'Within the approval limit — it will be approved and posted automatically.', v.amount > S.settings.expenseLimit ? 'warn' : 'ok', v.amount > S.settings.expenseLimit ? 'clock' : 'circle-check') : '',
    submitLabel:'Save expense', submit:v => { const { file, ...rest } = v; return api('expense.create', withKey(rest), file || undefined); } });
};
A.approveExpense = d => { if (guard('expense.approve')) api('expense.decide', { id:d.id, decision:'approve' }); };
A.rejectExpense = d => { if (!guard('expense.approve')) return; const e = byId(S.expenses, d.id); confirmBox(`Reject ${e.ref}?`, 'Rejected expenses are kept on record but never post to the ledger.', 'Reject expense', r => api('expense.decide', { id:e.id, decision:'reject', reason:r }), { reason:true, danger:true }); };

/* ---------- Refunds ---------- */
const refundMax = (b, cancelFee, fee) => paidOf(b) - refundOf(b) - (b.cancel ? b.cancel.fee : (cancelFee || 0)) - (fee || 0);
A.newRefund = d => {
  closePops(); closeDrawer(); if (!guard('refund.create')) return;
  const opts = S.bookings.filter(b => paidOf(b) - refundOf(b) > 0 && b.status !== 'Refunded' && !S.refunds.some(r => r.bookingId === b.id && !['Completed','Rejected'].includes(r.status))).map(b => [b.id, `${b.ref} · ${partyName(b)} · paid ${pk(paidOf(b))}`]);
  openForm({ title:'Request refund', sub:'Refunds are linked to the original booking and payment and need approval.', wide:true, values:{ bookingId:d && d.bid || '', cancelFee:0, fee:0, method:'Bank Transfer' },
    fields:[{ k:'bookingId', l:'Original booking', type:'select', opts, req:true, full:true }, { k:'cancelFee', l:'Cancellation charge kept', type:'money', help:'Value of the booking the agency keeps (penalty).' }, { k:'fee', l:'Refund processing fee', type:'money' }, { k:'requested', l:'Refund amount requested', type:'money', req:true, min:1 }, { k:'method', l:'Refund method', type:'select', opts:['Bank Transfer','Cash','Card'], ph:false }, { k:'reason', l:'Reason', type:'textarea', full:true, req:true }],
    onChange:(v, form, t) => { if (t && ['bookingId','cancelFee','fee'].includes(t.name) && v.bookingId) { const b = bk(v.bookingId); if (b.cancel) form.elements.cancelFee.value = b.cancel.fee; form.elements.requested.value = Math.max(0, refundMax(b, v.cancelFee, v.fee)); } },
    preview:v => { if (!v.bookingId) return ''; const b = bk(v.bookingId); return (b.cancel ? note(`Already cancelled with a ${pk(b.cancel.fee)} fee — that fee applies.`, '', 'info') + '<div style="height:8px"></div>' : '') + calcBox([['Booking value', pk(b.price)], ['Customer paid', pk(paidOf(b))], ['Charges kept', pk((b.cancel ? b.cancel.fee : (v.cancelFee || 0)) + (v.fee || 0))], ['Max refundable', pk(Math.max(0, refundMax(b, v.cancelFee, v.fee))), 'pos']]); },
    submitLabel:'Submit request', submit: async v => { const j = await api('refund.request', withKey(v)); if (j.ok) go('refunds'); return j; } });
};
A.refundStep = d => api('refund.step', { id:d.id });
A.approveRefund = d => {
  const r = byId(S.refunds, d.id); const b = bk(r.bookingId); if (!guard('refund.approve')) return; const mx = refundMax(b, r.cancelFee, r.fee);
  openForm({ title:`Approve refund ${r.ref}`, sub:`${partyName(b)} · ${b.ref}`, values:{ approved:Math.min(r.requested, mx), supplierCredit:0 },
    intro: kv([['Requested', pk(r.requested)], ['Reason', esc(r.reason)], ['Customer paid', pk(paidOf(b))], ['Charges kept', pk(r.cancelFee + r.fee)]]) + '<div style="height:14px"></div>',
    fields:[{ k:'approved', l:'Approved amount', type:'money', req:true, min:1, max:mx }, { k:'supplierCredit', l:'Supplier credit / refund received', type:'money', max:b.cost, hide:!!b.cancel || !b.cost, help:`Up to ${pk(b.cost)}.` }, { k:'note', l:'Approval note', opt:true, full:true }],
    preview:() => note(b.cancel ? 'The booking is already cancelled.' : `On approval ${b.ref} is cancelled and its revenue reduced to the charges kept (${pk(r.cancelFee)}). The payout is recorded when you mark the refund paid.`, '', 'info'),
    submitLabel:'Approve refund', submit:v => api('refund.approve', { ...v, id:r.id }) });
};
A.completeRefund = (d, el) => { if (!guard('refund.approve')) return; if (el) el.disabled = true; api('refund.complete', withKey({ id:d.id })); };
A.rejectRefund = d => { const r = byId(S.refunds, d.id); if (!guard('refund.approve')) return; confirmBox(`Reject ${r.ref}?`, 'The booking and payments are left unchanged.', 'Reject refund', reason => api('refund.reject', { id:r.id, reason }), { reason:true, danger:true }); };
A.openRefund = d => {
  const r = byId(S.refunds, d.id); const b = bk(r.bookingId); const p = byId(S.payments, r.paymentId);
  openDrawer(`Refund ${r.ref}`, `<div class="steps">${REFUND_STAGES.map((s, i) => { const ci = REFUND_STAGES.indexOf(r.status); return `<div class="step ${r.status === 'Rejected' ? (i === 0 ? 'done' : '') : i < ci ? 'done' : i === ci ? 'cur' : ''}"><i></i>${s}</div>`; }).join('')}</div>${r.status === 'Rejected' ? '<div style="height:10px"></div>' + note('<b>Rejected.</b> ' + esc(r.rejectReason || ''), 'err', 'x') : ''}<div class="mt">${kv([['Status', pill(r.status)], ['Original booking', link(b.ref, 'booking', b.id)], ['Original payment', p ? p.ref : '—'], ['Customer', esc(partyName(b))], ['Requested', pk(r.requested)], ['Approved', r.approved != null ? pk(r.approved) : '—'], ['Cancellation charge', pk(r.cancelFee)], ['Processing fee', pk(r.fee)], ['Supplier credit', pk(r.supplierCredit)], ['Refund method', r.method], ['Reason', esc(r.reason)], ['Requested by', esc(r.reqBy)], ['Approved by', esc(r.apprBy || '—')]])}</div>
   <h4 style="font-size:13px;margin:20px 0 10px">Financial impact</h4>${calcBox([['Revenue reversed', pk(r.status === 'Requested' || r.status === 'Under Review' || r.status === 'Awaiting Approval' ? 0 : b.price - r.cancelFee)], ['Fee income', pk(r.fee)], ['Cash paid out', pk(r.status === 'Completed' ? r.approved : 0)]])}
   <div class="mt" style="display:flex;gap:8px;flex-wrap:wrap">${refundActions(r)}</div>
   <h4 style="font-size:13px;margin:20px 0 10px">History</h4><ul class="tl">${r.history.map(h => `<li><span class="td"></span><div><div class="tt">${esc(h.text)}</div><div class="tm">${fdt(h.at)} · ${esc(h.by)}</div></div></li>`).join('')}</ul>`);
};
function refundActions(r) {
  const id = `data-id="${r.id}"`;
  if (r.status === 'Requested') return sbtn('Start review', 'refundStep', { icon:'search', data:id, perm:'refund.create' }) + sbtn('Reject', 'rejectRefund', { cls:'btn-d', icon:'x', data:id, perm:'refund.approve' });
  if (r.status === 'Under Review') return sbtn('Send for approval', 'refundStep', { icon:'send', data:id, perm:'refund.create' }) + sbtn('Reject', 'rejectRefund', { cls:'btn-d', icon:'x', data:id, perm:'refund.approve' });
  if (r.status === 'Awaiting Approval') return sbtn('Approve', 'approveRefund', { cls:'btn-p', icon:'check', data:id, perm:'refund.approve' }) + sbtn('Reject', 'rejectRefund', { cls:'btn-d', icon:'x', data:id, perm:'refund.approve' });
  if (r.status === 'Approved') return sbtn('Start processing', 'refundStep', { icon:'loader', data:id, perm:'refund.approve' }) + sbtn('Mark paid', 'completeRefund', { cls:'btn-p', icon:'banknote', data:id, perm:'refund.approve' });
  if (r.status === 'Processing') return sbtn('Mark paid', 'completeRefund', { cls:'btn-p', icon:'banknote', data:id, perm:'refund.approve' });
  return '';
}

/* ---------- Commissions ---------- */
A.commApprove = d => api('commission.decide', { id:d.id, decision:'approve' });
A.commPay = d => { const c = byId(S.commissions, d.id); confirmBox(`Pay ${c.ref}?`, `Posts ${pk(c.amount)} to Staff Incentives & Commissions, paid from the main bank account.`, 'Record payment', () => api('commission.decide', withKey({ id:d.id, decision:'pay' }))); };
A.commReverse = d => { const c = byId(S.commissions, d.id); if (!guard('commission.reverse')) return; confirmBox(`Reverse ${c.ref}?`, 'Use this when the underlying booking was cancelled. Reversed commissions stay visible in statements.', 'Reverse commission', r => api('commission.decide', { id:c.id, decision:'reverse', reason:r }), { reason:true, danger:true }); };
A.editRule = d => { const r = byId(S.commRules, d.id); if (!guard('settings.edit')) return; openForm({ title:'Edit commission rule', sub:`${r.kind} · ${r.service}`, values:{ basis:r.basis, rate:r.rate }, fields:[{ k:'basis', l:'Basis', type:'select', opts:['% of margin','% of selling price','Fixed per booking','Fixed per passenger'], ph:false }, { k:'rate', l:'Rate', type:'number', step:'0.25', req:true, help:'Percentage or PKR amount, depending on the basis.' }], submit:v => api('commRule.update', { ...v, id:r.id }) }); };

/* ---------- Accounting ---------- */
A.newJournal = d => {
  if (!guard('journal.create')) return; const opening = d && d.opening;
  const opts = ACCOUNTS.filter(a => !['1100','2000'].includes(a.code)).map(a => `<option value="${a.code}">${a.code} · ${esc(a.name)}</option>`).join('');
  const row = i => `<tr><td><select class="inp" style="width:100%" name="a${i}" aria-label="Account line ${i + 1}"><option value="">Select account…</option>${opts}</select></td><td><input class="inp r" style="width:120px" type="number" min="0" step="1" name="d${i}" placeholder="0" aria-label="Debit"></td><td><input class="inp r" style="width:120px" type="number" min="0" step="1" name="c${i}" placeholder="0" aria-label="Credit"></td></tr>`;
  const m = openModal(opening ? 'Record opening balances' : 'New journal entry', `<form id="jf" novalidate>${opening ? note('Enter the cash and bank balances you start with as debits, and the total as a credit to <b>3000 Owner Capital</b>.', '', 'info') + '<div style="height:12px"></div>' : ''}<div class="fgrid"><div class="fld"><label for="jf-date">Date <span class="req">*</span></label><input id="jf-date" type="date" name="date" value="${TODAY}"></div><div class="fld"><label for="jf-memo">Narration <span class="req">*</span></label><input id="jf-memo" name="memo" value="${opening ? 'Opening balances' : ''}" placeholder="e.g. Reclassify marketing expense"></div></div>
    <div class="tw mt"><table class="tbl"><thead><tr><th>Account</th><th class="r">Debit</th><th class="r">Credit</th></tr></thead><tbody>${[0, 1, 2, 3, 4, 5].map(row).join('')}</tbody><tfoot><tr><td>Totals</td><td class="r" id="jf-dt">0</td><td class="r" id="jf-ct">0</td></tr></tfoot></table></div>
    <div class="mt" id="jf-msg"></div><small class="mut" style="display:block;margin-top:8px">Receivable and payable control accounts are updated only through bookings, receipts and supplier payments.</small>
    <div class="mfoot"><button type="button" class="btn" data-a="mclose">Cancel</button><button class="btn btn-p" type="submit">Post journal</button></div></form>`, { wide:true });
  const f = m.querySelector('form'); const lines = () => [0, 1, 2, 3, 4, 5].map(i => ({ acct:f.elements['a' + i].value, dr:int(f.elements['d' + i].value), cr:int(f.elements['c' + i].value) })).filter(l => l.acct || l.dr || l.cr);
  const upd = () => { const L = lines(); const dt = sum(L, l => l.dr), ct = sum(L, l => l.cr); m.querySelector('#jf-dt').textContent = num(dt); m.querySelector('#jf-ct').textContent = num(ct); m.querySelector('#jf-msg').innerHTML = dt || ct ? (dt === ct ? note('Balanced — debits equal credits.', 'ok', 'circle-check') : note(`Out of balance by ${pk(Math.abs(dt - ct))}.`, 'err', 'circle-alert')) : ''; };
  f.addEventListener('input', upd);
  f.addEventListener('submit', async e => { e.preventDefault(); const L = lines(); const dt = sum(L, l => l.dr), ct = sum(L, l => l.cr); if (dt !== ct) { toast(`Debits (${pk(dt)}) must equal credits (${pk(ct)}).`, 'err'); return; } const j = await api('journal.create', withKey({ date:f.elements.date.value, memo:f.elements.memo.value.trim(), lines:L })); if (j.ok) m.remove(); });
};
A.closePeriod = d => { const p = byId(S.periods, d.id); if (!guard('journal.approve')) return; confirmBox(`Close ${esc(p.name)}?`, 'After closing, no transaction can be dated in this period. Corrections must be posted in an open period.', 'Close period', r => api('period.close', { id:p.id, reason:r }), { reason:true, reasonLabel:'Closing note' }); };
A.newPeriod = () => { if (!guard('journal.approve')) return; const t = new Date(TODAY + 'T00:00:00Z'); const s = TODAY.slice(0, 8) + '01'; const e = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 0)).toISOString().slice(0, 10); openForm({ title:'New financial period', values:{ name:MON[t.getUTCMonth()] + ' ' + t.getUTCFullYear(), start:s, end:e }, fields:[{ k:'name', l:'Name', req:true, full:true }, { k:'start', l:'Start', type:'date', req:true }, { k:'end', l:'End', type:'date', req:true }], submit:v => api('period.create', v) }); };

/* ---------- Cash & bank ---------- */
A.dailyClose = () => {
  if (!guard('cash.create')) return;
  const calc = acct => { const open = natural(acct, '0000', addDays(TODAY, -1)); let rec = 0, pay = 0, refunds = 0; S.journal.filter(e => e.date === TODAY).forEach(e => e.lines.forEach(l => { if (l[0] === acct) { rec += l[1]; if (e.src === 'Refund') refunds += l[2]; else pay += l[2]; } })); return { open, rec, pay, refunds, exp:open + rec - pay - refunds }; };
  openForm({ title:'Daily cash closing', sub:`${fd(TODAY)} · count the physical cash and compare it with the books`, values:{ account:BR_CASH[myBranch()] || cashOpts('Cash')[0]?.[0] },
    fields:[{ k:'account', l:'Cash account', type:'select', opts:cashOpts('Cash'), req:true, ph:false, full:true }, { k:'counted', l:'Physical cash counted', type:'money', req:true }, { k:'note', l:'Explanation', type:'textarea', full:true, opt:true, check:(v, a) => { const c = calc(a.account); return a.counted != null && a.counted !== c.exp && !v ? 'Explain the difference before saving.' : null; } }],
    preview:v => { const c = calc(v.account); const diff = v.counted == null ? null : v.counted - c.exp; return calcBox([['Opening cash', pk(c.open)], ['+ Cash receipts', pk(c.rec)], ['− Cash payments', pk(c.pay)], ['− Cash refunds paid', pk(c.refunds)], ['Expected closing', pk(c.exp)], ['Difference', diff == null ? '—' : pk(diff), diff ? 'neg' : 'pos']]) + '<div style="height:8px"></div><small class="mut">The book balance is never changed to match the count; a difference needs an approved adjustment.</small>'; },
    submitLabel:'Save closing', submit:v => api('closing.create', withKey(v)) });
};
A.approveAdj = d => { const c = byId(S.closings, d.id); if (!guard('cash.approve')) return; confirmBox(`Approve adjustment for ${c.ref}?`, `Posts a cash ${c.diff < 0 ? 'shortage' : 'overage'} of <b>${pk(Math.abs(c.diff))}</b> to “Cash Over / Short”. The original count stays on record.`, 'Approve adjustment', r => api('closing.approve', { id:c.id, reason:r }), { reason:true, reasonLabel:'Approval note' }); };
A.transfer = () => { if (!guard('journal.create')) return; openForm({ title:'Internal transfer', sub:'Move money between your own cash and bank accounts.', values:{ date:TODAY, from:cashOpts('Cash')[0]?.[0], to:'1010', memo:'Cash deposited to bank' }, fields:[{ k:'from', l:'From account', type:'select', opts:cashOpts(), req:true, ph:false }, { k:'to', l:'To account', type:'select', opts:cashOpts(), req:true, ph:false }, { k:'amount', l:'Amount', type:'money', req:true, min:1 }, { k:'date', l:'Date', type:'date', req:true }, { k:'memo', l:'Narration', full:true }], preview:v => calcBox([['From balance', pk(natural(v.from))], ['To balance', pk(natural(v.to))]]), submitLabel:'Record transfer', submit:v => api('transfer.create', withKey(v)) }); };
CH.recMatch = (v, d) => api('bank.match', { entryId:d.k, matched:v });
CH.recStmt = v => api('bank.statement', { value:v });

/* ---------- People & partners ---------- */
A.newEmployee = () => { if (!guard('settings.create')) return; openForm({ title:'Add employee', sub:'Optionally create a login now. Passwords are hashed — nobody can read them later.', wide:true, values:{ role:'Receptionist', branch:myBranch() }, fields:[{ k:'name', l:'Full name', req:true }, { k:'role', l:'Role', type:'select', opts:ROLES, ph:false }, { k:'branch', l:'Branch', type:'select', opts:brOpts(), ph:false }, { k:'email', l:'Email', type:'email', opt:true }, { k:'phone', l:'Phone', opt:true }, { type:'sec', l:'Login (optional)' }, { k:'username', l:'Username', opt:true }, { k:'password', l:'Temporary password', type:'password', opt:true, help:'At least 8 characters, not all numbers.' }], submitLabel:'Add employee', submit:v => api('employee.save', withKey(v)) }); };
A.empRole = d => { const e = emp(d.id); if (!guard('settings.edit')) return; openForm({ title:'Change role', sub:e.name, values:{ role:e.role, branch:e.branch }, fields:[{ k:'role', l:'Role', type:'select', opts:ROLES, ph:false }, { k:'branch', l:'Branch', type:'select', opts:brOpts(), ph:false }, { k:'reason', l:'Reason', req:true, full:true }], submit:v => api('employee.role', { ...v, id:e.id }) }); };
A.empStatus = d => { const e = emp(d.id); if (!guard('settings.edit')) return; const nx = e.status === 'Active' ? 'Suspended' : 'Active'; confirmBox(`${nx === 'Suspended' ? 'Suspend' : 'Reactivate'} ${esc(e.name)}?`, nx === 'Suspended' ? 'They are signed out immediately. Their records and history stay intact.' : 'They can sign in again.', nx === 'Suspended' ? 'Suspend' : 'Reactivate', r => api('employee.status', { id:e.id, reason:r }), { reason:true, danger: nx === 'Suspended' }); };
A.empLogin = d => { const e = emp(d.id); if (!guard('settings.edit')) return; openForm({ title: e.hasLogin ? 'Reset password' : 'Create login', sub:e.name, values:{ username:e.username || '' }, fields:[{ k:'username', l:'Username', req:!e.hasLogin, ro:e.hasLogin }, { k:'password', l: e.hasLogin ? 'New password' : 'Password', type:'password', req:true, help:'Share it privately. Ask them to change it from the user menu.' }], submit:v => api('employee.login', { ...v, id:e.id }) }); };
A.newBranch = () => { if (!guard('settings.create')) return; openForm({ title:'New branch', sub:'A cash-in-hand account is created for the branch automatically.', fields:[{ k:'code', l:'Branch code', req:true, ph:'ISB' }, { k:'name', l:'Branch name', req:true, ph:'Islamabad Branch' }, { k:'city', l:'City', req:true }, { k:'phone', l:'Phone', opt:true }, { k:'address', l:'Address', full:true, opt:true }], submitLabel:'Create branch', submit:v => api('branch.create', withKey(v)) }); };
A.newAgent = () => { if (!guard('agent.create')) return; openForm({ title:'Register sub-agent', sub:'New agents start as pending until approved.', wide:true, values:{ rate:1.5, limit:300000, opening:0 }, fields:[{ k:'name', l:'Agency name', req:true }, { k:'city', l:'City', req:true }, { k:'contact', l:'Contact phone', req:true }, { k:'limit', l:'Credit limit', type:'money', req:true }, { k:'rate', l:'Commission (% of sale)', type:'number', step:'0.25', req:true }, { k:'opening', l:'Opening balance they owe', type:'money', help:'Posted against Owner Capital as an opening balance.' }], submitLabel:'Register agent', submit:v => api('agent.save', withKey(v)) }); };
A.agentApprove = d => api('agent.approve', { id:d.id });
A.agentLimit = d => { const a = agentOf(d.id); if (!guard('agent.approve')) return; closeTop(); openForm({ title:'Change credit limit', sub:a.name, values:{ limit:a.limit }, fields:[{ k:'limit', l:'New credit limit', type:'money', req:true }, { k:'reason', l:'Reason', req:true, full:true }], submit:v => api('agent.limit', { ...v, id:a.id }) }); };
A.newAgentReq = d => { if (!guard('agent.create')) return; const act = S.agents.filter(a => a.status === 'Active'); if (!act.length) { toast('Register and approve a sub-agent first.', 'info'); return; } openForm({ title:'Log agent booking request', sub:'For requests received by phone or WhatsApp. Approval runs a credit check.', wide:true, values:{ agentId:d && d.id || act[0].id, service:'Air Ticket', pax:1, travelDate:addDays(TODAY, 14) }, fields:[{ k:'agentId', l:'Sub-agent', type:'select', opts:act.map(a => [a.id, a.name]), req:true, ph:false }, { k:'service', l:'Service', type:'select', opts:SERVICES, ph:false }, { k:'desc', l:'Request', req:true, full:true, ph:'e.g. SKT → DXB · 3 pax · flydubai' }, { k:'pax', l:'Passengers', type:'number', min:1, req:true }, { k:'travelDate', l:'Travel date', type:'date', req:true }, { k:'amount', l:'Selling amount', type:'money', req:true }, { k:'cost', l:'Supplier cost', type:'money', req:true }, { k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), opt:true }], submit:v => api('agentReq.create', withKey(v)) }); };
A.agentReq = d => {
  const q = byId(S.agentReqs, d.id); const a = agentOf(q.agentId); if (!guard('agent.approve')) return;
  if (d.v === 'reject') return confirmBox('Reject booking request?', `${esc(a.name)}'s request will be marked rejected.`, 'Reject request', r => api('agentReq.decide', { id:q.id, decision:'reject', reason:r }), { reason:true, danger:true });
  api('agentReq.decide', withKey({ id:q.id, decision:'approve' })).then(j => { if (!j.ok && /Credit limit/.test(j.message || '')) openModal('Credit limit exceeded', `${note(esc(j.message), 'err', 'circle-alert')}<p class="mut mt" style="font-size:13px">Ask the agent to pay down their balance, or raise the limit.</p><div class="mfoot"><button class="btn" data-a="mclose">Close</button>${btn('Change credit limit', 'agentLimit', { cls:'btn-p', data:`data-id="${a.id}"`, perm:'agent.approve' })}</div>`); });
};
A.agentDeposit = d => { const a = agentOf(d.id); if (!guard('payment.create')) return; const bks = S.bookings.filter(b => b.agentId === a.id && balOf(b) > 0); if (!bks.length) { toast('This agent has no open bookings to apply a payment to.', 'info'); return; } openForm({ title:'Record agent payment', sub:a.name, values:{ bookingId:bks[0].id, date:TODAY, method:'Bank Transfer' }, fields:[{ k:'bookingId', l:'Apply to booking', type:'select', opts:bks.map(b => [b.id, `${b.ref} · due ${pk(balOf(b))}`]), req:true, full:true }, { k:'amount', l:'Amount', type:'money', req:true, min:1 }, { k:'date', l:'Date', type:'date', req:true }, { k:'method', l:'Method', type:'select', opts:S.settings.methods, ph:false }, { k:'txRef', l:'Reference' }], submit: async v => { const j = await api('payment.create', withKey(v)); if (j.ok && j.result.id) setTimeout(() => showReceipt(j.result.id), 60); return j; } }); };

/* ---------- Documents ---------- */
A.uploadDoc = d => { if (!guard('customer.edit')) return; openForm({ title:'Upload document', sub:'PDF, JPG, PNG, WEBP, DOCX or XLSX up to 10 MB. Stored on this PC in the SafarPro documents folder.', wide:true, values:{ customerId:d && d.cid || '', type:'Passport' }, fields:[{ k:'type', l:'Document type', type:'select', opts:['Passport','CNIC','Visa','Ticket','Hotel Voucher','Invoice','Receipt','Travel Insurance','Other'], ph:false }, { k:'customerId', l:'Customer', type:'select', opts:custOpts(true), req:true }, { k:'bookingId', l:'Related booking', type:'select', opts:S.bookings.map(b => [b.id, `${b.ref} · ${partyName(b)}`]), opt:true }, { k:'expiry', l:'Expiry date', type:'date', opt:true }, { k:'file', l:'File', type:'file', accept:'.pdf,.jpg,.jpeg,.png,.webp,.docx,.xlsx', req:true, full:true, check:f => !f ? 'Choose a file.' : f.size > 10 * 1024 * 1024 ? 'This file is larger than 10 MB.' : null }], submitLabel:'Upload', submit:v => { const { file, ...rest } = v; return api('document.upload', rest, file); } }); };
A.verifyDoc = d => { closeDrawer(); api('document.verify', { id:d.id }); };
A.openDoc = d => { const doc = byId(S.documents, d.id); const url = `/documents/${doc.id}/file`; const isImg = /^image\//.test(doc.contentType); openDrawer(esc(doc.file), `${isImg ? `<img src="${url}" alt="Preview of ${esc(doc.file)}" style="border-radius:8px;border:1px solid var(--bd);margin-bottom:14px">` : ''}<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap"><a class="btn btn-sm" href="${url}" target="_blank" rel="noopener">${ic('eye')}Open</a><a class="btn btn-sm" href="${url}?download=1">${ic('download')}Download</a></div>${kv([['Type', doc.type], ['Customer', doc.customerId ? link(cust(doc.customerId)?.name, 'customer', doc.customerId) : '—'], ['Booking', doc.bookingId && bk(doc.bookingId) ? link(bk(doc.bookingId).ref, 'booking', doc.bookingId) : '—'], ['Size', (doc.size / 1024).toFixed(0) + ' KB'], ['Uploaded', fd(doc.uploaded) + ' · ' + esc(doc.uploadedBy)], ['Expiry', doc.expiry ? fd(doc.expiry) + (ddiff(doc.expiry, TODAY) < 180 ? ' ' + pill('Expiring', 'warn') : '') : '—'], ['Verification', pill(doc.status)], ['Access', 'Signed-in staff with customer access only.']])}<div class="mt">${doc.status !== 'Verified' ? sbtn('Mark verified', 'verifyDoc', { cls:'btn-p', icon:'badge-check', data:`data-id="${doc.id}"`, perm:'customer.edit' }) : ''}</div>`); };

/* ---------- Hotels & transport ---------- */
const linkOpts = () => [...S.groups.map(g => ['g:' + g.id, `Group ${g.ref}`]), ...S.bookings.filter(b => !['Cancelled','Refunded'].includes(b.status)).map(b => ['b:' + b.id, `${b.ref} · ${partyName(b)}`])];
A.newHotel = () => { if (!guard('umrah.create')) return; openForm({ title:'Add hotel reservation', wide:true, values:{ rooms:1, status:'Pending confirmation' }, fields:[{ k:'hotel', l:'Hotel name', req:true }, { k:'city', l:'City', req:true }, { k:'country', l:'Country', req:true }, { k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), req:true, help:noSupplierHint() }, { k:'room', l:'Room type', req:true }, { k:'rooms', l:'Rooms', type:'number', min:1, req:true }, { k:'checkIn', l:'Check-in', type:'date', req:true }, { k:'checkOut', l:'Check-out', type:'date', req:true }, { k:'link', l:'Link to', type:'select', opts:linkOpts(), opt:true }, { k:'conf', l:'Confirmation reference', opt:true }, { k:'status', l:'Status', type:'select', opts:['Pending confirmation','Confirmed','Cancelled'], ph:false }], intro: note('Hotel costs are part of the linked booking’s supplier cost, so nothing is posted here.', '', 'info') + '<div style="height:12px"></div>', submit:v => api('hotel.create', withKey(v)) }); };
A.confirmHotel = d => { const h = byId(S.hotels, d.id); openForm({ title:'Confirm hotel', sub:h.hotel, fields:[{ k:'conf', l:'Confirmation reference', req:true, full:true }], submit:v => api('hotel.confirm', { ...v, id:h.id }) }); };
A.newTransport = () => { if (!guard('umrah.create')) return; openForm({ title:'Add transport', wide:true, values:{ pax:1, status:'Pending confirmation' }, fields:[{ k:'type', l:'Vehicle / service', req:true, ph:'Coaster (22-seater)' }, { k:'supplierId', l:'Supplier', type:'select', opts:supOpts(), req:true }, { k:'from', l:'Pickup', req:true }, { k:'to', l:'Drop-off', req:true }, { k:'at', l:'Date & time', type:'datetime-local', req:true }, { k:'pax', l:'Passengers', type:'number', min:1, req:true }, { k:'status', l:'Status', type:'select', opts:['Pending confirmation','Confirmed'], ph:false }, { k:'link', l:'Link to', type:'select', opts:linkOpts(), opt:true }], submit:v => api('transport.create', withKey(v)) }); };

/* ---------- Tours ---------- */
A.newTourPkg = () => { if (!guard('umrah.create')) return; openForm({ title:'New tour package', wide:true, values:{ region:'Domestic', days:5, policy:'Full refund up to 15 days before departure. 50% refund 7–14 days before. No refund within 7 days.' }, fields:[{ k:'name', l:'Package name', req:true, full:true }, { k:'dest', l:'Destination', req:true }, { k:'region', l:'Region', type:'select', opts:['Domestic','International'], ph:false }, { k:'days', l:'Duration (days)', type:'number', min:1, req:true }, { k:'sup', l:'Ground supplier', type:'select', opts:supOpts(), opt:true }, { k:'price', l:'Selling price per person', type:'money', req:true }, { k:'cost', l:'Cost per person', type:'money', req:true }, { k:'transport', l:'Transport' }, { k:'hotel', l:'Accommodation' }, { k:'itin', l:'Itinerary (one day per line)', type:'textarea', rows:4, full:true, req:true }, { k:'inc', l:'Inclusions (one per line)', type:'textarea', full:true }, { k:'exc', l:'Exclusions (one per line)', type:'textarea', full:true }, { k:'policy', l:'Cancellation policy', type:'textarea', full:true, req:true }], submitLabel:'Create package', submit: async v => { const j = await api('tour.save', withKey(v)); if (j.ok) go('tour', { id:j.result.id }); return j; } }); };
A.editPolicy = d => { const t = byId(S.tours, d.id); if (!guard('settings.edit')) return; openForm({ title:'Cancellation policy', sub:t.name, values:{ policy:t.policy }, fields:[{ k:'policy', l:'Policy shown on quotations', type:'textarea', rows:4, full:true, req:true }], submit:v => api('tour.policy', { ...v, id:t.id }) }); };
A.addDeparture = d => { const t = byId(S.tours, d.id); if (!guard('umrah.create')) return; openForm({ title:'Schedule departure', sub:t.name, values:{ capacity:20 }, fields:[{ k:'date', l:'Departure date', type:'date', req:true }, { k:'capacity', l:'Seats', type:'number', min:1, req:true }], submit:v => api('tour.departure', { ...v, id:t.id }) }); };

/* ---------- Settings & backups ---------- */
A.saveSettings = () => {
  if (!guard('settings.edit')) return; const box = $('#set-form'); const data = { _section:UI.setSec };
  box.querySelectorAll('[data-set]').forEach(el => { data[el.dataset.set] = el.type === 'checkbox' ? el.checked : el.value; });
  api('settings.save', data).then(j => { if (!j.ok && j.errors) Object.entries(j.errors).forEach(([k, msg]) => toast(msg, 'err')); });
};
A.backupNow = async (d, el) => { if (!guard('settings.edit')) return; if (el) { el.disabled = true; el.innerHTML = 'Creating backup…'; } await api('backup.create', {}); };
CH.npref = (v, d) => api('notif.prefs', { cat:d.k, channel:d.c, value:v });
A.integ = d => openModal(`Connect ${esc(d.v)}`, `${note(`${esc(d.v)} needs an internet connection and an account with a provider. This offline edition does not include it — every other feature works without it.`, '', 'plug')}<div class="mfoot"><button class="btn btn-p" data-a="mclose">OK</button></div>`);
