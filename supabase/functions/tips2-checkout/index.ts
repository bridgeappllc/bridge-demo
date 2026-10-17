// Pod Club tips2 (earn first): hosted Checkout for a tip. purpose "thanks" (tip a person / the clip's sharer) or
// "listen" (a tip for a pod member on a clip, held until they answer it). Same fee math as tips v1.
//   Recipient payouts-enabled + thanks -> destination charge (application_fee_amount + transfer_data.destination).
//   Otherwise -> plain platform charge; 90% of the tip is owed to the recipient and transferred later (tips2-connect/payout).
import { CORS, MAX, MIN, UUID, appMode, json, keyFor, me, rest, split, stripe } from "../_shared/tips2.ts";

const USD_ONLY = (Deno.env.get("TIPS_USD_ONLY_APPS") ?? "").split(",").filter(Boolean);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const u = await me(req); if (!u) return json({ error: "Not signed in" }, 401);
  let body: any; try { body = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const { recipient, kind, ref } = body ?? {}; const purpose = body?.purpose ?? "thanks"; const tip = Number(body?.amount_cents);
  if (!UUID.test(recipient ?? "") || !["thanks", "listen"].includes(purpose) || !(kind == null || (["bridge", "group_clip"].includes(kind) && UUID.test(ref ?? "")))) return json({ error: "Bad request" }, 400);
  if (!Number.isInteger(tip) || tip % 100 !== 0) return json({ error: "Pick a whole-dollar amount" }, 400);
  if (tip < MIN) return json({ error: "The minimum tip is $2" }, 400);
  if (tip > MAX) return json({ error: "The maximum tip is $100" }, 400);
  const { app, live } = appMode(body?.app);
  if (!keyFor(live)) return json({ error: "Tips aren't available yet" }, 503);
  try {
    const p = (await rest("rpc/tips2_prepare", { method: "POST", body: JSON.stringify({ p_tipper: u.id, p_recipient: recipient, p_purpose: purpose, p_kind: kind ?? null, p_ref: kind ? ref : null }) }))?.[0];
    if (!p) return json({ error: "Couldn't start the tip" }, 500);
    // destination charge only when the recipient's ready account is in this mode (live app -> live account)
    const acctLive = p.stripe_account_id ? (await rest(`tip_accounts2?stripe_account_id=eq.${p.stripe_account_id}&select=livemode`))?.[0]?.livemode : null;
    const s = split(tip), id = crypto.randomUUID(), dest = purpose === "thanks" && p.stripe_account_id && !!acctLive === live ? p.stripe_account_id : null;
    const md = { pod_club_tip2: id, tipper: u.id, recipient, purpose };
    const f: Record<string, string> = {
      mode: "payment", client_reference_id: id, submit_type: "pay",
      success_url: `${app}#tipped/${id}`, cancel_url: kind ? `${app}#${kind === "bridge" ? "bridge/" + ref : "tipcancel/" + recipient}` : `${app}#tipcancel/${recipient}`,
      "line_items[0][quantity]": "1", "line_items[0][price_data][currency]": "usd", "line_items[0][price_data][unit_amount]": String(s.tip),
      "line_items[0][price_data][product_data][name]": (purpose === "listen" ? `Tip for ${p.recipient_name} for listening` : `Tip for ${p.recipient_name}`).slice(0, 120),
      "line_items[0][price_data][product_data][description]": (purpose === "listen" ? `They get it after they answer “${p.title}”. Refunded if they don't within 30 days.` : p.title ? `For sharing “${p.title}” on Pod Club` : "A thank-you on Pod Club").slice(0, 300),
      "line_items[1][quantity]": "1", "line_items[1][price_data][currency]": "usd", "line_items[1][price_data][unit_amount]": String(s.fee),
      "line_items[1][price_data][product_data][name]": "Processing fee",
      "line_items[1][price_data][product_data][description]": "Covers card processing so the full tip reaches them",
      "payment_intent_data[description]": `Pod Club tip for ${p.recipient_name}`.slice(0, 200),
      "payment_intent_data[transfer_group]": `tip_${id}`,
    };
    // USD-only (no Adaptive Pricing currency conversion) for apps listed in TIPS_USD_ONLY_APPS
    if (USD_ONLY.includes(app)) f["adaptive_pricing[enabled]"] = "false";
    if (dest) { f["payment_intent_data[application_fee_amount]"] = String(s.application_fee); f["payment_intent_data[transfer_data][destination]"] = dest; }
    for (const [k, v] of Object.entries(md)) { f[`metadata[${k}]`] = v; f[`payment_intent_data[metadata][${k}]`] = v; }
    const cs = await stripe(live, "POST", "checkout/sessions", f, id);
    if (!!cs.livemode !== live) throw new Error("Stripe mode mismatch");
    await rest("tips2", { method: "POST", body: JSON.stringify({ id, purpose, mode: dest ? "destination" : "platform", tipper: u.id, recipient, tipper_name: p.tipper_name, title: (p.title ?? "").slice(0, 300), pod_kind: kind ?? null, pod_ref: kind ? ref : null, amount_cents: s.tip, fee_cents: s.fee, total_cents: s.total, app_cut_cents: s.app_cut, recipient_cents: s.recipient, application_fee_cents: dest ? s.application_fee : null, stripe_account_id: dest, checkout_session_id: cs.id, livemode: !!cs.livemode }) });
    return json({ ...s, url: cs.url, tip_id: id, mode: dest ? "destination" : "platform", purpose });
  } catch (e: any) {
    if (!e?.friendly) console.error("tips2-checkout", e?.message);
    return json({ error: e?.friendly ? e.message : "Couldn't start the tip" }, e?.friendly ? 400 : e?.status ?? 500);
  }
});
