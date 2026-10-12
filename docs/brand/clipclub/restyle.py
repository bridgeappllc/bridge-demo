"""Clip Club Blue palette + two-bubble logo + DM Sans headings for index/legal pages."""
import re
R='/workspace/bridge-demo-repo/'
MARK=('<g stroke-linejoin="round"><rect x="6" y="12" width="54" height="40" rx="13" fill="#60A5FA"/><path d="M15 48 L9 64 L31 50 Z" fill="#60A5FA" stroke="#60A5FA" stroke-width="3"/>'
 '<g stroke="#F4F7FE" stroke-width="5" paint-order="stroke"><path d="M78 72 L90 88 L88 72 Z" fill="#1D4ED8"/><rect x="32" y="31" width="62" height="45" rx="14" fill="#1D4ED8"/></g>'
 '<path d="M77 72 L89 87 L87 70 Z" fill="#1D4ED8" stroke="#1D4ED8" stroke-width="3"/><path d="M57 44 L74 53.5 L57 63 Z" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="4"/></g>')
C=[("#F3F6FA","#F4F7FE"),("#E4E9F0","#E8EEFB"),("#16233B","#0F1E3D"),("#2B4C7E","#1D4ED8"),("#213B63","#1E40AF"),
 ("#785A26","#1E40AF"),("#F1EADB","#E3ECFD"),("#E4EBF5","#E3ECFD"),("#DCE3EE","#DCE5F7"),("#E9EEF5","#E8EFFC"),
 ("#E6ECF4","#60A5FA"),("#56617A","#4B5568"),("#4E586C","#4B5568"),("#7D879A","#7887A3"),("#9DB8E0","#60A5FA"),
 ("rgba(43,76,126","rgba(29,78,216"),("rgba(22,35,59","rgba(15,30,61"),("rgba(243,246,250","rgba(244,247,254"),("rgba(120,90,38","rgba(29,78,216"),
 ("#F4EBD9","#EEF3FE"),("#5E4519","#1E3A8A")]
for f in ['index.html','privacy.html','terms.html','support.html']:
    s=open(R+f).read()
    s=re.sub(r'<g fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M40 43V60.*?M4 64H96"[^>]*/></g>',MARK,s)
    for a,b in C: s=s.replace(a,b).replace(a.lower(),b)
    s=s.replace("'DM Serif Display',Georgia,'Times New Roman',serif","'DM Sans',system-ui,sans-serif")
    s=s.replace("'DM Serif Display',var(--serif);font-weight:400","'DM Sans',var(--serif);font-weight:700")
    s=s.replace("'DM Serif Display',Georgia,serif;font-weight:400","'DM Sans',system-ui,sans-serif;font-weight:700")
    s=s.replace("var(--serif);font-weight:400","var(--serif);font-weight:700")
    s=s.replace("h1,h2,h3{font-family:var(--serif);font-weight:400","h1,h2,h3{font-family:var(--serif);font-weight:700;color:#0F1E3D")
    s=s.replace("body{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:var(--n)","body{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#2B2F36")
    s=s.replace("family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400&family=DM+Serif+Display","family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400")
    open(R+f,'w').write(s)
m=open(R+'manifest.webmanifest').read().replace('"Bridge"','"Clip Club"').replace('#F3F6FA','#F4F7FE'); open(R+'manifest.webmanifest','w').write(m)
