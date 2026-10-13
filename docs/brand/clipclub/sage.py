"""Clip Club 'Sage Paper' recolor (from Clip Club Blue). Run from repo root."""
import re
M=[("#1D4ED8","#4A6B57"),("#F4F7FE","#F4F5EF"),("#0F1E3D","#24302A"),("#60A5FA","#A9C2B0"),("#4B5568","#5F6A62"),
 ("#DCE5F7","#DDE2D6"),("#1E40AF","#3A5645"),("#EEF3FE","#EEF2EA"),("#E8EEFB","#E9EBE2"),("#2B2F36","#24302A"),
 ("#1E3A8A","#2F4A3A"),("#E3ECFD","#E4EBE3"),("#E8EFFC","#E9EEE7"),("#7887A3","#7D887F"),
 ("rgba(29,78,216","rgba(74,107,87"),("rgba(15,30,61","rgba(36,48,42"),("rgba(244,247,254","rgba(244,245,239")]
for f in ['index.html','privacy.html','terms.html','support.html','manifest.webmanifest','supabase/email-templates/magic_link.html','supabase/email-templates/email_change.html']:
    s=open(f).read()
    for a,b in M: s=re.sub(re.escape(a),b,s,flags=re.I)
    open(f,'w').write(s)
