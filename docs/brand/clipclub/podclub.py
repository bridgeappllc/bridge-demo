"""Rename Clip Club -> Pod Club and club(s) -> pod(s) in user-visible text (DB/routes untouched)."""
import re,glob
TAG="Share it with your pod."
def tr(s):
    s=s.replace("A book club for clips",TAG).replace("Clip Club","@@PC@@")
    for a,b in [("Clubs","Pods"),("clubs","pods"),("Club","Pod"),("club","pod")]: s=re.sub(r'\b%s\b'%a,b,s)
    s=s.replace("On a pod","In a pod")
    return s.replace("@@PC@@","Pod Club")
for f in ['index.html','privacy.html','terms.html','support.html','manifest.webmanifest','tests/local-stack/up.sh']+glob.glob('supabase/email-templates/*.html')+glob.glob('tests/*.py'):
    s=open(f).read(); n=tr(s)
    if n!=s: open(f,'w').write(n); print(f)
