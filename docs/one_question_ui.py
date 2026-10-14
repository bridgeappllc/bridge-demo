import re
f='index.html';s=open(f).read()
def r(a,b,cnt=1):
    global s; assert s.count(a)==cnt,(a[:80],s.count(a)); s=s.replace(a,b)
# helpers
r('const QS=[','const RQ="How much value did this bring you?";\nconst QS=[')
r('const personRow=','''const Q1=()=>QS[2];
const rateScale=(key)=>`<fieldset class="rate" data-rk="${key}"><legend>${RQ} <span class="mut sm">(0 = none, 10 = a lot)</span></legend><div class="rsc" role="radiogroup" aria-label="${RQ}">${[...Array(11).keys()].map(n=>`<button type="button" role="radio" aria-checked="false" data-rv="${n}" aria-label="${n} out of 10">${n}</button>`).join("")}</div><div class="rlab sm mut" aria-hidden="true"><span>None</span><span>A lot</span></div></fieldset>`;
const rateOf=k=>{const b=document.querySelector(`.rate[data-rk="${k}"] [aria-checked=true]`);return b?+b.dataset.rv:null};
function bindRate(){$$(".rate").forEach(fs=>{const bs=[...fs.querySelectorAll("[data-rv]")];bs.forEach((b,i)=>{b.tabIndex=i===0?0:-1;b.onclick=()=>{bs.forEach(x=>{x.setAttribute("aria-checked",x===b?"true":"false");x.tabIndex=x===b?0:-1});const h=fs.parentElement.querySelector("[data-hint]");if(h)h.textContent=""};
 b.onkeydown=e=>{const d={ArrowRight:1,ArrowUp:1,ArrowLeft:-1,ArrowDown:-1}[e.key];if(!d)return;e.preventDefault();const n=bs[Math.max(0,Math.min(10,i+d))];n.focus();n.click()}})})}
const rChip=v=>v==null?"":`<span class="rchip" aria-label="Rated ${v} out of 10">${v}<small>/10</small></span>`;
const ansHTML=a=>a.a1?QS.map((q,i)=>`<p class="sm" style="margin:4px 0"><span class="mut">${i+1}.</span> ${esc(a["a"+(i+1)]||"")}</p>`).join(""):`<p class="sm" style="margin:4px 0">${esc(a.a3||"")}</p>`;
const personRow=''')
# API
r('async answer(id,a){ok(await sb.from("answers").insert({bridge_id:id,user_id:ME,a1:a[0],a2:a[1],a3:a[2]}))},','async answer(id,a,rating){ok(await sb.from("answers").insert({bridge_id:id,user_id:ME,a3:a,rating}))},')
r('sb.from("answers").select("user_id,a1,a2,a3")','sb.from("answers").select("user_id,a1,a2,a3,rating")')
r('async ganswer(clip,a){ok(await sb.rpc("answer_group_clip",{p_clip:clip,p_a1:a[0],p_a2:a[1],p_a3:a[2]}))},','async ganswer(clip,a,rating){ok(await sb.rpc("answer_group_clip_v2",{p_clip:clip,p_answer:a,p_rating:rating}))},')
r('select("clip_id,user_id,a1,a2,a3")','select("clip_id,user_id,a1,a2,a3,rating")')
# copy
r('answered the 3 questions on${t}','answered and rated${t}')
r('Accept to listen, answer 3 questions, then talk','Accept to listen, answer one question and rate it, then talk')
r('you both listen, answer 3 questions, then talk.','you both listen, answer one question and rate it, then talk.')
r('and answer its 3 questions to join the chat.','and answer & rate it to join the chat.')
r(', then answer three questions.</p>',', then answer one question and rate it.</p>')
r('Unlocks after you answer the three questions.','Unlocks after you answer and rate.')
r('Next: Answer 3 questions','Next: Answer & rate')
# 1:1 form + results
r('<h2>Answer three questions</h2>','<h2>Answer & rate</h2>')
r('${QS.map((q,i)=>`<label class="sm">${i+1}. ${q}</label><textarea rows="3" class="q" maxlength="4000"></textarea>`).join("")}','<label class="sm" for="q3">${Q1()}</label><textarea rows="3" class="q" id="q3" maxlength="4000"></textarea>${rateScale("b")}')
r('<p class="sm" id="qhint" style="color:var(--r)"></p><button class="btn" id="qsave">Submit answers · Unlock chat</button>','<p class="sm" id="qhint" data-hint style="color:var(--r)" aria-live="polite"></p><button class="btn" id="qsave">Submit · Unlock chat</button>')
r('''  else h+=`<h2>Answers</h2>${QS.map((q,i)=>`<div class="card"><div class="sm" style="font-weight:600">${i+1}. ${q}</div><div class="who">You</div><div class="qa">${esc(myA["a"+(i+1)])}</div>${frA?`<div class="who">${fn}</div><div class="qa fr">${esc(frA["a"+(i+1)])}</div>`:""}</div>`).join("")}''',
'''  else h+=`<h2>Answers</h2>${(myA.a1||frA&&frA.a1)?QS.map((q,i)=>`<div class="card"><div class="sm" style="font-weight:600">${i+1}. ${q}</div><div class="who">You</div><div class="qa">${esc(myA["a"+(i+1)]||(i===2?myA.a3:"")||"")}</div>${frA?`<div class="who">${fn}</div><div class="qa fr">${esc(frA["a"+(i+1)]||(i===2?frA.a3:"")||"")}</div>`:""}</div>`).join("")+(myA.rating!=null||frA&&frA.rating!=null?`<div class="card"><div class="sm" style="font-weight:600">${RQ}</div><div class="rrow"><span class="who">You</span>${rChip(myA.rating)||'<span class="mut sm">—</span>'}</div>${frA?`<div class="rrow"><span class="who">${fn}</span>${rChip(frA.rating)||'<span class="mut sm">—</span>'}</div>`:""}</div>`:""):`<div class="card"><div class="sm" style="font-weight:600">${Q1()}</div><div class="who">You ${rChip(myA.rating)}</div><div class="qa">${esc(myA.a3)}</div>${frA?`<div class="who">${fn} ${rChip(frA.rating)}</div><div class="qa fr">${esc(frA.a3)}</div>`:""}</div>`}''')
r('''$$(".q").forEach(t=>t.oninput=()=>$("#qhint").textContent="");const q=$("#qsave");if(q)q.onclick=async()=>{const a=$$(".q").map(t=>t.value.trim());if(a.some(x=>x.length<3))return $("#qhint").textContent="Please answer all three questions to continue.";const bad=$$(".q").find(t=>MOD.scan(t.value)==="hate");if(bad){ierr(bad,MSG.post);return}''',
'''bindRate();$$(".q").forEach(t=>t.oninput=()=>$("#qhint").textContent="");const q=$("#qsave");if(q)q.onclick=async()=>{const a=$("#q3").value.trim(),rt=rateOf("b");if(a.length<3){$("#q3").focus();return $("#qhint").textContent="Please answer the question to continue."}if(rt==null)return $("#qhint").textContent="Please pick a rating from 0 to 10.";const bad=$$(".q").find(t=>MOD.scan(t.value)==="hate");if(bad){ierr(bad,MSG.post);return}''')
r('try{await API.answer(id,a);await loadBridge(id);toast("Chat unlocked 💬")','try{await API.answer(id,a,rt);await loadBridge(id);toast("Chat unlocked 💬")')
# group form + results
r('<summary class="sm"><b>Answer 3 questions</b> to see the others\' answers${c===newest?" and join the chat":""}</summary>${QS.map((q,i)=>`<label for="ga-${c.id}-${i}">${i+1}. ${q}</label><textarea class="gq" data-gc="${c.id}" id="ga-${c.id}-${i}" rows="3" maxlength="4000"></textarea>`).join("")}<p class="sm" style="color:var(--r)" id="gh-${c.id}" aria-live="polite"></p><button class="btn" data-gans="${c.id}">Submit answers</button>',
 '<summary class="sm"><b>Answer & rate</b> to see the others\' answers${c===newest?" and join the chat":""}</summary><label for="ga-${c.id}">${Q1()}</label><textarea class="gq" data-gc="${c.id}" id="ga-${c.id}" rows="3" maxlength="4000"></textarea>${rateScale(c.id)}<p class="sm" style="color:var(--r)" id="gh-${c.id}" data-hint aria-live="polite"></p><button class="btn" data-gans="${c.id}">Submit</button>')
r('[{user_id:ME,a1:my.a1,a2:my.a2,a3:my.a3},...others].map(a=>`<div class="gans"><div class="who">${AV(a.user_id===ME?PROFILE.display_name:gNameOf(D,a.user_id),24,a.user_id)}${esc(a.user_id===ME?"You":gNameOf(D,a.user_id))}</div>${QS.map((q,i)=>`<p class="sm" style="margin:4px 0"><span class="mut">${i+1}.</span> ${esc(a["a"+(i+1)])}</p>`).join("")}</div>`).join("")}',
 '${(()=>{const all=[{...my,user_id:ME},...others],rs=all.map(a=>a.rating).filter(v=>v!=null);return (rs.length?`<p class="gavg sm"><b>Average value: ${(rs.reduce((x,y)=>x+y,0)/rs.length).toFixed(1)}/10</b> <span class="mut">· ${rs.length} rating${rs.length===1?"":"s"}</span></p>`:"")+(all.some(a=>!a.a1)?`<p class="sm mut" style="margin:6px 0 0">${Q1()}</p>`:"")+all.map(a=>`<div class="gans"><div class="who">${AV(a.user_id===ME?PROFILE.display_name:gNameOf(D,a.user_id),24,a.user_id)}${esc(a.user_id===ME?"You":gNameOf(D,a.user_id))} ${rChip(a.rating)}</div>${ansHTML(a)}</div>`).join("")})()}')
r('''const cid=b.dataset.gans,tx=$$(`.gq[data-gc="${cid}"]`),a=tx.map(t=>t.value.trim()),h=$("#gh-"+cid);if(a.some(x=>x.length<3)){h.textContent="Please answer all three questions.";return}''',
'''const cid=b.dataset.gans,tx=$$(`.gq[data-gc="${cid}"]`),a=tx[0].value.trim(),rt=rateOf(cid),h=$("#gh-"+cid);if(a.length<3){h.textContent="Please answer the question.";tx[0].focus();return}if(rt==null){h.textContent="Please pick a rating from 0 to 10.";return}''')
r('if(!confirm("Submit your answers? You can\'t edit them afterwards."))return;busy(b,true);','if(!confirm("Submit your answer and rating? You can\'t edit them afterwards."))return;busy(b,true);')
r('try{await API.ganswer(cid,a);await loadGpod(id);toast("Answers shared ✓")','try{await API.ganswer(cid,a,rt);await loadGpod(id);toast("Answers shared ✓")')
r('.person{display:flex;','''.rate{border:0;padding:0;margin:12px 0 4px;min-width:0}.rate legend{font-weight:600;font-size:15px;padding:0;margin-bottom:8px}
.rsc{display:grid;grid-template-columns:repeat(11,minmax(0,1fr));gap:3px}
.rsc button{min-height:44px;min-width:0;padding:0;border:1px solid var(--fl);border-radius:10px;background:var(--sf);color:var(--n);font:600 15px var(--serif);cursor:pointer}
.rsc button[aria-checked=true]{background:var(--b);border-color:var(--b);color:var(--onp)}
.rsc button:focus-visible{outline:3px solid var(--ac);outline-offset:2px}
.rlab{display:flex;justify-content:space-between;margin-top:4px}
.rchip{display:inline-flex;align-items:baseline;gap:1px;padding:2px 8px;border-radius:999px;background:var(--bl);color:var(--ac);font-weight:700;font-size:14px;margin-left:6px}.rchip small{font-weight:600;font-size:11px}
.rrow{display:flex;align-items:center;justify-content:space-between;padding:6px 0}
.gavg{background:var(--bl);color:var(--n);border-radius:10px;padding:8px 10px;margin:8px 0}
.person{display:flex;''')
open(f,'w').write(s);print("patched")
