// Bundle the web app (repo root) into mobile/www so the native app ships its own copy (Apple 4.2: not just a remote URL).
// supabase-js is vendored from node_modules instead of the CDN. Invite/profile links still point to the public web URL (see PUBLIC_URL in index.html).
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path"; import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url)), root = join(here, "..", ".."), www = join(here, "..", "www");
rmSync(www, { recursive: true, force: true }); mkdirSync(join(www, "vendor"), { recursive: true });
for (const f of ["index.html", "privacy.html", "terms.html", "support.html", "manifest.webmanifest"]) cpSync(join(root, f), join(www, f));
cpSync(join(root, "assets"), join(www, "assets"), { recursive: true });
cpSync(join(here, "..", "node_modules", "@supabase", "supabase-js", "dist", "umd", "supabase.js"), join(www, "vendor", "supabase.js"));
cpSync(join(here, "..", "node_modules", "@capacitor", "core", "dist", "capacitor.js"), join(www, "vendor", "capacitor.js"));  // window.Capacitor.registerPlugin (no bundler)
const idx = join(www, "index.html"); let html = readFileSync(idx, "utf8");
const cdn = /<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/@supabase\/supabase-js@[^"]+"[^>]*><\/script>/;
if (!cdn.test(html)) throw new Error("supabase-js CDN tag not found in index.html");
html = html.replace(cdn, '<script src="vendor/capacitor.js"></script><script src="vendor/supabase.js"></script>').replace('<link rel="manifest" href="manifest.webmanifest">', "");
writeFileSync(idx, html); console.log("www/ built from", root);
