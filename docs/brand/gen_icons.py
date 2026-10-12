"""Logo 3 'Suspension' icons for web (assets/) and Capacitor (mobile/resources/) rendered via Chromium."""
from playwright.sync_api import sync_playwright
from PIL import Image
R = '/workspace/bridge-demo-repo/'
BLUE, NAVY, SKY, BRASS_L, BG = '#2B4C7E', '#16233B', '#9DB8E0', '#CDAF78', '#F3F6FA'
def mark(tower, cable, hang):
    return (f'<g fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M40 43V60M50 48.5V60M60 43V60" stroke="{hang}" stroke-width="2.6"/>'
            f'<path d="M5 62Q19 50 31 25Q50 66 69 25Q81 50 95 62" stroke="{cable}" stroke-width="3.6"/><path d="M31 22V80M69 22V80" stroke="{tower}" stroke-width="7"/>'
            f'<path d="M4 64H96" stroke="{tower}" stroke-width="5.5"/></g>')
ON_BLUE = mark('#FFFFFF', SKY, BRASS_L); ON_LIGHT = mark(NAVY, BLUE, SKY); ON_DARK = mark('#F5F3EC', SKY, BRASS_L)
def svg(bg, m, frac, rx=0, size=1024):
    """frac = width of the 92-unit-wide mark as a fraction of the canvas; mark centred on (50,51)."""
    s = size * frac / 92; tx = size / 2 - 50 * s; ty = size / 2 - 51 * s
    rect = f'<rect width="{size}" height="{size}" rx="{rx}" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">{rect}<g transform="translate({tx:.1f} {ty:.1f}) scale({s:.4f})">{m}</g></svg>'
ICON_ROUND = svg(BLUE, ON_BLUE, .70, rx=230)          # favicons / PWA "any"
ICON_SQ = svg(BLUE, ON_BLUE, .70)                     # apple-touch, store icon (OS applies its own mask)
MASKABLE = svg(BLUE, ON_BLUE, .56)                    # inside the 80% safe zone
FG = svg(None, ON_BLUE, .50)                          # Android adaptive foreground: 66% safe zone
SPLASH = svg(BLUE, ON_BLUE, .22, size=2732); SPLASH_D = svg(NAVY, ON_DARK, .22, size=2732)
open(R + 'assets/icon.svg', 'w').write(ICON_ROUND)
jobs = [(ICON_ROUND, 32, 'assets/favicon-32.png', True), (ICON_ROUND, 192, 'assets/icon-192.png', True), (ICON_ROUND, 512, 'assets/icon-512.png', True),
        (MASKABLE, 512, 'assets/icon-maskable-512.png', False), (ICON_SQ, 180, 'assets/apple-touch-icon.png', False),
        (ICON_SQ, 1024, 'mobile/resources/icon-only.png', False), (FG, 1024, 'mobile/resources/icon-foreground.png', True),
        (SPLASH, 2732, 'mobile/resources/splash.png', False), (SPLASH_D, 2732, 'mobile/resources/splash-dark.png', False)]
with sync_playwright() as p:
    br = p.chromium.launch()
    for src, px, out, alpha in jobs:
        pg = br.new_page(viewport={'width': px, 'height': px})
        pg.set_content(f'<html><body style="margin:0;background:transparent">{src.replace("<svg ", f"<svg style=\"display:block;width:{px}px;height:{px}px\" ", 1)}</body></html>')
        pg.screenshot(path=R + out, omit_background=alpha, clip={'x': 0, 'y': 0, 'width': px, 'height': px}); pg.close()
        if not alpha: Image.open(R + out).convert('RGB').save(R + out)   # no alpha channel (App Store requirement)
    br.close()
Image.new('RGB', (1024, 1024), BLUE).save(R + 'mobile/resources/icon-background.png')
for _, px, out, _a in jobs + [(0, 1024, 'mobile/resources/icon-background.png', 0)]:
    im = Image.open(R + out); print(out, im.size, im.mode)
