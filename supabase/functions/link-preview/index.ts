// Pod Club "link-preview": returns {thumb_url, title, site} for a link so the Library can show a rich preview card.
// Signed-in callers only. Respects the link filter (public.link_ok) for the page AND the image, blocks private/
// loopback hosts (SSRF), follows at most 3 redirects (each re-checked), 5 s timeout, reads at most 512 KB of HTML.
const SB = Deno.env.get("SUPABASE_URL")!;
const ANON = Deno.env.get("SUPABASE_ANON_KEY")!;
const ALLOW_LOCAL = Deno.env.get("LINK_PREVIEW_ALLOW_LOCAL") === "1"; // local test stack only
const MAX_BYTES = 512 * 1024, TIMEOUT_MS = 5000, MAX_HOPS = 3;
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const json = (b: unknown, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { ...CORS, "Content-Type": "application/json" } });

export function ytId(u: string): string | null {
  try {
    const x = new URL(u), h = x.hostname.replace(/^(www\.|m\.|music\.)/, "");
    let id: string | null = null;
    if (h === "youtu.be") id = x.pathname.split("/")[1];
    else if (h === "youtube.com" || h === "youtube-nocookie.com") {
      id = x.searchParams.get("v");
      const m = x.pathname.match(/^\/(shorts|embed|live|v)\/([^/?#]+)/); if (!id && m) id = m[2];
    }
    return id && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
  } catch { return null; }
}
export function privateHost(h: string): boolean {
  h = h.toLowerCase().replace(/^\[|\]$/g, "");
  if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal") || !h.includes(".") && !h.includes(":")) return true;
  const m = h.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (m) { const [a, b] = [+m[1], +m[2]]; return a === 10 || a === 127 || a === 0 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b < 32) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b < 128); }
  if (h.includes(":")) return true; // no raw IPv6 literals
  return /^\d+$/.test(h); // decimal-encoded IPs
}
const dec = (s: string) => s.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#0?39;|&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n)).trim();
export function parseMeta(html: string) {
  const meta: Record<string, string> = {};
  for (const tag of html.match(/<meta\b[^>]*>/gi) ?? []) {
    const k = tag.match(/\b(?:property|name|itemprop)\s*=\s*["']([^"']+)["']/i)?.[1]?.toLowerCase();
    const v = tag.match(/\bcontent\s*=\s*"([^"]*)"/i)?.[1] ?? tag.match(/\bcontent\s*=\s*'([^']*)'/i)?.[1];
    if (k && v != null && !(k in meta)) meta[k] = dec(v);
  }
  const t = html.match(/<title[^>]*>([^<]{1,400})<\/title>/i)?.[1];
  return { image: meta["og:image:secure_url"] || meta["og:image"] || meta["og:image:url"] || meta["twitter:image"] || meta["twitter:image:src"] || meta["image"] || "",
    title: meta["og:title"] || meta["twitter:title"] || (t ? dec(t) : ""), site: meta["og:site_name"] || meta["application-name"] || "" };
}
async function linkOk(u: string): Promise<boolean> {
  const r = await fetch(`${SB}/rest/v1/rpc/link_ok`, { method: "POST", headers: { apikey: ANON, Authorization: `Bearer ${ANON}`, "Content-Type": "application/json" }, body: JSON.stringify({ p_url: u }) });
  return r.ok && (await r.json()) === true;
}
let why = "";
async function fetchHtml(start: string, signal: AbortSignal): Promise<{ url: string; html: string } | null> {
  let u = start;
  for (let hop = 0; hop <= MAX_HOPS; hop++) {
    const x = new URL(u);
    if (!/^https?:$/.test(x.protocol) || (!ALLOW_LOCAL && privateHost(x.hostname)) || x.username || x.password) { why = "host"; return null; }
    if (hop > 0 && !(await linkOk(u))) { why = "redirect blocked"; return null; }
    const r = await fetch(u, { redirect: "manual", signal, headers: { "User-Agent": "Mozilla/5.0 (compatible; PodClubPreview/1.0; +https://bridgeappllc.github.io/bridge-demo/)", Accept: "text/html,application/xhtml+xml" } });
    if (r.status >= 300 && r.status < 400) { const loc = r.headers.get("location"); await r.body?.cancel(); if (!loc) return null; u = new URL(loc, u).href; continue; }
    if (!r.ok || !/html/i.test(r.headers.get("content-type") ?? "")) { why = `status ${r.status} ${r.headers.get("content-type") ?? ""}`.slice(0, 80); await r.body?.cancel(); return null; }
    const rd = r.body!.getReader(); const parts: Uint8Array[] = []; let n = 0;
    while (n < MAX_BYTES) { const { done, value } = await rd.read(); if (done) break; parts.push(value); n += value.length; }
    await rd.cancel().catch(() => {});
    const buf = new Uint8Array(Math.min(n, MAX_BYTES)); let o = 0;
    for (const p of parts) { const s = p.subarray(0, Math.max(0, buf.length - o)); buf.set(s, o); o += s.length; }
    return { url: u, html: new TextDecoder().decode(buf) };
  }
  return null;
}
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const u = await fetch(`${SB}/auth/v1/user`, { headers: { apikey: ANON, Authorization: req.headers.get("Authorization") ?? "" } });
  if (!u.ok) return json({ error: "Not signed in" }, 401);
  let url = ""; try { url = String((await req.json())?.url ?? "").slice(0, 2000); } catch { return json({ error: "Bad request" }, 400); }
  if (!/^https?:\/\//i.test(url)) return json({ error: "Bad request" }, 400);
  if (!(await linkOk(url))) return json({ error: "That link can't be shared on Pod Club." }, 422);
  const yt = ytId(url);
  if (yt) return json({ thumb_url: `https://img.youtube.com/vi/${yt}/hqdefault.jpg`, title: null, site: "YouTube" });
  const ac = new AbortController(); const t = setTimeout(() => ac.abort(), TIMEOUT_MS);
  try {
    why = ""; const page = await fetchHtml(url, ac.signal);
    if (!page) return json({ thumb_url: null, title: null, site: null, why: why || "redirects" });
    const m = parseMeta(page.html);
    let img: string | null = null;
    if (m.image) { try { const i = new URL(m.image, page.url); if (i.protocol === "http:") i.protocol = "https:"; if (i.href.length <= 1000 && !privateHost(i.hostname) && (await linkOk(i.href))) img = i.href; } catch { /* ignore */ } }
    return json({ thumb_url: img, title: m.title ? m.title.slice(0, 300) : null, site: (m.site || host(page.url)).slice(0, 80) || null });
  } catch (e) { return json({ thumb_url: null, title: null, site: null, why: ac.signal.aborted ? "timeout" : String(e).slice(0, 80) }); }
  finally { clearTimeout(t); }
});
