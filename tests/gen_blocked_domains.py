"""Regenerate supabase/seed/blocked_domains.sql from StevenBlack/hosts 'porn-only' (MIT + CC BY 4.0 sources, see docs/MODERATION.md)."""
import re, urllib.request, datetime, os
SRC = "https://raw.githubusercontent.com/StevenBlack/hosts/master/alternates/porn-only/hosts"
hs = set()
for l in urllib.request.urlopen(SRC).read().decode().splitlines():
    m = re.match(r"0\.0\.0\.0\s+(\S+)", l)
    if not m: continue
    h = re.sub(r"^(www\d*\.)+", "", m.group(1).lower().rstrip("."))
    if h not in ("0.0.0.0", "localhost"): hs.add(h)
par = lambda h: [".".join(h.split(".")[i:]) for i in range(1, len(h.split(".")) - 1)]
ds = sorted(h for h in hs if not any(q in hs for q in par(h)) and re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", h) and len(h) <= 253)
out = [f"-- Generated {datetime.date.today()} from {SRC}", "-- Sources: Clefspeare13/pornhosts (MIT), Sinfonietta/hostfiles (MIT), tiuxo/hosts (CC BY 4.0), brijrajparmar27/host-sources (CC BY 4.0), bigdargon/hostsVN (MIT).",
       f"-- Lowercased, www. stripped, subdomains of listed parents dropped. {len(ds)} domains. Idempotent."]
for i in range(0, len(ds), 6000):
    out.append("insert into public.blocked_domains (domain, category, source) select d, 'adult', 'stevenblack-porn' from unnest(string_to_array('" + ",".join(ds[i:i+6000]) + "', ',')) d on conflict (domain) do nothing;")
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "supabase", "seed", "blocked_domains.sql"), "w").write("\n".join(out) + "\n"); print(len(ds), "domains")
