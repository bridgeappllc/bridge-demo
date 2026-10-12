"""Terracotta -> Harbor Blue + Logo C -> Logo 3 'Suspension'. Idempotent-ish: run once on a Terracotta checkout."""
import re, os, glob
R = '/workspace/bridge-demo-repo/'
ROOT = (":root{--bg:#F3F6FA;--sf:#FFFFFF;--inp:#FFFFFF;--n:#16233B;--b:#2B4C7E;--ac:#785A26;--onp:#FFFFFF;--bl:#E4EBF5;"
        "--m:#56617A;--l:#DCE3EE;--fl:#7D879A;--g:#2F6B3F;--r:#A3261B;--clay:#2B4C7E;"
        "--serif:'DM Serif Display',Georgia,'Times New Roman',serif;color-scheme:light}")
MAP = {  # terracotta -> harbor blue
 '#F3EBDF':'#F3F6FA', '#FBF6EF':'#FFFFFF', '#FFFDF9':'#FFFFFF', '#2A2522':'#16233B', '#A0452B':'#2B4C7E', '#A4492E':'#2B4C7E',
 '#8A3A23':'#213B63',   # primary hover
 '#E2D8CB':'#DCE3EE', '#5E544D':'#4E586C', '#EFE7DC':'#E9EEF5', '#E8DECF':'#E4E9F0',
 '#E3E8DD':'#F1EADB',   # tag bg (brass text)
 '#EBDFD0':'#E6ECF4',   # chat bubble
 '#F0E0D3':'#E4EBF5', '#8C8076':'#7D879A', '#6B5F57':'#56617A', '#56664C':'#785A26',
 '#F6E5C8':'#F4EBD9', '#6B4210':'#5E4519',  # warm note (warning) -> brass family
}
RGBA = {'rgba(42,37,34,':'rgba(22,35,59,', 'rgba(160,69,43,':'rgba(43,76,126,', 'rgba(243,235,223,':'rgba(243,246,250,', 'rgba(107,66,16,':'rgba(120,90,38,'}
MARK = ('<g fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M40 43V60M50 48.5V60M60 43V60" stroke="#9DB8E0" stroke-width="2.6"/>'
        '<path d="M5 62Q19 50 31 25Q50 66 69 25Q81 50 95 62" stroke="#2B4C7E" stroke-width="3.6"/><path d="M31 22V80M69 22V80" stroke="#16233B" stroke-width="7"/>'
        '<path d="M4 64H96" stroke="#16233B" stroke-width="5.5"/></g>')
OLD_MARK = re.compile(r'<path d="M16 84C16 52 31 31 49 21"[^>]*/><path d="M84 84C84 52 69 31 51 21"[^>]*/>')
# small one-colour glyph for buttons (inherits text colour)
GLYPH = ('<svg class="gl" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">'
         '<path d="M2 14.5Q5 12 7.4 6.5Q12 16.5 16.6 6.5Q19 12 22 14.5" stroke-width="1.6"/><path d="M7.4 5.5V19M16.6 5.5V19" stroke-width="2.4"/><path d="M1.5 15.5h21" stroke-width="2"/></svg>')
NAV = '<path d="M2 15.5Q5 12.5 7 6.5Q12 16 17 6.5Q19 12.5 22 15.5"/><path d="M7 5v15M17 5v15M2 16.5h20"/>'

def recolor(s):
    for a, b in MAP.items(): s = re.sub(re.escape(a), b, s, flags=re.I)
    for a, b in RGBA.items(): s = s.replace(a, b)
    return s

# --- app ---
p = R + 'index.html'; s = open(p).read()
s, n = re.subn(r":root\{[^}]*\}", ROOT, s, count=1); assert n == 1
s = recolor(s)
s, n = re.subn(r"const LOGO='[^']*';", "const LOGO='<svg class=\"mk\" viewBox=\"0 0 100 100\" role=\"img\" aria-label=\"Bridge logo\">" + MARK + "</svg>';", s, count=1); assert n == 1
s = s.replace("const LOGO=", "const GLYPH='" + GLYPH + "';\nconst LOGO=", 1)
s, n = re.subn(r"bridges:'<path[^']*'", "bridges:'" + NAV + "'", s, count=1); assert n == 1
for a, b in [('>🌉 Meet Me on the Bridge<', '>${GLYPH}Meet Me on the Bridge<'), ('>🌉 Meet ${fn} on the Bridge<', '>${GLYPH}Meet ${fn} on the Bridge<'),
             ("You're on the bridge 🌉", "You're on the bridge")]:
    assert a in s, a; s = s.replace(a, b)
s = s.replace('🌉 Meet', '${GLYPH}Meet')  # remaining button labels (library 'with this' buttons)
s = s.replace('</style>', '.btn .gl{width:1.15em;height:1.15em;vertical-align:-.2em;margin-right:7px}\n</style>', 1)
open(p, 'w').write(s)
# --- legal pages ---
for f in ('privacy.html', 'terms.html', 'support.html'):
    p = R + f; s = recolor(open(p).read()); s, n = OLD_MARK.subn(MARK, s); assert n == 1, f
    s = s.replace('stroke-linecap="round" aria-hidden="true">' + MARK, 'aria-hidden="true">' + MARK); open(p, 'w').write(s)
# --- email templates (repo only) ---
for p in glob.glob(R + 'supabase/email-templates/*.html'): s = recolor(open(p).read()); open(p, 'w').write(s)
# --- manifest ---
p = R + 'manifest.webmanifest'; s = recolor(open(p).read()); open(p, 'w').write(s)
left = {}
for f in ['index.html', 'privacy.html', 'terms.html', 'support.html', 'manifest.webmanifest'] + [x[len(R):] for x in glob.glob(R + 'supabase/email-templates/*.html')]:
    s = open(R + f).read(); hx = [h for h in re.findall(r'#[0-9A-Fa-f]{6}', s) if h.upper() in MAP] + (['🌉'] if '🌉' in s else []) + (['oldmark'] if OLD_MARK.search(s) else [])
    if hx: left[f] = hx
print('leftover terracotta:', left or 'none')
# post-step: keep 'ex'/'wh' tags distinct from the brass topic tag
p = R + 'index.html'; s = open(p).read(); s = s.replace('.tag.ex,.tag.wh{background:#F4EBD9;color:#5E4519}', '.tag.ex,.tag.wh{background:#E4EBF5;color:#2B4C7E}'); open(p, 'w').write(s)
