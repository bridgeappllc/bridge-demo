"""Replace the suspension-bridge glyphs (button GLYPH + nav 'Clubs' icon) with a mini two-bubble/play mark."""
import re
f='index.html'; s=open(f).read()
MINI=('<rect x="2" y="3" width="13" height="9.5" rx="3"/><path d="M4.6 12.4 3.4 16l4.2-3.6"/>'
      '<rect x="8" y="8.5" width="14" height="10" rx="3" fill="currentColor"/><path d="M17.4 18 20 21.4V18z" fill="currentColor"/>'
      '<path class="pl" d="M13.4 11.2 17.4 13.5 13.4 15.8z" stroke="none"/>')
old_g=re.search(r"const GLYPH='[^']*';",s).group(0)
s=s.replace(old_g,"const GLYPH='<svg class=\"gl\" viewBox=\"0 0 24 24\" aria-hidden=\"true\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.7\" stroke-linecap=\"round\" stroke-linejoin=\"round\">"+MINI+"</svg>';")
s=re.sub(r"bridges:'<path d=\"M2 15\.5Q5[^']*'","bridges:'"+MINI+"'",s)
css='.pl{fill:#FFFFFF}.btn:not(.o) .pl{fill:var(--b)}'
s=s.replace('.gl{width:1.15em',css+'.gl{width:1.15em',1)
# sticky :hover on touch screens made tapped buttons look near-black; only darken on real hover devices
h='.btn:not(:disabled):hover{background:#3A5645;border-color:#3A5645}'
assert h in s; s=s.replace(h,'@media (hover:hover){'+h+'}')
open(f,'w').write(s)
