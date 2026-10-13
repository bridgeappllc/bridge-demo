"""Group pods UI patch for index.html (applied once on branch group-pods)."""
f='index.html'; s=open(f).read()
def ins(anchor, text, before=True, count=1):
    global s
    assert s.count(anchor)>=1, anchor[:60]
    i=s.index(anchor); s = s[:i]+text+s[i:] if before else s[:i+len(anchor)]+text+s[i+len(anchor):]
def rep(a,b):
    global s
    assert a in s, a[:70]; s=s.replace(a,b,1)

# ---------- API
ins(' async addFriendToBridge(bid,uid)', r''' // group pods (supabase/migrations/20261013120000_group_pods.sql)
 async gpods(){return ok(await sb.from("group_pods").select("id,name,owner,created_at,group_pod_members(user_id,display_name,role),group_pod_clips(id,title,created_at)").order("created_at",{ascending:false}))||[]},
 async gpod(id){const[p,c,m]=await Promise.all([sb.from("group_pods").select("id,name,owner,max_members,created_at,group_pod_members(user_id,display_name,role,joined_at)").eq("id",id).maybeSingle(),sb.from("group_pods").select("id").limit(0),sb.from("group_pod_messages").select("id,user_id,display_name,body,created_at").eq("pod_id",id).order("id").limit(500)]);
  const pod=ok(p);if(!pod)return{pod:null};const clips=ok(await sb.from("group_pod_clips").select("id,shared_by,shared_by_name,title,url,kind,note,created_at").eq("pod_id",id).order("created_at",{ascending:false}).limit(100))||[];
  const ans=clips.length?ok(await sb.from("group_pod_answers").select("clip_id,user_id,a1,a2,a3").in("clip_id",clips.map(x=>x.id)))||[]:[];return{pod,clips,ans,messages:ok(m)||[]}},
 async gcreate(name,ids){return ok(await sb.rpc("create_group_pod",{p_name:name,p_members:ids}))},
 async gadd(pod,ids){return ok(await sb.rpc("add_group_members",{p_pod:pod,p_members:ids}))},
 async gremove(pod,uid){ok(await sb.rpc("remove_group_member",{p_pod:pod,p_user:uid}))},
 async gleave(pod){ok(await sb.rpc("leave_group_pod",{p_pod:pod}))},
 async gshare(pod,c,note){return ok(await sb.rpc("share_to_group_pod",{p_pod:pod,p_title:c.title,p_url:c.url,p_kind:c.type||"Article",p_note:note||""}))},
 async ganswer(clip,a){ok(await sb.rpc("answer_group_clip",{p_clip:clip,p_a1:a[0],p_a2:a[1],p_a3:a[2]}))},
 async gsend(pod,t){return ok(await sb.rpc("send_group_message",{p_pod:pod,p_body:t}))},
 watchG(id,cb,ms){let ch=null;try{ch=sb.channel("gpod:"+id+":"+Math.random().toString(36).slice(2));for(const t of["group_pod_messages","group_pod_clips","group_pod_members"])ch.on("postgres_changes",{event:"*",schema:"public",table:t,filter:"pod_id=eq."+id},()=>cb());ch.subscribe(st=>{window.__podRealtime=st})}catch(e){ch=null}
  const iv=setInterval(()=>{if(!document.hidden)cb()},ms||4000);return()=>{clearInterval(iv);if(ch)sb.removeChannel(ch)}},
''')
rep('select("id,kind,actor,actor_name,bridge_id,title,count,created_at,read_at")','select("id,kind,actor,actor_name,bridge_id,group_pod_id,title,count,created_at,read_at")')
# ---------- notifications
rep('joined:`${a} joined your pod${t}`}','joined:`${a} joined your pod${t}`,pod_added:`${a} added you to the pod${t}`,pod_clip:`${a} shared a clip in your pod:${t}`,pod_message:`${a} sent ${n.count>1?n.count+" messages":"a message"} in${t}`}')
rep('const nTarget=n=>','const nTarget=n=>n.group_pod_id?"pod/"+n.group_pod_id:')
# ---------- state
rep('const freshDB=()=>({','const freshDB=()=>({gl:null,g:{},gsel:{},')
# ---------- helpers + views
ins('const bridgeCard=b=>', r'''const gMembers=P=>(P.group_pod_members||[]).slice().sort((a,b)=>(a.role==="owner"?-1:0)-(b.role==="owner"?-1:0)||String(a.joined_at||"").localeCompare(String(b.joined_at||"")));
const gStack=(P,n=5)=>`<div class="gstack">${gMembers(P).slice(0,n).map(m=>AV(m.display_name,30,m.user_id)).join("")}${(P.group_pod_members||[]).length>n?`<span class="gmore">+${P.group_pod_members.length-n}</span>`:""}</div>`;
const gCard=P=>{const c=(P.group_pod_clips||[]).slice().sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))[0];return `<div class="card gcard" style="cursor:pointer" onclick="go('pod/${P.id}')"><span class="tag">Group pod</span><div class="bcrow" style="margin-top:6px"><div style="flex:1;min-width:0"><div class="ti">${esc(P.name)}</div><div class="mut sm">${(P.group_pod_members||[]).length} people${c?" · Latest: "+esc(c.title):" · Nothing shared yet"}</div></div>${gStack(P,3)}</div></div>`};
const gPicker=()=>{const sel=DB.gsel,q=DB.srch.q||"",rows=q.trim().replace(/^@/,"").length>=2?DB.srch.rows:null;
 const item=p=>p.id===ME?"":`<label class="chk gpk"><input type="checkbox" data-gp="${p.id}" data-gn="${esc(p.display_name)}"${sel[p.id]?" checked":""}>${AV(p.display_name,32,p.id)}<span>${esc(p.display_name)}${p.username?` <span class="mut sm">@${esc(p.username)}</span>`:""}</span></label>`;
 const chosen=Object.entries(sel);
 return `<p class="sm" id="gcount" aria-live="polite"><b>${chosen.length}</b> picked${chosen.length?": "+chosen.map(([,n])=>esc(n)).join(", "):""}</p><label for="gpq">Find people</label><input id="gpq" type="search" placeholder="Name or @username" value="${esc(q)}" autocomplete="off" maxlength="40">
<div id="gpres">${rows===null?(q.trim().length>=2?loading:""):rows.length?rows.map(item).join(""):'<p class="mut sm">No one found.</p>'}</div><h3 class="sm" style="margin:14px 0 4px">Your friends</h3>${DB.friends===null?loading:DB.friends.length?DB.friends.map(item).join(""):'<p class="mut sm">No friends yet — find people above.</p>'}`};
const gAnsOf=(D,cid,uid)=>D.ans.find(a=>a.clip_id===cid&&a.user_id===uid);
const gNameOf=(D,uid)=>{const m=(D.pod.group_pod_members||[]).find(x=>x.user_id===uid);return m?m.display_name:"Former member"};
''')
ins('bridges(){const L=DB.list;', r'''newpod(){return `<p class="mut sm"><a href="#bridges">← Your Pods</a></p><h1>Create a pod</h1><p class="mut">A pod is a small group (up to 12 people) that shares clips, answers 3 quick questions, then chats.</p>
<label for="gname">Pod name</label><input id="gname" placeholder="e.g. Sunday listeners" maxlength="60" value="${esc(S.gname||"")}">${gPicker()}<div class="btmbar"><button class="btn big" id="ggo">Create pod</button></div>`},
pod(id){const D=DB.g[id];if(D===undefined)return loading;if(!D||!D.pod)return `<h1>Pod not found</h1><p class="mut">You're not in this pod, or it was deleted.</p><a class="btn o" href="#bridges">Go to Your Pods</a>`;
 const P=D.pod,mine=P.owner===ME,newest=D.clips[0],open=!newest||!!gAnsOf(D,newest.id,ME);let prev=null;
 const memRow=m=>`<div class="person gmem">${AV(m.display_name,36,m.user_id)}<div class="pi"><b>${esc(m.display_name)}${m.user_id===ME?" (you)":""}</b><span class="mut sm">${m.role==="owner"?"Owner":"Member"}</span></div>${mine&&m.user_id!==ME?`<button class="btn o s" data-grm="${m.user_id}" data-gn="${esc(m.display_name)}" aria-label="Remove ${esc(m.display_name)}">Remove</button>`:""}</div>`;
 const clipH=c=>{const my=gAnsOf(D,c.id,ME),others=D.ans.filter(a=>a.clip_id===c.id&&a.user_id!==ME);return `<div class="card gclip" id="gc-${c.id}"><span class="tag">${esc(c.kind)}</span><div class="ti" style="margin-top:6px"><a href="${esc(safeUrl(c.url))}" target="_blank" rel="noopener">${esc(c.title)} ↗</a></div><div class="mut sm">Shared by ${esc(c.shared_by===ME?"you":c.shared_by_name||"someone")} · ${since(c.created_at)}</div>${c.note?`<p class="sdq">“${esc(c.note)}”</p>`:""}
${my?`<details${c===newest?" open":""}><summary class="sm">✓ You answered · ${others.length} other${others.length===1?"":"s"} answered</summary>${[{user_id:ME,a1:my.a1,a2:my.a2,a3:my.a3},...others].map(a=>`<div class="gans"><div class="who">${AV(a.user_id===ME?PROFILE.display_name:gNameOf(D,a.user_id),24,a.user_id)}${esc(a.user_id===ME?"You":gNameOf(D,a.user_id))}</div>${QS.map((q,i)=>`<p class="sm" style="margin:4px 0"><span class="mut">${i+1}.</span> ${esc(a["a"+(i+1)])}</p>`).join("")}</div>`).join("")}</details>`
:`<details${c===newest?" open":""}><summary class="sm"><b>Answer 3 questions</b> to see the others' answers${c===newest?" and join the chat":""}</summary>${QS.map((q,i)=>`<label for="ga-${c.id}-${i}">${i+1}. ${q}</label><textarea class="gq" data-gc="${c.id}" id="ga-${c.id}-${i}" rows="3" maxlength="4000"></textarea>`).join("")}<p class="err sm" id="gh-${c.id}" aria-live="polite"></p><button class="btn" data-gans="${c.id}">Submit answers</button></details>`}</div>`};
 return `<p class="mut sm"><a href="#bridges">← Your Pods</a></p><h1 style="margin-bottom:4px">${esc(P.name)}</h1><div class="bcrow" style="gap:10px">${gStack(P,6)}<span class="mut sm">${(P.group_pod_members||[]).length} of ${P.max_members} people</span></div>
<details class="card" id="gmembers"><summary><b>Members</b></summary>${gMembers(P).map(memRow).join("")}${mine?`<button class="btn o" id="gaddbtn">＋ Add people</button><div id="gaddbox"></div>`:""}<button class="btn danger-o" id="gleave">Leave pod</button></details>
<h2>Shared clips</h2><button class="btn" id="gsharebtn">${GLYPH}Share a clip with the pod</button><div id="gsharebox"></div>
${D.clips.length?D.clips.map(clipH).join(""):'<div class="card c"><p class="ti" style="margin:4px 0">Nothing shared yet</p><p class="mut sm">Share a podcast, video or article. Everyone listens, answers 3 quick questions, then chats.</p></div>'}
<h2>💬 Group chat</h2>${open?`<div id="gchat">${D.messages.map(m=>{const me=m.user_id===ME,who=me||m.user_id===prev?"":`<div class="who">${AV(m.display_name,24,m.user_id)}${esc(m.display_name||gNameOf(D,m.user_id))}</div>`;prev=m.user_id;return who+`<div class="bub ${me?"me":""}">${esc(m.body)}</div>`}).join("")||'<p class="mut sm">No messages yet. Say hi 👋</p>'}</div><div class="row"><input id="gct" placeholder="Message the pod…" maxlength="2000" aria-label="Message the pod"><button class="btn s" id="gcs">Send</button></div>`
:`<div class="lock">${LOCK}<div class="ti" style="margin-top:6px">Chat locked</div><p class="mut sm">Listen to “${esc(newest.title)}” and answer its 3 questions to join the chat.</p></div>`}`},
''')
rep('<button class="btn big" onclick="go(\'new\')">${GLYPH}Check this out</button>','<button class="btn big" onclick="go(\'new\')">${GLYPH}Check this out</button><button class="btn o" id="gnew" onclick="go(\'newpod\')">＋ Create a pod</button>${(DB.gl||[]).length?`<h2 style="margin:18px 0 6px;font-size:1.15rem">Group pods</h2>${DB.gl.map(gCard).join("")}`:""}')
# ---------- binders
ins('people(){const q=$("#pq");', r'''newpod(){const n=$("#gname");n.oninput=()=>{S.gname=n.value;save()};bindPicker();
 $("#ggo").onclick=async()=>{const name=n.value.trim(),ids=Object.keys(DB.gsel);if(!name){n.focus();return toast("Give your pod a name")}if(!ids.length)return toast("Pick at least one person");if(!modOk(n,true))return;const b=$("#ggo");busy(b,true);
  try{const id=await API.gcreate(name,ids);DB.gsel={};delete S.gname;save();DB.gl=null;toast("Pod created 🎉");go("pod/"+id)}catch(e){busy(b,false);if(!modFail(e,n))fail(e)}}},
pod(id){const D=DB.g[id];if(!D||!D.pod)return;
 $$("[data-grm]").forEach(b=>b.onclick=async()=>{if(!confirm(`Remove ${b.dataset.gn} from this pod?`))return;busy(b,true);try{await API.gremove(id,b.dataset.grm);toast("Removed");await loadGpod(id)}catch(e){busy(b,false);fail(e)}});
 const lv=$("#gleave");if(lv)lv.onclick=async()=>{if(!confirm("Leave this pod? You can be added again by the owner."))return;busy(lv,true);try{await API.gleave(id);delete DB.g[id];DB.gl=null;toast("You left the pod");go("bridges")}catch(e){busy(lv,false);fail(e)}};
 const ab=$("#gaddbtn");if(ab)ab.onclick=()=>{DB.gsel={};DB.srch={q:"",rows:null};gAddOpen=id;if(DB.friends===null)loadSocial();paintAdd(id)};if(gAddOpen===id)paintAdd(id);
 const sb_=$("#gsharebtn");sb_.onclick=()=>{gShareOpen=gShareOpen===id?null:id;paintShare(id)};if(gShareOpen===id)paintShare(id);
 $$("[data-gans]").forEach(b=>b.onclick=async()=>{const cid=b.dataset.gans,tx=$$(`.gq[data-gc="${cid}"]`),a=tx.map(t=>t.value.trim()),h=$("#gh-"+cid);if(a.some(x=>x.length<3)){h.textContent="Please answer all three questions.";return}
  const bad=tx.find(t=>MOD.scan(t.value)==="hate");if(bad){ierr(bad,MSG.post);return}if(!confirm("Submit your answers? You can't edit them afterwards."))return;busy(b,true);
  try{await API.ganswer(cid,a);await loadGpod(id);toast("Answers shared ✓")}catch(e){busy(b,false);if(isMod(e)){MOD.load(true);h.textContent=MSG.post}else fail(e)}});
 const cs=$("#gcs");if(cs){let sending=false;const send=async()=>{const t=$("#gct").value.trim();if(!t||sending)return;if(!modOk($("#gct"),false))return;const masked=MOD.scan(t)==="profanity";sending=true;cs.disabled=true;
  try{await API.gsend(id,t);$("#gct").value="";await loadGpod(id);if(masked)toast("Sent — some words were hidden with ***")}catch(e){if(!modFail(e,$("#gct")))fail(e)}sending=false;if($("#gcs"))$("#gcs").disabled=false;if($("#gct"))$("#gct").focus()};cs.onclick=send;$("#gct").onkeydown=e=>{if(e.key==="Enter")send()}}},
''')
# picker/share helpers (outside V/B)
ins('function afterTopics(){', r'''let gAddOpen=null,gShareOpen=null;
function bindPicker(onChange){const q=$("#gpq");if(q){let t;q.oninput=()=>{clearTimeout(t);t=setTimeout(()=>searchPeople(q.value),250)}}
 $$("[data-gp]").forEach(c=>c.onchange=()=>{if(c.checked)DB.gsel[c.dataset.gp]=c.dataset.gn;else delete DB.gsel[c.dataset.gp];$$(`[data-gp="${c.dataset.gp}"]`).forEach(x=>x.checked=c.checked);const n=Object.entries(DB.gsel);const g=$("#gcount");if(g)g.innerHTML=`<b>${n.length}</b> picked${n.length?": "+n.map(([,v])=>esc(v)).join(", "):""}`;if(onChange)onChange()})}
function paintAdd(id){const box=$("#gaddbox");if(!box)return;const D=DB.g[id],have=new Set((D.pod.group_pod_members||[]).map(m=>m.user_id));const keep=$("#gpq")&&document.activeElement===$("#gpq");
 box.innerHTML=gPicker()+'<button class="btn" id="gaddgo">Add to pod</button>';$$("#gaddbox [data-gp]").forEach(c=>{if(have.has(c.dataset.gp))c.closest("label").remove()});bindPicker();if(keep){const q=$("#gpq");q.focus();q.setSelectionRange(q.value.length,q.value.length)}
 $("#gaddgo").onclick=async()=>{const ids=Object.keys(DB.gsel).filter(x=>!have.has(x));if(!ids.length)return toast("Pick someone to add");const b=$("#gaddgo");busy(b,true);try{const n=await API.gadd(id,ids);DB.gsel={};gAddOpen=null;toast(`Added ${n} ${n===1?"person":"people"}`);await loadGpod(id)}catch(e){busy(b,false);fail(e)}}}
function paintShare(id){const box=$("#gsharebox");if(!box)return;if(gShareOpen!==id){box.innerHTML="";return}if(box.innerHTML)return;const L=DB.lib||[];if(DB.lib===null)loadLib();
 box.innerHTML=`<div class="card"><label for="gspick">From your library</label><select id="gspick"><option value="">— Or paste a link below —</option>${L.map(it=>`<option value="${it.id}">${esc(it.title)}</option>`).join("")}</select>
<label for="gsurl">Link</label><input id="gsurl" type="url" placeholder="https://…" maxlength="2000"><label for="gstitle">Title</label><input id="gstitle" placeholder="What is it called?" maxlength="300">
<label for="gsnote">Note <span class="mut sm">(optional)</span></label><textarea id="gsnote" rows="2" maxlength="300" placeholder="Why should the pod listen?"></textarea><button class="btn" id="gsgo">Share with the pod</button></div>`;
 $("#gspick").onchange=()=>{const it=L.find(x=>x.id===$("#gspick").value);if(it){$("#gsurl").value=it.url;$("#gstitle").value=it.title}};
 $("#gsgo").onclick=async()=>{const url=normUrl($("#gsurl").value.trim()),title=$("#gstitle").value.trim()||url;if(!/^https?:\/\/\S+\.\S+/i.test(url))return toast("Please paste a valid link");if(!modOk($("#gsnote"),false)||!modOk($("#gstitle"),false))return;const it=L.find(x=>x.id===$("#gspick").value);const b=$("#gsgo");busy(b,true);
  try{await API.gshare(id,{url,title:title.slice(0,300),type:it?it.kind:kindOf(url)},$("#gsnote").value.trim());gShareOpen=null;toast("Shared with the pod 📨");await loadGpod(id)}catch(e){busy(b,false);if(!modFail(e,$("#gsnote")))fail(e)}}}
async function loadGpods(){try{DB.gl=await API.gpods();rerender()}catch(e){console.warn(e)}}
async function loadGpod(id){try{DB.g[id]=await API.gpod(id);if(parse().id===id)rerender()}catch(e){if(DB.g[id]===undefined)DB.g[id]=null;fail(e);rerender()}}
''')
# routing / render
rep('const viewData=(v,id)=>v==="bridge"?DB.d[id]:v==="bridges"?[DB.list,DB.inc]:','const viewData=(v,id)=>v==="pod"?[DB.g[id],gAddOpen===id?[DB.srch,DB.friends]:0]:v==="newpod"?[DB.srch,DB.friends]:v==="bridge"?DB.d[id]:v==="bridges"?[DB.list,DB.inc,DB.gl]:')
rep('curTab={bridges:"bridges",bridge:"bridges",','curTab={bridges:"bridges",bridge:"bridges",pod:"bridges",newpod:"bridges",')
rep(' if(v==="bridges"){loadList();unwatch=API.watch(null,loadList,10000)}',' if(v==="bridges"){loadList();loadGpods();unwatch=API.watch(null,()=>{loadList();loadGpods()},10000)}\n if(v==="newpod"){if(DB.friends===null)loadSocial();DB.srch={q:"",rows:null}}\n if(v==="pod"){gShareOpen=null;gAddOpen=null;loadGpod(id);unwatch=API.watchG(id,()=>loadGpod(id),POLL_MS)}')
rep('if(v==="bridge"&&$("#chat")){','if(v==="pod"&&$("#gchat")){const n=DB.g[id].messages.length;if(n!==lastMsgCount&&lastMsgCount>=0&&n>lastMsgCount)$("#gct").scrollIntoView({block:"end"});lastMsgCount=n}else if(v==="bridge"&&$("#chat")){')
# css
rep('.gl{width:1.15em','.gstack{display:flex;align-items:center}.gstack .av{margin-left:-8px;box-shadow:0 0 0 2px var(--sf);border-radius:50%}.gstack .av:first-child{margin-left:0}.gmore{font-size:.75rem;color:var(--m);margin-left:6px}.gpk{padding:6px 0;border-bottom:1px solid var(--l)}.gpk input{width:20px;height:20px;flex:none;accent-color:var(--b)}.gmem{padding:6px 0}.gmem .pi{display:flex;flex-direction:column}.gclip details{margin-top:8px}.gclip summary{cursor:pointer;color:var(--b);padding:6px 0}.gans{border-top:1px solid var(--l);padding:6px 0}#gmembers summary{cursor:pointer;padding:4px 0}.gl{width:1.15em')
open(f,'w').write(s); print("patched")
