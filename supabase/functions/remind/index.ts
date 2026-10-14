// Pod Club "Remind" — nudges someone who hasn't answered yet: always in-app, plus email via Resend when they can get it.
// The caller is identified from their JWT; all rules + the recipient's email lookup happen in the DB
// (public.remind_prepare / remind_finish, service role only). The email address is never returned to the client.
const SB = Deno.env.get("SUPABASE_URL")!;
const SERVICE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const RESEND_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const RESEND_URL = Deno.env.get("RESEND_API_URL") ?? "https://api.resend.com/emails";
const FROM = Deno.env.get("REMIND_FROM") ?? "Pod Club <hello@meetonthebridge.org>";
const APPS = (Deno.env.get("REMIND_APPS") ?? "https://bridgeappllc.github.io/bridge-demo/,https://bridgeappllc.github.io/bridge-preview/").split(",");
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const mask = (e: string) => e.replace(/^(.).*?(@.).*?(\.[^.]+)$/, "$1***$2***$3");

async function rpc(fn: string, args: unknown) {
  const r = await fetch(`${SB}/rest/v1/rpc/${fn}`, { method: "POST", headers: { apikey: SERVICE, Authorization: `Bearer ${SERVICE}`, "Content-Type": "application/json" }, body: JSON.stringify(args) });
  const b = await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error(b?.message ?? "Database error"), { status: r.status < 500 ? 400 : 500 });
  return b;
}

export function emailFor(name: string, title: string, link: string, settings: string) {
  const subject = `${name} wants you to listen to this`;
  const html = `<!doctype html><html><body style="margin:0;background:#F4F5EF;font-family:'DM Sans',Helvetica,Arial,sans-serif;color:#24302A">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F4F5EF;padding:28px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#FFFFFF;border:1px solid #DDE2D6;border-radius:16px;padding:28px">
<tr><td style="font-size:15px;font-weight:700;color:#4A6B57;padding-bottom:18px">Pod Club</td></tr>
<tr><td style="font-size:22px;font-weight:700;line-height:1.3;padding-bottom:10px">${esc(name)} wants you to listen to this</td></tr>
<tr><td style="font-size:16px;line-height:1.5;padding-bottom:6px">“${esc(title)}”</td></tr>
<tr><td style="font-size:15px;line-height:1.5;color:#5F6A62;padding-bottom:22px">Give it a listen, answer one quick question, then see what ${esc(name)} thought.</td></tr>
<tr><td><a href="${esc(link)}" style="display:inline-block;background:#4A6B57;color:#FFFFFF;text-decoration:none;font-weight:700;font-size:16px;padding:13px 22px;border-radius:12px">Open the pod</a></td></tr>
<tr><td style="font-size:12px;line-height:1.5;color:#5F6A62;padding-top:26px;border-top:1px solid #DDE2D6;margin-top:22px">
You got this because you're in a pod with ${esc(name)} on Pod Club. Don't want reminders? <a href="${esc(settings)}" style="color:#3A5645">Turn off “Email me reminders” in Settings</a>.</td></tr>
</table></td></tr></table></body></html>`;
  const text = `${name} wants you to listen to this:\n“${title}”\n\nGive it a listen, answer one quick question, then see what ${name} thought.\nOpen the pod: ${link}\n\nDon't want reminders? Turn off "Email me reminders" in Settings: ${settings}`;
  return { subject, html, text };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const auth = req.headers.get("Authorization") ?? "";
  const u = await fetch(`${SB}/auth/v1/user`, { headers: { apikey: ANON, Authorization: auth } });
  if (!u.ok) return json({ error: "Not signed in" }, 401);
  const me = await u.json();
  let body: any; try { body = await req.json(); } catch { return json({ error: "Bad request" }, 400); }
  const { kind, pod, target } = body ?? {}; const dry = body?.dry_run === true;
  if (!["bridge", "group"].includes(kind) || !UUID.test(pod ?? "") || !UUID.test(target ?? "")) return json({ error: "Bad request" }, 400);
  const app = APPS.find((a) => a === body?.app) ?? APPS[0];
  try {
    const rows = await rpc("remind_prepare", { p_sender: me.id, p_kind: kind, p_pod: pod, p_target: target, p_dry: dry });
    const r = rows?.[0]; if (!r) return json({ error: "Couldn't send the reminder" }, 500);
    const link = `${app}#${kind === "bridge" ? `bridge/${pod}/1` : `pod/${pod}`}`;
    // Not emailable (guest, unconfirmed, or reminders off): in-app notification only. The client never learns why.
    if (!r.email) {
      if (dry) return json({ ok: true, dry_run: true, emailed: false });
      await rpc("remind_finish", { p_id: r.reminder_id, p_ok: true });
      return json({ ok: true, emailed: false });
    }
    const mail = emailFor(r.sender_name, r.clip_title, link, `${app}#settings`);
    if (dry) return json({ ok: true, dry_run: true, emailed: true, to: mask(r.email), from: FROM, subject: mail.subject, link, html_bytes: mail.html.length });
    let sent = false, why = "";
    try {
      const s = await fetch(RESEND_URL, { method: "POST", headers: { Authorization: `Bearer ${RESEND_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from: FROM, to: [r.email], subject: mail.subject, html: mail.html, text: mail.text,
          headers: { "List-Unsubscribe": `<${app}#settings>` }, tags: [{ name: "type", value: "reminder" }] }) });
      sent = s.ok; if (!s.ok) why = (await s.text()).slice(0, 200);
    } catch (e) { why = String(e).slice(0, 200); }
    // The in-app notification goes out either way; a failed email just makes it in-app only.
    await rpc("remind_finish", { p_id: r.reminder_id, p_ok: true });
    if (!sent) console.error("resend failed", why);
    return json({ ok: true, emailed: sent });
  } catch (e: any) { return json({ error: e.message }, e.status ?? 500); }
});
