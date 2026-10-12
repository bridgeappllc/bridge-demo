"""Clip Club rename: user-visible wording only (DB names, RPCs, routes, storage keys untouched)."""
import re,sys,glob
R='/workspace/bridge-demo-repo/'
PAIRS=[
 ("Meet me on the Bridge with this","Start a club with this"),
 ("Meet me on the Bridge: listen to","Join my Clip Club: listen to"),
 ("Meet Me on the Bridge","Start a Club"),
 ('Meet ${esc(nameOf(c.owner)||"them")} on the Bridge with this','Send to ${esc(nameOf(c.owner)||"them")}'),
 ("Meet {A} on the Bridge with this","Send to {A}"),
 ("Meet <friend> on the Bridge","Start a club with <friend>"),
 ("Meet ${fn} on the Bridge","Start a club with ${fn}"),
 ("invited you to meet on the Bridge","invited you to their Clip Club"),
 ("Send a bridge","Send a clip"),("sent you a bridge","sent you a clip"),("Bridge sent to","Clip sent to"),
 ("Your Bridges","Your Clubs"),("New Bridge","New Club"),('bridges:"Bridges"','bridges:"Clubs"'),
 ('"Friends","Bridges","Settings"','"Friends","Clubs","Settings"'),('profTab==="Bridges"','profTab==="Clubs"'),
 ('<span class="sm">Bridges</span>','<span class="sm">Clubs</span>'),
 ("No bridges yet","No clubs yet"),("This bridge is full","This club is full"),("Bridge not found","Club not found"),
 ("Join the bridge","Join the club"),("You're on the bridge","You're in the club"),("joined your bridge","joined your club"),
 ("'s bridge","'s club"),("is on this bridge","is in this club"),("added to this bridge","added to this club"),
 ("People you've bridged with","People from your clubs"),("ve bridged with","from your clubs"),
 ("People you meet on a bridge","People you meet in a club"),("been on a bridge with","been in a club with"),
 ("Pick something to bridge on together","Pick something to talk about together"),
 ("Go to Bridge","Go to Clip Club"),("Bridge account","Clip Club account"),
 ("Bridge: go to Your Clubs","Clip Club: go to Your Clubs"),("Bridge: go to Welcome","Clip Club: go to Welcome"),
 ('aria-label="Bridge logo"','aria-label="Clip Club logo"'),
 ("<title>Bridge</title>","<title>Clip Club</title>"),('<h1 class="wm">Bridge</h1>','<h1 class="wm">Clip Club</h1>'),
 ("<b>Bridge</b></button>","<b>Clip Club</b></button>"),("About Bridge","About Clip Club"),
 ("Bridges you share","Clubs you share"),("Bridges you shared","Clubs you shared"),("Bridges you already share","Clubs you already share"),
 ("Bridges sent to you","Clips sent to you"),("in their Bridges","in their Clubs"),("It's in their Bridges list","It's in their Clubs list"),
 ("your bridges","your clubs"),("its bridges","its clubs"),("account's bridges","account's clubs"),("new bridges","new clubs"),
 ("this bridge","this club"),("Bridge partner","Club partner"),("bridge partner","club partner"),("a bridge","a club"),
 ("Bridge LLC","@@LLC@@"),
 (" on Bridge"," on Clip Club"),(" to Bridge"," to Clip Club"),(" of Bridge"," of Clip Club"),(" by Bridge"," by Clip Club"),
 ("using Bridge","using Clip Club"),("use Bridge","use Clip Club"),("run Bridge","run Clip Club"),("make Bridge","make Clip Club"),
 ("about Bridge","about Clip Club"),("with Bridge","with Clip Club"),("got Bridge","got Clip Club"),("the Bridge ","the Clip Club "),
 ("Bridge is","Clip Club is"),("Bridge has","Clip Club has"),("Bridge doesn","Clip Club doesn"),("· Bridge<","· Clip Club<"),
 ("Bridge home","Clip Club home"),(">Bridge<",">Clip Club<"),
 ("@@LLC@@","Bridge LLC"),
]
def run(paths):
    for f in paths:
        s=open(f).read();o=s
        for a,b in PAIRS: s=s.replace(a,b)
        if s!=o: open(f,'w').write(s);print('updated',f)
if __name__=='__main__': run(sys.argv[1:] or [R+'index.html',R+'privacy.html',R+'terms.html',R+'support.html'])
MORE=[("Your bridges and library","Your clubs and library"),("people you bridge with","people you share clubs with"),
 ("<b>Bridges</b>:","<b>Clubs</b>:"),("run the bridge between","run the club between"),("on that bridge.","in that club."),
 ("Back to Bridge","Back to Clip Club")]
if __name__=='__main__':
    PAIRS[:]=MORE; run([R+'index.html',R+'privacy.html',R+'terms.html',R+'support.html'])
