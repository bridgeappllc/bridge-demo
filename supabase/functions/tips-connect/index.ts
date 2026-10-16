// Pod Club tips: Stripe Connect Express onboarding for recipients ("Get paid for tips" in Settings).
// actions: "onboard" -> creates (once) an Express account and returns a hosted Account Link URL;
//          "status"  -> refreshes the account's flags from Stripe and returns none | pending | ready;
//          "dashboard" -> a one-time Express dashboard login link (payouts).
// The Stripe key stays server-side (secret STRIPE_SECRET_KEY). TEST MODE is enforced unless TIPS_ALLOW_LIVE=1.
const SB = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const STRIPE_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_API = Deno.env.get("STRIPE_API_URL") ?? "https://api.stripe.com";
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
async function rest(path: string, init: RequestInit = {}) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json", Prefer: "return=representation", ...(init.headers ?? {}) } });
  const b = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error(b?.message ?? "Database error"), { status: 500 });
  return b;
}
const flags = (a: any) => ({ details_submitted: !!a.details_submitted, charges_enabled: !!a.charges_enabled, payouts_enabled: !!a.payouts_enabled, updated_at: new Date().toISOString() });
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
      const a = await stripe("GET", `accounts/${row.stripe_account_id}`);
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
      const a = await stripe("POST", "accounts", { type: "express", country: "US", email: me.email, "capabilities[card_payments][requested]": "true", "capabilities[transfers][requested]": "true", "business_type": "individual", "business_profile[product_description]": "Tips from listeners on Pod Club", "metadata[pod_club_user]": me.id });
      row = (await rest("tip_accounts", { method: "POST", body: JSON.stringify({ user_id: me.id, stripe_account_id: a.id, ...flags(a) }) }))[0];
    }
    const link = await stripe("POST", "account_links", { account: row.stripe_account_id, type: "account_onboarding", refresh_url: `${app}#tipsetup/refresh`, return_url: `${app}#tipsetup/return` });
    return json({ url: link.url, status: state(row) });
  } catch (e: any) {
    console.error("tips-connect", e?.message);
    return json({ error: e?.message?.includes("signed up for Connect") ? "Tips aren't available yet" : "Couldn't reach Stripe. Try again." }, e?.status ?? 500);
  }
});
