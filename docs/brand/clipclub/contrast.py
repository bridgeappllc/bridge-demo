def L(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)];c=[x/12.92 if x<=.03928 else ((x+.055)/1.055)**2.4 for x in c];return .2126*c[0]+.7152*c[1]+.0722*c[2]
def cr(a,b):a,b=L(a),L(b);return (max(a,b)+.05)/(min(a,b)+.05)
P=[("Headlines (Navy) on Mist","#0F1E3D","#F4F7FE",4.5),("Body (Charcoal) on Mist","#2B2F36","#F4F7FE",4.5),("Body on white card","#2B2F36","#FFFFFF",4.5),
("Muted on Mist","#4B5568","#F4F7FE",4.5),("Muted on tint","#4B5568","#E3ECFD",4.5),("Muted on white","#4B5568","#FFFFFF",4.5),
("Button text white on Blue","#FFFFFF","#1D4ED8",4.5),("White on Blue hover","#FFFFFF","#1E40AF",4.5),("Links Blue on Mist","#1D4ED8","#F4F7FE",4.5),
("Blue on white","#1D4ED8","#FFFFFF",4.5),("Outline hover Blue on tint","#1D4ED8","#E3ECFD",4.5),("Tag text #1E40AF on tint","#1E40AF","#E3ECFD",4.5),
("Friend chat bubble Navy on Sky","#0F1E3D","#60A5FA",4.5),("Own chat bubble white on Blue","#FFFFFF","#1D4ED8",4.5),
("Info note #1E3A8A on #EEF3FE","#1E3A8A","#EEF3FE",4.5),("Field border #7887A3 on white (UI 3:1)","#7887A3","#FFFFFF",3.0),
("Sky on white (decorative only)","#60A5FA","#FFFFFF",0),("Charcoal dark bg w/ Mist text","#F4F7FE","#2B2F36",4.5)]
print("| Pair | Colours | Ratio | Result |\n|---|---|---|---|")
for n,a,b,t in P:
    r=cr(a,b);print(f"| {n} | `{a}` on `{b}` | {r:.2f}:1 | {'AA ✓' if t and r>=t else ('decorative (not text)' if not t else 'FAIL')} |")
