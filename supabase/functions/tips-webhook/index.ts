// Pod Club tips: Stripe webhook. Verifies the Stripe-Signature (HMAC-SHA256, 5-minute tolerance) with the endpoint's
// signing secret (STRIPE_WEBHOOK_SECRET), then records the outcome. Deployed with verify_jwt = false (Stripe has no JWT).
//   checkout.session.completed / async_payment_succeeded -> tip paid + "X tipped you $5" notification (public.tip_mark_paid)
//   checkout.session.expired / async_payment_failed -> tip failed
//   account.updated (Connect endpoint, optional) -> refresh the recipient's payout flags
const SB = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const SECRETS = (Deno.env.get("STRIPE_WEBHOOK_SECRET") ?? "").split(",").filter(Boolean);
const enc = new TextEncoder();
const hex = (b: ArrayBuffer) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("");
function same(a: string, b: string) { if (a.length !== b.length) return false; let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i); return d === 0; }

export async function verify(raw: string, header: string, secrets: string[], now = Date.now() / 1000, tol = 300) {
  const parts = header.split(",").map((x) => x.split("=")); const t = Number(parts.find(([k]) => k === "t")?.[1]);
  const sigs = parts.filter(([k]) => k === "v1").map(([, v]) => v);
  if (!t || !sigs.length || Math.abs(now - t) > tol) return false;
  for (const s of secrets) {
    const key = await crypto.subtle.importKey("raw", enc.encode(s), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const mac = hex(await crypto.subtle.sign("HMAC", key, enc.encode(`${t}.${raw}`)));
    if (sigs.some((v) => same(v, mac))) return true;
  }
  return false;
}
async function svc(path: string, init: RequestInit) {
  const r = await fetch(`${SB}/rest/v1/${path}`, { ...init, headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json" } });
  if (!r.ok) throw new Error(`db ${r.status}`);
  return r.json().catch(() => null);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const raw = await req.text();
  if (!SECRETS.length || !(await verify(raw, req.headers.get("Stripe-Signature") ?? "", SECRETS))) return new Response("Bad signature", { status: 400 });
  let ev: any; try { ev = JSON.parse(raw); } catch { return new Response("Bad payload", { status: 400 }); }
  const o = ev?.data?.object ?? {};
  try {
    if ((ev.type === "checkout.session.completed" && o.payment_status === "paid") || ev.type === "checkout.session.async_payment_succeeded") {
      await svc("rpc/tip_mark_paid", { method: "POST", body: JSON.stringify({ p_session: o.id, p_payment_intent: typeof o.payment_intent === "string" ? o.payment_intent : o.payment_intent?.id ?? null, p_livemode: !!ev.livemode }) });
    } else if (ev.type === "checkout.session.expired" || ev.type === "checkout.session.async_payment_failed") {
      await svc(`tips?checkout_session_id=eq.${encodeURIComponent(o.id)}&status=eq.pending`, { method: "PATCH", body: JSON.stringify({ status: "failed" }) });
    } else if (ev.type === "account.updated" && /^acct_[A-Za-z0-9]+$/.test(o.id ?? "")) {
      await svc(`tip_accounts?stripe_account_id=eq.${o.id}`, { method: "PATCH", body: JSON.stringify({ details_submitted: !!o.details_submitted, charges_enabled: !!o.charges_enabled, payouts_enabled: !!o.payouts_enabled, updated_at: new Date().toISOString() }) });
    }
  } catch (e: any) { console.error("tips-webhook", ev?.type, e?.message); return new Response("Retry", { status: 500 }); }
  return new Response(JSON.stringify({ received: true }), { headers: { "Content-Type": "application/json" } });
});
