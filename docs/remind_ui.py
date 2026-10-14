f='index.html';s=open(f).read()
def r(a,b,cnt=1):
    global s; assert s.count(a)==cnt,(a[:90],s.count(a)); s=s.replace(a,b)
# API
r('async suggest(){return ok(await sb.rpc("suggest_people"))},','''async suggest(){return ok(await sb.rpc("suggest_people"))},
 async remState(kind,pod){const since=new Date(Date.now()-864e5).toISOString();const[c,d]=await Promise.all([sb.rpc("remindable",{p_kind:kind,p_pod:pod}),sb.from("pod_reminders").select("target").eq("pod_id",pod).gt("created_at",since)]);return{can:(ok(c)||[]).map(x=>typeof x==="string"?x:x.remindable||Object.values(x)[0]),done:(ok(d)||[]).map(x=>x.target)}},
 async remind(kind,pod,target){const{data}=await sb.auth.getSession();const t=data&&data.session&&data.session.access_token;
  const r=await fetch(CFG.SUPABASE_URL+"/functions/v1/remind",{method:"POST",headers:{Authorization:"Bearer "+t,apikey:CFG.SUPABASE_ANON_KEY,"Content-Type":"application/json"},body:JSON.stringify({kind,pod,target,app:location.origin+location.pathname,dry_run:!!window.REMIND_DRY})});
  const b=await r.json().catch(()=>({}));if(!r.ok)throw new Error(b.error||"Couldn't send the reminder");return b},
 async setReminders(on){ok(await sb.from("profiles").update({email_reminders:on}).eq("id",ME))},''')
r('from("profiles").select("id,display_name,topics,username,bio,library_visibility,avatar_url"','from("profiles").select("id,display_name,topics,username,bio,library_visibility,avatar_url,email_reminders"')
r('sugg:null,prow:null,','sugg:null,rem:{},prow:null,')
# helpers
r('const personRow=','''const remBtn=(kind,pod,uid,name)=>{const R=DB.rem[pod];if(!R)return "";if(R.done.includes(uid))return `<button class="btn o s rmd done" disabled aria-label="Reminded ${esc(name)}">✓ Reminded</button>`;
 return R.can.includes(uid)?`<button class="btn o s rmd" data-rmd="${uid}" data-rk="${kind}" data-rp="${pod}" data-rn="${esc(name)}" aria-label="Email ${esc(name)} a reminder">🔔 Remind</button>`:""};
async function loadRem(kind,pod){try{DB.rem[pod]=await API.remState(kind,pod);rerender()}catch(e){console.warn(e)}}
document.addEventListener("click",async e=>{const b=e.target.closest("[data-rmd]");if(!b)return;e.preventDefault();const{rmd,rk,rp,rn}=b.dataset;busy(b,true);
 try{const res=await API.remind(rk,rp,rmd);if(res.dry_run){busy(b,false);toast(`Dry run ✓ would email ${res.to}`);return}const R=DB.rem[rp];if(R&&!R.done.includes(rmd))R.done.push(rmd);toast(`Reminder sent to ${rn} ✓`);rerender()}catch(err){busy(b,false);toast(err.message)}});
document.addEventListener("change",async e=>{if(e.target.id!=="erem")return;const on=e.target.checked;try{await API.setReminders(on);PROFILE.email_reminders=on;save&&0;toast(on?"Reminder emails on":"Reminder emails off")}catch(err){e.target.checked=!on;fail(err)}});
const personRow=''')
# notification text
r("pod_message:`${a} sent ${n.count>1?n.count+\" messages\":\"a message\"} in${t}`}[n.kind]","pod_message:`${a} sent ${n.count>1?n.count+\" messages\":\"a message\"} in${t}`,reminder:`${a} reminded you to listen to${t}`}[n.kind]")
# viewData + routing
r('v==="pod"?[DB.g[id],','v==="pod"?[DB.g[id],DB.rem[id],')
r(':v==="bridge"?DB.d[id]:',':v==="bridge"?[DB.d[id],DB.rem[id]]:')
r('if(v==="pod"){gShareOpen=null;gAddOpen=null;loadGpod(id);unwatch=API.watchG(id,()=>loadGpod(id),POLL_MS)}','if(v==="pod"){gShareOpen=null;gAddOpen=null;loadGpod(id);loadRem("group",id);unwatch=API.watchG(id,()=>{loadGpod(id);loadRem("group",id)},POLL_MS)}')
r('if(v==="bridge"){loadBridge(id);unwatch=API.watch(id,()=>loadBridge(id),POLL_MS)}','if(v==="bridge"){loadBridge(id);loadRem("bridge",id);unwatch=API.watch(id,()=>{loadBridge(id);loadRem("bridge",id)},POLL_MS)}')
# 2-person: one line under the step bar while the friend hasn't answered
r('stepbar(cur,st,id,me.role==="friend"?"Joined":"Invite")+','stepbar(cur,st,id,me.role==="friend"?"Joined":"Invite")+(fr&&!fr.answered_at&&!gone&&remBtn("bridge",id,fr.user_id,fn)?`<div class="remrow"><span class="sm mut">${fn} hasn\'t answered yet.</span>${remBtn("bridge",id,fr.user_id,fn)}</div>`:"")+')
# group: per-member button + waiting line
r('${m.user_id!==ME?`<button class="rp" data-rep="user"','${m.user_id!==ME?remBtn("group",P.id,m.user_id,m.display_name):""}${m.user_id!==ME?`<button class="rp" data-rep="user"')
r('<summary><b>Members</b></summary>','<summary><b>Members</b>${(()=>{const R=DB.rem[P.id],n=R?R.can.filter(u=>!R.done.includes(u)).length:0;return n?` <span class="sm mut">· ${n} can be reminded</span>`:""})()}</summary>')
# settings toggle
r('<div class="card"><b>Your name</b>','<div class="card"><label class="chk" style="font-weight:600"><input type="checkbox" id="erem" ${PROFILE.email_reminders!==false?"checked":""}> Email me reminders</label><p class="mut sm" style="margin:4px 0 0">${isGuest()?"Add an email to your account to get reminders when a pod is waiting on you.":"When someone in your pod reminds you to listen, we\'ll email you. Turn off anytime."}</p></div><div class="card"><b>Your name</b>')
r('.person{display:flex;','.remrow{display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--bl);border-radius:12px;padding:8px 10px;margin:8px 0}\n.rmd{flex:none;min-height:40px}.rmd.done{color:var(--g);border-color:var(--g);opacity:1}\n.person{display:flex;')
open(f,'w').write(s);print("patched")
