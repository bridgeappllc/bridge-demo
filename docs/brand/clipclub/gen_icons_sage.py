"""Clip Club 'two bubbles' logo: brand files (v-blue/) + repo icons. Rendered via headless Chromium."""
import sys
from playwright.sync_api import sync_playwright
from PIL import Image
BLUE,SKY,NAVY,CHAR,MIST='#4A6B57','#A9C2B0','#24302A','#24302A','#F4F5EF'
def mark(back,front,play,gap):
    return (f'<g stroke-linejoin="round">'
      f'<rect x="6" y="12" width="54" height="40" rx="13" fill="{back}"/><path d="M15 48 L9 64 L31 50 Z" fill="{back}" stroke="{back}" stroke-width="3"/>'
      f'<g stroke="{gap}" stroke-width="5" paint-order="stroke"><path d="M78 72 L90 88 L88 72 Z" fill="{front}"/><rect x="32" y="31" width="62" height="45" rx="14" fill="{front}"/></g>'
      f'<path d="M77 72 L89 87 L87 70 Z" fill="{front}" stroke="{front}" stroke-width="3"/>'
      f'<path d="M57 44 L74 53.5 L57 63 Z" fill="{play}" stroke="{play}" stroke-width="4"/></g>')
ON_LIGHT=mark(SKY,BLUE,'#FFFFFF','#FFFFFF'); ON_MIST=mark(SKY,BLUE,'#FFFFFF',MIST)
ON_BLUE=mark(SKY,'#FFFFFF',BLUE,BLUE)
def icon(frac,rx=0,size=1024,bg=BLUE,m=ON_BLUE):
    s=size*frac/88; tx=size/2-50*s; ty=size/2-50*s
    r=f'<rect width="{size}" height="{size}" rx="{rx}" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">{r}<g transform="translate({tx:.1f} {ty:.1f}) scale({s:.4f})">{m}</g></svg>'
MARK=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="4 8 92 84">{ON_LIGHT}</svg>'
WORD=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400"><g transform="translate(220 10) scale(2)">{ON_LIGHT}</g>'
 f'<text x="320" y="292" text-anchor="middle" font-family="DM Sans" font-weight="600" font-size="84" fill="{NAVY}" letter-spacing="-1">Clip Club</text>'
 f'<text x="320" y="345" text-anchor="middle" font-family="DM Sans" font-size="30" fill="#5F6A62">A book club for clips</text></svg>')
WORD_H=(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 180"><g transform="translate(10 4) scale(1.7)">{ON_LIGHT}</g>'
 f'<text x="190" y="118" font-family="DM Sans" font-weight="600" font-size="88" fill="{NAVY}" letter-spacing="-1">Clip Club</text></svg>')
ICON=icon(.74,rx=230); ICON_SQ=icon(.74); MASK=icon(.58); FG=icon(.50,bg=None)
B='/workspace/clipclub-brand/sage/'; R='/workspace/bridge-demo-repo/'
files={'logo-mark.svg':MARK,'logo-wordmark-stacked.svg':WORD,'logo-wordmark.svg':WORD_H,'app-icon.svg':ICON,'app-icon-square.svg':ICON_SQ}
for n,s in files.items(): open(B+n,'w').write(s)
jobs=[(MARK,600,525,B+'logo-mark.png',True),(WORD,1280,800,B+'logo-wordmark-stacked.png',True),(WORD_H,1520,360,B+'logo-wordmark.png',True),
 (ICON,1024,1024,B+'app-icon-1024.png',True),(ICON,48,48,B+'app-icon-48.png',True)]
if 'repo' in sys.argv:
    open(R+'assets/icon.svg','w').write(ICON)
    jobs+=[(ICON,32,32,R+'assets/favicon-32.png',True),(ICON,192,192,R+'assets/icon-192.png',True),(ICON,512,512,R+'assets/icon-512.png',True),
      (MASK,512,512,R+'assets/icon-maskable-512.png',False),(ICON_SQ,180,180,R+'assets/apple-touch-icon.png',False)]
with sync_playwright() as p:
    br=p.chromium.launch()
    for src,w,h,out,a in jobs:
        pg=br.new_page(viewport={'width':w,'height':h})
        pg.set_content(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600"><body style="margin:0">{src.replace("<svg ",f"<svg style=\"display:block;width:{w}px;height:{h}px\" ",1)}</body>')
        pg.wait_for_timeout(400); pg.screenshot(path=out,omit_background=a); pg.close()
        if not a: Image.open(out).convert('RGB').save(out)
    br.close()
print('ok')
