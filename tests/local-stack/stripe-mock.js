// Local stand-in for the bits of the Stripe API the tips-* functions use (TEST ONLY, no network, no real key).
// Also exposes /mock/* helpers for tests: enable an account's payouts, "pay" a checkout session (fires a correctly
// signed webhook at tips-webhook), and inspect what was sent. Webhook signing secret: whsec_local_mock.
const http = require('http'), crypto = require('crypto');
const PORT = 54333, HOOK = process.env.TIPS_WEBHOOK_URL || 'http://127.0.0.1:54321/functions/v1/tips-webhook', WHSEC = 'whsec_local_mock';
const accts = {}, sessions = {}; let n = 0; const id = p => `${p}_mock${Date.now().toString(36)}${(n++).toString(36)}`;
const send = (res, s, b) => { res.writeHead(s, { 'content-type': 'application/json' }); res.end(JSON.stringify(b)); };
function sign(payload, t = Math.floor(Date.now() / 1000), secret = WHSEC) { return `t=${t},v1=${crypto.createHmac('sha256', secret).update(`${t}.${payload}`).digest('hex')}`; }
async function fire(ev, header) { const body = JSON.stringify(ev); const r = await fetch(HOOK, { method: 'POST', headers: { 'content-type': 'application/json', 'stripe-signature': header ?? sign(body) }, body }); return { status: r.status, body: await r.text() }; }
http.createServer((req, res) => {
  let raw = ''; req.on('data', c => raw += c); req.on('end', async () => {
    const f = Object.fromEntries(new URLSearchParams(raw)); const u = req.url.split('?')[0];
    if ((u.startsWith('/v1/') || u.startsWith('/v2/')) && !/^Bearer sk_test_/.test(req.headers.authorization || '')) return send(res, 401, { error: { message: 'bad key' } });
    if (u.startsWith('/v2/') && !/^\d{4}-\d{2}-\d{2}\.\w+$/.test(req.headers['stripe-version'] || '')) return send(res, 400, { error: { message: 'v2 needs a Stripe-Version header' } });
    let j = {}; if (u.startsWith('/v2/') && raw) { try { j = JSON.parse(raw); } catch { return send(res, 400, { error: { message: 'bad json' } }); } }
    const v2acct = a => ({ id: a.id, object: 'v2.core.account', dashboard: a.dashboard, contact_email: a.email, metadata: a.metadata, defaults: a.defaults,
      configuration: { recipient: { capabilities: { stripe_balance: { stripe_transfers: { status: a.payouts_enabled ? 'active' : 'restricted' }, payouts: { status: a.payouts_enabled ? 'active' : 'restricted' } } } } },
      requirements: { entries: a.payouts_enabled ? [] : [{ description: 'external_account', minimum_deadline: { status: 'currently_due' } }] } });
    let m;
    if (req.method === 'POST' && u === '/v2/core/accounts') {
      const st = j?.configuration?.recipient?.capabilities?.stripe_balance?.stripe_transfers?.requested, cp = j?.configuration?.merchant?.capabilities?.card_payments?.requested;
      if (!st || !cp) return send(res, 400, { error: { message: 'mock: needs recipient stripe_transfers + merchant card_payments' } });
      if (j.dashboard === 'express' && (j?.defaults?.responsibilities?.fees_collector !== 'application' || j?.defaults?.responsibilities?.losses_collector !== 'application')) return send(res, 400, { error: { message: 'express needs application fees/losses' } });
      const a = { id: id('acct'), type: 'v2', dashboard: j.dashboard, email: j.contact_email, defaults: j.defaults, payouts_enabled: false, charges_enabled: false, details_submitted: false, metadata: j.metadata || {} }; accts[a.id] = a; return send(res, 200, v2acct(a)); }
    if (req.method === 'GET' && (m = u.match(/^\/v2\/core\/accounts\/(acct_\w+)$/))) return accts[m[1]] ? send(res, 200, v2acct(accts[m[1]])) : send(res, 404, { error: { message: 'not found' } });
    if (req.method === 'POST' && u === '/v2/core/account_links') { const o = j?.use_case?.account_onboarding; if (j?.use_case?.type !== 'account_onboarding' || !o?.return_url || !o?.refresh_url || !accts[j.account]) return send(res, 400, { error: { message: 'bad account link' } });
      return send(res, 200, { object: 'v2.core.account_link', url: `http://127.0.0.1:${PORT}/mock/onboard/${j.account}?return=${encodeURIComponent(o.return_url)}` }); }
    if (req.method === 'POST' && u === '/v1/accounts') return send(res, 400, { error: { message: 'Stripe no longer recommends Accounts v1 for new Connect integrations.' } });
    if (false) { const a = { id: id('acct'), object: 'account', type: f.type, email: f.email, details_submitted: false, charges_enabled: false, payouts_enabled: false, metadata: { pod_club_user: f['metadata[pod_club_user]'] } }; accts[a.id] = a; return send(res, 200, a); }
    if (req.method === 'GET' && (m = u.match(/^\/v1\/accounts\/(acct_\w+)$/))) return accts[m[1]] ? send(res, 200, accts[m[1]]) : send(res, 404, { error: { message: 'No such account' } });
    if (req.method === 'POST' && u === '/v1/account_links') return send(res, 200, { object: 'account_link', url: `http://127.0.0.1:${PORT}/mock/onboard/${f.account}?return=${encodeURIComponent(f.return_url)}` });
    if (req.method === 'POST' && (m = u.match(/^\/v1\/accounts\/(acct_\w+)\/login_links$/))) return send(res, 200, { url: `http://127.0.0.1:${PORT}/mock/express/${m[1]}` });
    if (req.method === 'POST' && u === '/v1/checkout/sessions') { if (!accts[f['payment_intent_data[transfer_data][destination]']]) return send(res, 400, { error: { message: 'No such destination' } });
      const s = { id: id('cs_test'), object: 'checkout.session', livemode: false, url: '', form: f, payment_status: 'unpaid', status: 'open' }; s.url = `http://127.0.0.1:${PORT}/mock/checkout/${s.id}`; sessions[s.id] = s; return send(res, 200, s); }
    // ---- test helpers
    if ((m = u.match(/^\/mock\/onboard\/(acct_\w+)$/))) { const a = accts[m[1]]; if (a) Object.assign(a, { details_submitted: true, charges_enabled: true, payouts_enabled: true }); res.writeHead(302, { location: new URL(req.url, 'http://x').searchParams.get('return') }); return res.end(); }
    if ((m = u.match(/^\/mock\/checkout\/(cs_test_\w+)$/))) { const s = sessions[m[1]]; res.writeHead(200, { 'content-type': 'text/html' }); return res.end(`<h1>Mock Checkout</h1>${s ? Object.keys(s.form).filter(k => /line_items\[\d\]\[price_data\]\[product_data\]\[name\]/.test(k)).map(k => `<p>${s.form[k]}: ${s.form[k.replace('[product_data][name]', '[unit_amount]')]}</p>`).join('') : ''}<a id="pay" href="/mock/pay/${m[1]}">Pay</a>`); }
    if ((m = u.match(/^\/mock\/pay\/(cs_test_\w+)$/))) { const s = sessions[m[1]]; if (!s) return send(res, 404, {}); Object.assign(s, { payment_status: 'paid', status: 'complete', payment_intent: id('pi') });
      const r = await fire({ id: id('evt'), type: 'checkout.session.completed', livemode: false, data: { object: { id: s.id, object: 'checkout.session', payment_status: 'paid', payment_intent: s.payment_intent } } });
      if (req.method === 'GET') { res.writeHead(302, { location: s.form.success_url }); return res.end(); } return send(res, 200, r); }
    if (u === '/mock/state') return send(res, 200, { accts, sessions });
    if (u === '/mock/enable') { const a = accts[f.account]; if (a) Object.assign(a, { details_submitted: true, charges_enabled: true, payouts_enabled: true }); return send(res, a ? 200 : 404, a || {}); }
    if (u === '/mock/fire') { const ev = JSON.parse(f.event); return send(res, 200, await fire(ev, f.header === 'bad' ? sign(JSON.stringify(ev), undefined, 'whsec_wrong') : f.header === 'old' ? sign(JSON.stringify(ev), Math.floor(Date.now() / 1000) - 3600) : undefined)); }
    send(res, 404, { error: { message: 'mock: no route ' + req.method + ' ' + u } });
  });
}).listen(PORT, '127.0.0.1', () => console.log('stripe mock on :' + PORT));
