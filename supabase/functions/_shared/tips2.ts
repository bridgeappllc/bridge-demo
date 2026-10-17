// Shared helpers for the tips2-* edge functions (Pod Club tips, "earn first"). Preview uses the Stripe SANDBOX key
// (secret STRIPE_SECRET_KEY_SANDBOX); a live key is refused unless TIPS2_ALLOW_LIVE=1. Never logs secrets.
export const SB = Deno.env.get("SUPABASE_URL")!;
export const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
export const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
export const STRIPE_KEY = Deno.env.get("STRIPE_SECRET_KEY_SANDBOX") ?? "";
export const STRIPE_API = Deno.env.get("STRIPE_API_URL") ?? "https://api.stripe.com";
export const STRIPE_V2_VERSION = Deno.env.get("STRIPE_V2_VERSION") ?? "2026-09-30.endive";
export const KEY_OK = !!STRIPE_KEY && (STRIPE_KEY.startsWith("sk_test_") || Deno.env.get("TIPS2_ALLOW_LIVE") === "1");
export const APPS = (Deno.env.get("TIPS2_APPS") ?? "https://bridgeappllc.github.io/bridge-preview/").split(",");
export const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
export const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const MIN = 200, MAX = 10000;

// total = ceil((tip + 30) / 0.971): the tipper covers Stripe's 2.9% + 30¢; recipient gets 90% of the tip, Pod Club 10%.
export function split(tip: number) {
  const total = Math.ceil((tip + 30) / (1 - 0.029));
  const fee = total - tip, app_cut = Math.round(tip * 0.1), recipient = tip - app_cut;
  return { tip, fee, total, app_cut, recipient, application_fee: app_cut + fee };
}

export async function stripe(method: string, path: string, form?: Record<string, string>, idem?: string) {
  const h: Record<string, string> = { Authorization: `Bearer ${STRIPE_KEY}`, "Content-Type": "application/x-www-form-urlencoded" };
  if (idem) h["Idempotency-Key"] = idem;
  const r = await fetch(`${STRIPE_API}/v1/${path}`, { method, headers: h, body: form ? new URLSearchParams(form) : undefined });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(b?.error?.message ?? "Stripe error"), { status: 502, code: b?.error?.code });
  return b;
}
export async function stripe2(method: string, path: string, body?: unknown) {
  const r = await fetch(`${STRIPE_API}/v2/${path}`, { method, headers: { Authorization: `Bearer ${STRIPE_KEY}`, "Stripe-Version": STRIPE_V2_VERSION, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(b?.error?.message ?? "Stripe error"), { status: 502 });
  return b;
}
export async function rest(path: string, init: RequestInit = {}) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers ?? {}) } });
  const b = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error(b?.message ?? "Database error"), { status: r.status < 500 ? 400 : 500, friendly: r.status < 500 && r.status !== 401 && r.status !== 403 });
  return b;
}
export async function me(req: Request) {
  const u = await fetch(`${SB}/auth/v1/user`, { headers: { apikey: ANON, Authorization: req.headers.get("Authorization") ?? "" } });
  return u.ok ? await u.json() : null;
}

export const getAccount = (id: string) => stripe2("GET", `core/accounts/${id}?include=configuration.recipient&include=requirements`);
export function flags(a: any) {
  const c = a?.configuration?.recipient?.capabilities?.stripe_balance ?? {};
  const transfers = c?.stripe_transfers?.status === "active", payouts = c?.payouts?.status === "active";
  const due = (a?.requirements?.entries ?? []).some((e: any) => ["currently_due", "past_due"].includes(e?.minimum_deadline?.status));
  return { details_submitted: transfers || !due, charges_enabled: transfers, payouts_enabled: transfers && payouts, updated_at: new Date().toISOString() };
}
export const ready = (row: any) => !!row && row.payouts_enabled && row.charges_enabled;

// Transfer every earned platform tip owed to this user (idempotent: a row is claimed earned -> paying before the
// transfer, the transfer uses a per-tip Idempotency-Key + source_transaction = the tip's charge, then -> paid_out).
export async function payout(uid: string, acct: string) {
  const out = { paid: 0, cents: 0, failed: 0 };
  const due = await rest(`tips2?recipient=eq.${uid}&status=eq.earned&mode=eq.platform&select=id`);
  for (const { id } of due ?? []) {
    const t = (await rest(`tips2?id=eq.${id}&status=eq.earned`, { method: "PATCH", body: JSON.stringify({ status: "paying" }) }))?.[0];
    if (!t) continue;
    try {
      let charge = t.charge_id;
      if (!charge) { const pi = await stripe("GET", `payment_intents/${t.payment_intent_id}`); charge = typeof pi.latest_charge === "string" ? pi.latest_charge : pi.latest_charge?.id; }
      const tr = await stripe("POST", "transfers", { amount: String(t.recipient_cents), currency: "usd", destination: acct, source_transaction: charge, transfer_group: `tip_${t.id}`, description: `Pod Club tip from ${t.tipper_name}`.slice(0, 200), "metadata[pod_club_tip]": t.id }, `tips2-transfer-${t.id}`);
      await rest(`tips2?id=eq.${t.id}`, { method: "PATCH", body: JSON.stringify({ status: "paid_out", transfer_id: tr.id, charge_id: charge, stripe_account_id: acct, paid_out_at: new Date().toISOString() }) });
      out.paid++; out.cents += t.recipient_cents;
    } catch (e: any) {
      console.error("tips2 payout", t.id, e?.message);
      await rest(`tips2?id=eq.${t.id}&status=eq.paying`, { method: "PATCH", body: JSON.stringify({ status: "earned" }) });
      out.failed++;
    }
  }
  return out;
}

// Refund one tip (held/earned, platform). Idempotent per tip.
export async function refund(t: any) {
  const prev = t.status;
  const c = (await rest(`tips2?id=eq.${t.id}&status=eq.${prev}`, { method: "PATCH", body: JSON.stringify({ status: "refunding" }) }))?.[0];
  if (!c) return false;
  try {
    const r = await stripe("POST", "refunds", { payment_intent: c.payment_intent_id, reason: "requested_by_customer", "metadata[pod_club_tip]": c.id }, `tips2-refund-${c.id}`);
    await rest(`tips2?id=eq.${c.id}`, { method: "PATCH", body: JSON.stringify({ status: "refunded", refund_id: r.id, refunded_at: new Date().toISOString() }) });
    return true;
  } catch (e: any) {
    console.error("tips2 refund", c.id, e?.message);
    await rest(`tips2?id=eq.${c.id}&status=eq.refunding`, { method: "PATCH", body: JSON.stringify({ status: prev }) });
    return false;
  }
}
