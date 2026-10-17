// Pod Club tips2: daily sweep (pg_cron -> pg_net POST with header x-tips2-cron = secret TIPS2_CRON_SECRET). verify_jwt = false.
//   1) transfers earned tips to every payouts-enabled recipient (same idempotent logic as tips2-connect "status");
//   2) refunds held listening tips not earned within 30 days (or whose pod/clip/membership is gone) and earned tips
//      unclaimed for 90 days (public.tips2_refundable).
import { KEY_OK, getAccount, flags, payout, ready, refund, rest } from "../_shared/tips2.ts";
const CRON = Deno.env.get("TIPS2_CRON_SECRET") ?? "";
function same(a: string, b: string) { if (!a || a.length !== b.length) return false; let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i); return d === 0; }
Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  if (!same(CRON, req.headers.get("x-tips2-cron") ?? "")) return new Response("Forbidden", { status: 403 });
  if (!KEY_OK) return new Response("Tips not configured", { status: 503 });
  const out = { payouts: 0, paid_cents: 0, refunds: 0, errors: 0 };
  try {
    // stuck claims (crash between claim and transfer) go back to earned; the transfer's idempotency key prevents doubles
    await rest(`tips2?status=eq.paying&paid_at=lt.${new Date(Date.now() - 6 * 3600e3).toISOString()}`, { method: "PATCH", body: JSON.stringify({ status: "earned" }) });
    const owed = await rest("tips2?status=eq.earned&mode=eq.platform&select=recipient");
    for (const uid of [...new Set((owed ?? []).map((r: any) => r.recipient).filter(Boolean))] as string[]) {
      let row = (await rest(`tip_accounts2?user_id=eq.${uid}&select=*`))?.[0];
      if (!row) continue;
      try { row = (await rest(`tip_accounts2?user_id=eq.${uid}`, { method: "PATCH", body: JSON.stringify(flags(await getAccount(row.stripe_account_id))) }))[0]; } catch { out.errors++; continue; }
      if (!ready(row)) continue;
      const p = await payout(uid, row.stripe_account_id); out.payouts += p.paid; out.paid_cents += p.cents; out.errors += p.failed;
    }
    for (const t of (await rest("rpc/tips2_refundable", { method: "POST", body: "{}" })) ?? []) (await refund(t)) ? out.refunds++ : out.errors++;
  } catch (e: any) { console.error("tips2-payout", e?.message); return new Response(JSON.stringify({ ...out, error: true }), { status: 500 }); }
  return new Response(JSON.stringify(out), { headers: { "Content-Type": "application/json" } });
});
