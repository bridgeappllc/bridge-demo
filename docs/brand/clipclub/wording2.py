"""Paul's wording pass: 'Check this out' / 'X wants you to listen to this'."""
import glob
P=[('Send to ${esc(nameOf(c.owner)||"them")}','Send to ${esc(nameOf(c.owner)||"them")}: Check this out'),
 ("Send to {A}","Send to {A}: Check this out"),
 ("Start a club with ${fn}","Send to ${fn}: Check this out"),("Start a club with <friend>","Send to <friend>: Check this out"),
 ("Start a club with this","Check this out"),("Start a Club","Check this out"),
 ("invited you to their Clip Club","wants you to listen to this"),
 ("sent you a clip:","wants you to listen to this:"),("} sent you a clip<","} wants you to listen to this<"),("sent you a clip","wants you to listen to this"),
 ("Join my Clip Club: listen to","Check this out: listen to")]
for f in ['index.html']+sorted(glob.glob('tests/*.py')):
    s=open(f).read();o=s
    for a,b in P: s=s.replace(a,b)
    if s!=o: open(f,'w').write(s);print(f)
