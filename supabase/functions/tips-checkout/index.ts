// Pod Club tips: creates a hosted Stripe Checkout Session for a tip (destination charge).
// The tipper pays the tip + a "Processing fee" line so the recipient gets the full 90% and Pod Club the full 10%:
//   total = ceil((tip + 30) / (1 - 0.029)); application_fee_amount = 10% of tip + (total - tip); recipient gets 90% of tip.
// Rules (self, blocks, recipient set up, pod membership) are checked in the DB by public.tip_prepare (service role only).
const SB = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const STRIPE_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_API = Deno.env.get("STRIPE_API_URL") ?? "https://api.stripe.com";
const LIVE_OK = Deno.env.get("TIPS_ALLOW_LIVE") === "1";
const APPS = (Deno.env.get("TIPS_APPS") ?? "https://bridgeappllc.github.io/bridge-preview/").split(",");
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const MIN = 200, MAX = 10000;

export function split(tip: number) {
  const total = Math.ceil((tip + 30) / (1 - 0.029));
  const fee = total - tip, app_cut = Math.round(tip * 0.1), recipient = tip - app_cut;
  return { tip, fee, total, app_cut, recipient, application_fee: app_cut + fee };
}

async function svc(path: string, init: RequestInit = {}) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", ...(init.headers ?? {}) } });
  const b = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error(b?.message ?? "Database error"), { status: r.status < 500 ? 400 : 500, friendly: r.status < 500 });
  return b;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  if (!STRIPE_KEY || (!STRIPE_KEY.startsWith("sk_test_") && !LIVE_OK)) return json({ error: "Tips aren't available yet" }, 503);
  const u = await fetch(`${SB}/auth/v1/user`, { headers: { apikey: ANON, Authorization: req.headers.get("Authorization") ?? "" } });
  if (!u.ok) return json({ error: "Not signed in" }, 401);
  const me = await u.json();
  let body: any; try { body = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const { recipient, kind, ref } = body ?? {}; const tip = Number(body?.amount_cents);
  if (!UUID.test(recipient ?? "") || !(kind == null || (["bridge", "group_clip"].includes(kind) && UUID.test(ref ?? "")))) return json({ error: "Bad request" }, 400);
  if (!Number.isInteger(tip) || tip % 100 !== 0) return json({ error: "Pick a whole-dollar amount" }, 400);
  if (tip < MIN) return json({ error: "The minimum tip is $2" }, 400);
  if (tip > MAX) return json({ error: "The maximum tip is $100" }, 400);
  const app = APPS.find((a) => a === body?.app) ?? APPS[0];
  try {
    const p = (await svc("rpc/tip_prepare", { method: "POST", body: JSON.stringify({ p_tipper: me.id, p_recipient: recipient, p_kind: kind ?? null, p_ref: kind ? ref : null }) }))?.[0];
    if (!p) return json({ error: "Couldn't start the tip" }, 500);
    const s = split(tip), id = crypto.randomUUID();
    const md = { pod_club_tip: id, tipper: me.id, recipient };
    const f: Record<string, string> = {
      mode: "payment", client_reference_id: id, "submit_type": "pay",
      success_url: `${app}#tipped/${id}`, cancel_url: `${app}#tipcancel/${recipient}`,
      "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": "usd", "line_items[0][price_data][unit_amount]": String(s.tip),
      "line_items[0][price_data][product_data][name]": `Tip for ${p.recipient_name}`.slice(0, 120),
      "line_items[0][price_data][product_data][description]": (p.title ? `For sharing “${p.title}” on Pod Club` : "A thank-you on Pod Club").slice(0, 300),
      "line_items[1][quantity]": "1", "line_items[1][price_data][currency]": "usd", "line_items[1][price_data][unit_amount]": String(s.fee),
      "line_items[1][price_data][product_data][name]": "Processing fee",
      "line_items[1][price_data][product_data][description]": "Covers card processing so the full tip reaches them",
      "payment_intent_data[application_fee_amount]": String(s.application_fee),
      "payment_intent_data[transfer_data][destination]": p.stripe_account_id,
      "payment_intent_data[description]": `Pod Club tip for ${p.recipient_name}`.slice(0, 200),
    };
    for (const [k, v] of Object.entries(md)) { f[`metadata[${k}]`] = v; f[`payment_intent_data[metadata][${k}]`] = v; }
    const r = await fetch(`${STRIPE_API}/v1/checkout/sessions`, { method: "POST", headers: { Authorization: `Bearer ${STRIPE_KEY}`, "Content-Type": "application/x-www-form-urlencoded", "Idempotency-Key": id }, body: new URLSearchParams(f) });
    const cs = await r.json().catch(() => ({}));
    if (!r.ok) { console.error("tips-checkout stripe", cs?.error?.message); return json({ error: "Couldn't reach Stripe. Try again." }, 502); }
    await svc("tips", { method: "POST", body: JSON.stringify({ id, tipper: me.id, recipient, tipper_name: p.tipper_name, pod_kind: kind ?? null, pod_ref: kind ? ref : null, amount_cents: s.tip, fee_cents: s.fee, total_cents: s.total, app_cut_cents: s.app_cut, application_fee_cents: s.application_fee, recipient_cents: s.recipient, stripe_account_id: p.stripe_account_id, checkout_session_id: cs.id, livemode: !!cs.livemode }) });
    return json({ ...s, url: cs.url, tip_id: id });
  } catch (e: any) {
    return json({ error: e?.friendly ? e.message : "Couldn't start the tip" }, e?.status ?? 500);
  }
});
