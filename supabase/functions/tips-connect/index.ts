// Pod Club tips: Stripe Connect onboarding for recipients ("Get paid for tips" in Settings), Accounts v2.
// Accounts are v2 (/v2/core/accounts) with an Express dashboard, platform-collected fees/losses, and the recipient
// configuration's stripe_balance.stripe_transfers capability (Stripe requires merchant.card_payments alongside it),
// so they can receive destination-charge transfers. Onboarding uses v2 account links (use_case account_onboarding).
// actions: "onboard" -> creates (once) an Express account and returns a hosted Account Link URL;
//          "status"  -> refreshes the account's flags from Stripe and returns none | pending | ready;
//          "dashboard" -> a one-time Express dashboard login link (payouts).
// The Stripe key stays server-side (secret STRIPE_SECRET_KEY). TEST MODE is enforced unless TIPS_ALLOW_LIVE=1.
const SB = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const STRIPE_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_API = Deno.env.get("STRIPE_API_URL") ?? "https://api.stripe.com";
const STRIPE_V2_VERSION = Deno.env.get("STRIPE_V2_VERSION") ?? "2026-09-30.endive";
const LIVE_OK = Deno.env.get("TIPS_ALLOW_LIVE") === "1";
const APPS = (Deno.env.get("TIPS_APPS") ?? "https://bridgeappllc.github.io/bridge-preview/").split(",");
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });

export async function stripe(method: string, path: string, form?: Record<string, string>) {
  const r = await fetch(`${STRIPE_API}/v1/${path}`, { method, headers: { Authorization: `Bearer ${STRIPE_KEY}`, "Content-Type": "application/x-www-form-urlencoded" }, body: form ? new URLSearchParams(form) : undefined });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(b?.error?.message ?? "Stripe error"), { status: 502 });
  return b;
}
export async function stripe2(method: string, path: string, body?: unknown) {
  const r = await fetch(`${STRIPE_API}/v2/${path}`, { method, headers: { Authorization: `Bearer ${STRIPE_KEY}`, "Stripe-Version": STRIPE_V2_VERSION, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(b?.error?.message ?? "Stripe error"), { status: 502 });
  return b;
}
const getAccount = (id: string) => stripe2("GET", `core/accounts/${id}?include=configuration.recipient&include=requirements`);
async function rest(path: string, init: RequestInit = {}) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers ?? {}) } });
  const b = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error(b?.message ?? "Database error"), { status: 500 });
  return b;
}
// v2: ready to receive tips when the recipient's stripe_transfers capability is active (payouts = its balance payouts).
export function flags(a: any) {
  const c = a?.configuration?.recipient?.capabilities?.stripe_balance ?? {};
  const transfers = c?.stripe_transfers?.status === "active", payouts = c?.payouts?.status === "active";
  const due = (a?.requirements?.entries ?? []).some((e: any) => ["currently_due", "past_due"].includes(e?.minimum_deadline?.status));
  return { details_submitted: transfers || !due, charges_enabled: transfers, payouts_enabled: transfers && payouts, updated_at: new Date().toISOString() };
}
const state = (row: any) => !row ? "none" : row.payouts_enabled && row.charges_enabled ? "ready" : "pending";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  if (!STRIPE_KEY || (!STRIPE_KEY.startsWith("sk_test_") && !LIVE_OK)) return json({ error: "Tips aren't available yet" }, 503);
  const u = await fetch(`${SB}/auth/v1/user`, { headers: { apikey: ANON, Authorization: req.headers.get("Authorization") ?? "" } });
  if (!u.ok) return json({ error: "Not signed in" }, 401);
  const me = await u.json();
  let body: any; try { body = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const app = APPS.find((a) => a === body?.app) ?? APPS[0];
  try {
    const rows = await rest(`tip_accounts?user_id=eq.${me.id}&select=*`);
    let row = rows?.[0] ?? null;
    if (body?.action === "status") {
      if (!row) return json({ status: "none" });
      const a = await getAccount(row.stripe_account_id);
      row = (await rest(`tip_accounts?user_id=eq.${me.id}`, { method: "PATCH", body: JSON.stringify(flags(a)) }))[0];
      return json({ status: state(row) });
    }
    if (body?.action === "dashboard") {
      if (!row) return json({ error: "Set up tips first" }, 400);
      const l = await stripe("POST", `accounts/${row.stripe_account_id}/login_links`);
      return json({ url: l.url });
    }
    if (body?.action !== "onboard") return json({ error: "Bad request" }, 400);
    if (me.is_anonymous || !me.email) return json({ error: "Save your account with your email first" }, 400);
    if (!row) {
      const a = await stripe2("POST", "core/accounts", {
        contact_email: me.email, display_name: (body?.name ?? "").toString().slice(0, 100) || undefined, dashboard: "express",
        identity: { country: "us", entity_type: "individual" },
        defaults: { responsibilities: { fees_collector: "application", losses_collector: "application" } },
        configuration: { merchant: { capabilities: { card_payments: { requested: true } } }, recipient: { capabilities: { stripe_balance: { stripe_transfers: { requested: true } } } } },
        metadata: { pod_club_user: me.id }, include: ["configuration.recipient", "requirements"],
      });
      row = (await rest("tip_accounts", { method: "POST", body: JSON.stringify({ user_id: me.id, stripe_account_id: a.id, ...flags(a) }) }))[0];
    }
    const link = await stripe2("POST", "core/account_links", { account: row.stripe_account_id, use_case: { type: "account_onboarding", account_onboarding: { refresh_url: `${app}#tipsetup/refresh`, return_url: `${app}#tipsetup/return` } } });
    return json({ url: link.url, status: state(row) });
  } catch (e: any) {
    console.error("tips-connect", e?.message);
    return json({ error: e?.message?.includes("signed up for Connect") ? "Tips aren't available yet" : "Couldn't reach Stripe. Try again." }, e?.status ?? 500);
  }
});
