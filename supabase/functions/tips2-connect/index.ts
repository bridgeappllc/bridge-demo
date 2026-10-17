// Pod Club tips2 (earn first): Stripe Connect onboarding + collecting earned tips. Accounts v2, Express dashboard.
// actions: "status"    -> refreshes the caller's account from Stripe; if payouts-enabled, transfers their earned tips.
//                         Returns { status: none|pending|ready, earned_cents, held_cents, paid_out_cents, paid }.
//          "onboard"   -> only once you've earned a tip: creates (once) the account, returns a fresh onboarding link.
//          "dashboard" -> Express dashboard login link.
import { CORS, appMode, flags, getAccount, json, keyFor, me, payout, ready, rest, stripe, stripe2 } from "../_shared/tips2.ts";

async function totals(uid: string, live: boolean) {
  const rows = await rest(`tips2?recipient=eq.${uid}&livemode=eq.${live}&status=in.(held,earned,paying,paid_out)&select=status,amount_cents,recipient_cents`);
  const s = (f: (r: any) => boolean) => (rows ?? []).filter(f).reduce((a: number, r: any) => a + r.recipient_cents, 0);
  return { earned_cents: s((r) => r.status === "earned" || r.status === "paying"), held_cents: s((r) => r.status === "held"), paid_out_cents: s((r) => r.status === "paid_out"), tips: (rows ?? []).length };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const u = await me(req); if (!u) return json({ error: "Not signed in" }, 401);
  let body: any; try { body = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const { app, live } = appMode(body?.app);
  if (!keyFor(live)) return json({ error: "Tips aren't available yet" }, 503);
  try {
    let row = (await rest(`tip_accounts2?user_id=eq.${u.id}&select=*`))?.[0] ?? null;
    // one account per person: a sandbox (preview) account never stands in for a live one and vice versa
    if (row && !!row.livemode !== live) {
      if (live && body?.action === "onboard") { await rest(`tip_accounts2?user_id=eq.${u.id}&livemode=eq.false`, { method: "DELETE" }); row = null; }
      else row = null;
    }
    if (body?.action === "status") {
      let paid = null;
      if (row) {
        row = (await rest(`tip_accounts2?user_id=eq.${u.id}`, { method: "PATCH", body: JSON.stringify(flags(await getAccount(live, row.stripe_account_id))) }))[0];
        if (ready(row)) paid = await payout(u.id, row.stripe_account_id, live);
      }
      return json({ status: !row ? "none" : ready(row) ? "ready" : "pending", ...(await totals(u.id, live)), paid, live });
    }
    if (body?.action === "dashboard") {
      if (!row) return json({ error: "Set up payouts first" }, 400);
      return json({ url: (await stripe(live, "POST", `accounts/${row.stripe_account_id}/login_links`)).url });
    }
    if (body?.action !== "onboard") return json({ error: "Bad request" }, 400);
    if (u.is_anonymous || !u.email) return json({ error: "Save your account with your email first" }, 400);
    if (!row) {
      if (row === null && (await rest(`tip_accounts2?user_id=eq.${u.id}&select=livemode`))?.[0]?.livemode && !live) return json({ error: "Set up payouts in the Pod Club app" }, 400);
      const t = await totals(u.id, live);
      if (!t.earned_cents && !t.held_cents) return json({ error: "You can set up payouts once you've earned a tip" }, 400);
      // Real users: Express dashboard + Stripe-hosted onboarding (Account Links). Nothing is filled in by the platform.
      const a = await stripe2(live, "POST", "core/accounts", {
        contact_email: u.email, display_name: (body?.name ?? "").toString().slice(0, 100) || undefined, dashboard: "express",
        identity: { country: "us", entity_type: "individual" },
        defaults: { responsibilities: { fees_collector: "application", losses_collector: "application" } },
        configuration: { merchant: { capabilities: { card_payments: { requested: true } } }, recipient: { capabilities: { stripe_balance: { stripe_transfers: { requested: true } } } } },
        metadata: { pod_club_user: u.id }, include: ["configuration.recipient", "requirements"],
      });
      row = (await rest("tip_accounts2", { method: "POST", body: JSON.stringify({ user_id: u.id, stripe_account_id: a.id, livemode: live, ...flags(a) }) }))[0];
    }
    const link = await stripe2(live, "POST", "core/account_links", { account: row.stripe_account_id, use_case: { type: "account_onboarding", account_onboarding: { refresh_url: `${app}#tipsetup/refresh`, return_url: `${app}#tipsetup/return` } } });
    return json({ url: link.url, status: ready(row) ? "ready" : "pending" });
  } catch (e: any) {
    console.error("tips2-connect", e?.message);
    return json({ error: e?.friendly ? e.message : "Couldn't reach Stripe. Try again." }, e?.status ?? 500);
  }
});
