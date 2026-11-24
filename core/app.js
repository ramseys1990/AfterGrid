"use strict";
const $ = id => document.getElementById(id);
let status;
let pending=new Set(), jobSignature="";
function error(message){ $("error").textContent=message; $("error").hidden=!message; }
function view(name){ for(const id of ["setup","login","dashboard"]) $(id).hidden=id!==name; }
async function api(path,body){
  const response=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok) throw Error(typeof result.detail==="string"?result.detail:"Request failed");
  return result;
}
async function refresh(){
  status=await api("/api/status");
  $("auth").hidden=status.setup_required;
  $("auth").textContent=status.admin?"Sign out":"Administrator login";
  $("server-name").textContent=status.server_name;
  $("version").textContent=status.version;
  $("admin").hidden=!status.admin;
  $("wizard").hidden=!(status.admin && status.selection_pending);
  if(!status.admin){pending.clear();jobSignature="";$("jobs").replaceChildren();$("local-inventory").replaceChildren();$("content-results").replaceChildren();$("downloads").replaceChildren();$("content-message").textContent="";}
  view(status.setup_required?"setup":"dashboard");
  if(!status.setup_required){
    if(status.admin){await renderJobs();refreshLocalContent().catch(e=>{$("local-inventory").textContent=e.message;});}
    await renderModules();
    await refreshHouseholds();
  }
}
async function renderModules(){
    const modules=await api("/api/modules");
    if(status.admin && status.selection_pending)renderWizard(modules);
    $("catalog").replaceChildren();
    for(const mod of modules){
      const card=document.createElement("article");
      for(const [tag,value] of [["small",mod.category],["h3",mod.name],["p",mod.description],["small",mod.status]]){
        const node=document.createElement(tag);node.textContent=value;card.append(node);
      }
      if(mod.installable && mod.status==="running" && (!mod.admin_only||status.admin) && (!mod.loopback_only||(mod.shared&&mod.lan_url)||["127.0.0.1","localhost"].includes(location.hostname))){
        const link=document.createElement("a");
        const url=new URL(mod.shared&&mod.lan_url?mod.lan_url:location.href);if(mod.loopback_only)url.protocol="http:";url.port=mod.port;url.pathname="/";url.search="";url.hash="";
        link.href=url.href;link.textContent="Open application";link.target="_blank";link.rel="noopener noreferrer";card.append(link);
      }
      if(status.admin && mod.installable){
        if(mod.setup_note){const note=document.createElement("p");note.textContent=mod.setup_note;card.append(note);}
        if(mod.loopback_only && !mod.shared && !["127.0.0.1","localhost"].includes(location.hostname)){
          const note=document.createElement("small");note.textContent="Local setup only. SSH forward port "+mod.port+" and open http://127.0.0.1:"+mod.port;card.append(note);
        }
        if(mod.id==="kopia" && mod.status==="running"){
          const reveal=document.createElement("button");reveal.textContent="Show backup credentials";
          const credentials=document.createElement("pre");credentials.hidden=true;
          reveal.addEventListener("click",async()=>{
            if(!credentials.hidden){credentials.textContent="";credentials.hidden=true;reveal.textContent="Show backup credentials";return;}
            if(location.protocol!=="https:"&&!["127.0.0.1","localhost"].includes(location.hostname)&&!confirm("These backup credentials will travel over unencrypted HTTP. Continue only on your trusted LAN?"))return;
            try{const c=await api("/api/admin/kopia/credentials",{});credentials.textContent="Username: "+c.username+"\nUI password: "+c.ui_password+"\nRepository password: "+c.repository_password;credentials.hidden=false;reveal.textContent="Hide credentials";}
            catch(e){error(e.message);}
          });card.append(reveal,credentials);
        }
        const actions=mod.status==="not installed"?["install"]:mod.status==="running"?["stop","restart","update","uninstall"]:["start","install","stop","uninstall"];
        if(mod.shared && mod.lan_url){
          const note=document.createElement("p");note.textContent="LAN URL: "+mod.lan_url+(mod.lan_dns?" — local DNS must point to the server.":" — reserve the server IP for stable links.")+" HTTP is unencrypted.";card.append(note);
        }else if(mod.share_available){
          const note=document.createElement("p");note.textContent=(mod.lan_dns?"Add a local DNS record for "+new URL(mod.lan_url).hostname+". ":"")+"Complete native account setup before sharing. LAN URL: "+mod.lan_url;card.append(note);
        }else if(["homebox","grocy","kopia"].includes(mod.id)){
          const note=document.createElement("small");note.textContent="LAN sharing needs a private LAN bind configured on the server; see the LAN setup guide.";card.append(note);
        }
        if(mod.shared && mod.status!=="not installed")actions.push("unshare");
        else if(mod.share_available&&mod.status==="running")actions.push("share");
        const controls=document.createElement("div");controls.className="controls";
        for(const action of actions){
          const b=document.createElement("button");b.textContent=action==="share"?"Share on LAN":action==="unshare"?"Return to local-only":action;b.addEventListener("click",async()=>{
            if(action==="share"){
              const warning=mod.id==="homebox"?"Confirm you created your Homebox account. Sharing closes public registration.":mod.id==="grocy"?"Confirm you changed Grocy's default administrator password.":"Kopia uses its generated native administrator password. Keep it private.";
              if(!confirm(warning+" "+(mod.lan_dns?"Confirm local DNS is configured. ":"")+"LAN HTTP is unencrypted. Continue only on a trusted LAN?"))return;
            }
            if(action==="unshare"&&!confirm("Return to loopback-only access? This recreates and starts the application while keeping its data."))return;
            if(action==="uninstall"&&!confirm("Remove this application's containers? Its data will be retained."))return;
            if(action==="update"&&!confirm("Pull the configured image and recreate if needed? Back up application data first."))return;
            b.disabled=true;error("");
            try{await api("/api/admin/modules/"+mod.id+"/"+action,{});await renderJobs();await renderModules();}
            catch(e){error(e.message);}finally{b.disabled=false;}
          });b.disabled=pending.has(mod.id);controls.append(b);
        }
        card.append(controls);
      }
      $("catalog").append(card);
    }
}
function renderWizard(modules){
  const root=$("wizard-options");
  const checked=new Set([...root.querySelectorAll("input:checked")].map(i=>i.value));
  root.replaceChildren();
  for(const mod of modules.filter(m=>m.installable&&m.status==="not installed"&&!pending.has(m.id))){
    const label=document.createElement("label");label.className="wizard-option";
    const input=document.createElement("input");input.type="checkbox";input.value=mod.id;input.checked=checked.has(mod.id);
    const description=document.createElement("span");description.textContent=mod.name+" — "+mod.description;
    label.append(input,description);root.append(label);
  }
  if(!root.children.length)root.textContent="No uninstalled applications currently available. You can skip and add applications later.";
}
let submittingWizard=false;
async function submitWizard(modules){
  if(submittingWizard)return;
  submittingWizard=true;error("");
  const controls=$("wizard-form").querySelectorAll("button,input");
  for(const el of controls)el.disabled=true;
  try{
    await api("/api/admin/first-run",{modules});
    await refresh();
  }catch(e){error(e.message);}
  finally{submittingWizard=false;for(const el of controls)el.disabled=false;}
}
$("essentials").addEventListener("click",()=>{
  for(const input of $("wizard-options").querySelectorAll("input"))input.checked=["kiwix","homebox","grocy","kopia"].includes(input.value);
});
$("wizard-form").addEventListener("submit",event=>{
  event.preventDefault();
  const chosen=[...$("wizard-options").querySelectorAll("input:checked")].map(i=>i.value);
  if(!chosen.length){$("wizard-message").textContent="Select an application or use Skip for now.";return;}
  submitWizard(chosen);
});
$("skip-wizard").addEventListener("click",()=>submitWizard([]));

function bytes(value){
  if(value===null||value===undefined)return "Size unavailable";
  if(value<1024)return value+" B";
  const units=["KiB","MiB","GiB","TiB"];
  let n=value/1024,i=0;while(n>=1024&&i<units.length-1){n/=1024;i++;}
  return n.toFixed(1)+" "+units[i];
}
async function refreshLocalContent(){
  const info=await api("/api/admin/content/local");
  if(!status?.admin)return;
  const root=$("local-inventory");root.replaceChildren();
  const p=document.createElement("p");p.textContent=bytes(info.free_bytes)+" free on content storage";root.append(p);
  function control(parent,file,action,label,question){
    const b=document.createElement("button");b.textContent=label;
    b.addEventListener("click",async()=>{
      if(question&&!confirm(question))return;
      b.disabled=true;error("");
      try{await api("/api/admin/content/local",{name:file.name,action});await refreshLocalContent();await renderDownloads();}
      catch(e){error(e.message);}finally{b.disabled=false;}
    });parent.append(b);
  }
  for(const file of info.files){
    const row=document.createElement("article"),line=document.createElement("p");
    line.textContent=file.name+" — "+bytes(file.size_bytes)+(file.indexed?" · indexed":" · not indexed");
    row.append(line);
    if(!file.indexed)control(row,file,"index","Add to library");
    control(row,file,"remove","Remove","Remove "+file.name+" from the library? A recoverable copy will be kept.");
    root.append(row);
  }
  if(info.removed?.length){
    const h=document.createElement("h4");h.textContent="Removed archives (still use storage)";root.append(h);
    for(const file of info.removed){
      const row=document.createElement("article"),line=document.createElement("p");
      line.textContent=file.name+" — "+bytes(file.size_bytes);row.append(line);
      control(row,file,"restore","Restore");
      control(row,file,"purge","Delete permanently","Permanently delete "+file.name+" and reclaim its storage? This cannot be undone.");
      root.append(row);
    }
  }
  if(!info.files.length){const p=document.createElement("p");p.textContent="No local ZIM files found.";root.append(p);}
}
$("local-content").addEventListener("click",()=>refreshLocalContent().catch(e=>{$("local-inventory").textContent=e.message;}));
let contentQuery=null, contentOffset=0, contentBusy=false;
async function searchContent(offset){
  if(contentBusy||!contentQuery||!status?.admin)return;
  contentBusy=true;$("content-prev").disabled=true;$("content-next").disabled=true;
  $("content-message").textContent="Searching official Kiwix catalog…";
  try{
    const params=new URLSearchParams({...contentQuery,start:String(offset)});
    const data=await api("/api/admin/content/catalog?"+params);
    if(!status?.admin)return;
    contentOffset=offset;
    const root=$("content-results");root.replaceChildren();
    for(const entry of data.entries){
      const card=document.createElement("article");
      const h=document.createElement("h4");h.textContent=entry.title;
      const p=document.createElement("p");p.textContent=entry.description;
      const meta=document.createElement("small");meta.textContent=bytes(entry.size_bytes)+" · "+entry.language+" · "+entry.updated.slice(0,10);
      card.append(h,p,meta);
      if(entry.download_key){
        const b=document.createElement("button");b.textContent="Download to server";
        b.addEventListener("click",async()=>{if(!confirm("Download and verify "+entry.title+" ("+bytes(entry.size_bytes)+")?"))return;b.disabled=true;try{await api("/api/admin/content/downloads",{key:entry.download_key});await renderDownloads();}catch(e){error(e.message);}finally{b.disabled=false;}});
        card.append(b);
      }
      root.append(card);
    }
    $("content-message").textContent=data.entries.length?"Showing "+(offset+1)+"–"+(offset+data.entries.length)+(data.total!==null?" of "+data.total:""):"No catalog results.";
    $("content-prev").disabled=offset===0;
    $("content-next").disabled=data.entries.length<20||(data.total!==null&&offset+data.entries.length>=data.total);
  }catch(e){$("content-message").textContent=e.message;}
  finally{contentBusy=false;}
}
$("content-search").addEventListener("submit",event=>{
  event.preventDefault();if(contentBusy)return;contentQuery=Object.fromEntries(new FormData(event.currentTarget));searchContent(0);
});
$("content-prev").addEventListener("click",()=>searchContent(Math.max(0,contentOffset-20)));
$("content-next").addEventListener("click",()=>searchContent(contentOffset+20));

async function renderDownloads(){
  const rows=await api("/api/admin/content/downloads");
  if(!status?.admin)return;
  const root=$("downloads");root.replaceChildren();
  for(const d of rows){
    const card=document.createElement("article"),title=document.createElement("strong"),detail=document.createElement("p");
    title.textContent=d.name+" · "+d.state;detail.textContent=d.detail+" — "+bytes(d.bytes)+" / "+bytes(d.size);card.append(title,detail);
    if(d.size){const bar=document.createElement("progress");bar.max=d.size;bar.value=Math.min(d.bytes,d.size);card.append(bar);}
    if(d.state==="failed"){const retry=document.createElement("button");retry.textContent="Retry / resume";retry.addEventListener("click",async()=>{try{await api("/api/admin/content/downloads",{key:d.key});await renderDownloads();}catch(e){error(e.message);}});card.append(retry);}
    root.append(card);
  }
  if(!rows.length)root.textContent="No downloads queued.";
}

async function renderJobs(){
  const jobs=await api("/api/admin/jobs");
  const parent=$("jobs");
  const signature=JSON.stringify(jobs.map(j=>[j.id,j.state]));
  const changed=signature!==jobSignature;
  jobSignature=signature;
  pending=new Set(jobs.filter(j=>["queued","running"].includes(j.state)).map(j=>j.module));
  const open=new Set([...parent.querySelectorAll("details[open]")].map(d=>d.dataset.job));
  parent.replaceChildren();
  if(!jobs.length){parent.textContent="No installation activity yet.";return changed;}
  for(const job of jobs.slice(0,8)){
    const row=document.createElement("article");
    const title=document.createElement("strong");title.textContent=job.module+" · "+job.action+" · "+job.state;row.append(title);
    const stage=document.createElement("p");stage.textContent=job.stage;row.append(stage);
    if(job.total){const progress=document.createElement("progress");progress.max=job.total;progress.value=job.completed;progress.setAttribute("aria-label","Completed installation stages");row.append(progress);}
    const details=document.createElement("details");details.dataset.job=String(job.id);details.open=open.has(String(job.id));const summary=document.createElement("summary");summary.textContent="Docker output";const pre=document.createElement("pre");pre.textContent=job.log;details.append(summary,pre);row.append(details);parent.append(row);
  }
  return changed;
}
let polling=false;
const refreshModules=document.createElement("button");refreshModules.textContent="Refresh applications";refreshModules.addEventListener("click",()=>renderModules().catch(e=>error(e.message)));$("catalog").before(refreshModules);
setInterval(async()=>{
  if(polling||!status?.admin||$("dashboard").hidden)return;
  polling=true;
  try{if(await renderJobs())await renderModules();await renderDownloads();}catch(e){error(e.message);}finally{polling=false;}
},2000);

for(const [id,path] of [["setup-form","/api/setup"],["login-form","/api/login"]]){
  $(id).addEventListener("submit",async event=>{
    event.preventDefault();error("");
    const form=event.currentTarget,button=form.querySelector("button");button.disabled=true;
    try{await api(path,Object.fromEntries(new FormData(form)));form.reset();await refresh();}
    catch(e){error(e.message);}finally{button.disabled=false;}
  });
}
$("auth").addEventListener("click",async()=>{
  error("");
  try{if(status.admin){await api("/api/logout",{});await refresh();}else view("login");}
  catch(e){error(e.message);}
});
$("cancel").addEventListener("click",()=>{error("");view("dashboard");});


let directory={households:[],locations:[]};
function option(select,value,label){
  const node=document.createElement("option");node.value=value;node.textContent=label;select.append(node);
}
function householdOptions(select,first,previous){
  select.replaceChildren();option(select,"",first);
  for(const h of directory.households)option(select,String(h.id),h.name);
  select.value=[...select.options].some(o=>o.value===previous)?previous:"";
}
function directoryButton(parent,label,handler){
  const button=document.createElement("button");button.type="button";button.textContent=label;
  button.addEventListener("click",async()=>{try{await handler();}catch(e){$("household-message").textContent=e.message;}});
  parent.append(button);
}
async function changeDirectory(path,payload){
  await api("/api/admin/households"+path,payload);
  $("household-message").textContent="Saved.";
  await refreshHouseholds();
}
function renderDirectory(){
  const filter=$("household-filter").value;
  const admin=!!status?.admin;
  $("household-editor").hidden=!admin;
  if(!admin){$("household-form").reset();$("location-form").reset();$("household-message").textContent="";}
  const root=$("household-list");root.replaceChildren();
  for(const h of directory.households){
    if(filter&&String(h.id)!==filter)continue;
    const card=document.createElement("article"),title=document.createElement("strong"),summary=document.createElement("p");
    title.textContent=h.name;
    const owned=directory.locations.filter(l=>l.owner_id===h.id).length;
    const stored=directory.locations.filter(l=>l.storage_id===h.id).length;
    summary.textContent=owned+" owned location references · "+stored+" storage location references (not item counts)";
    card.append(title,summary);
    if(admin){
      directoryButton(card,"Edit",()=>{const form=$("household-form");form.elements.id.value=h.id;form.elements.name.value=h.name;form.scrollIntoView();});
      directoryButton(card,"Delete",async()=>{if(confirm("Delete this household? Remove or reassign its location references first."))await changeDirectory("/delete",{id:h.id});});
    }
    root.append(card);
  }
  if(!directory.households.length)root.textContent="No households configured yet.";
  const locations=$("location-list");locations.replaceChildren();
  for(const l of directory.locations){
    if(filter&&String(l.owner_id)!==filter&&String(l.storage_id)!==filter)continue;
    const card=document.createElement("article"),title=document.createElement("strong"),detail=document.createElement("p"),ref=document.createElement("small");
    title.textContent=l.label+" · "+l.module;
    detail.textContent="Ownership: "+(l.owner_name||"Shared / unassigned")+" · Stored at: "+(l.storage_name||"Shared / unassigned");
    ref.textContent="Native location ID: "+l.native_id;card.append(title,detail,ref);
    if(admin){
      directoryButton(card,"Edit reference",()=>{const form=$("location-form");for(const key of ["id","module","native_id","label","owner_id","storage_id"])form.elements[key].value=l[key]??"";form.scrollIntoView();});
      directoryButton(card,"Remove reference",async()=>{if(confirm("Remove this AfterGrid reference only? Native inventory is not changed."))await changeDirectory("/locations/delete",{id:l.id});});
    }
    locations.append(card);
  }
  if(!locations.children.length)locations.textContent="No mapped locations for this view.";
}
async function refreshHouseholds(){
  directory=await api("/api/households");
  const filter=$("household-filter");
  householdOptions(filter,"All households",filter.value);
  for(const key of ["owner_id","storage_id"]){
    const select=$("location-form").elements[key];householdOptions(select,"Shared / unassigned",select.value);
  }
  renderDirectory();
}
$("household-filter").addEventListener("change",renderDirectory);
$("household-refresh").addEventListener("click",()=>refreshHouseholds().catch(e=>{$("household-message").textContent=e.message;}));
$("household-reset").addEventListener("click",()=>$("household-form").reset());
$("location-reset").addEventListener("click",()=>$("location-form").reset());
$("household-form").addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget;const v=Object.fromEntries(new FormData(form));
  try{await changeDirectory("",{id:v.id?Number(v.id):null,name:v.name});form.reset();}catch(e){$("household-message").textContent=e.message;}
});
$("location-form").addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget;const v=Object.fromEntries(new FormData(form));
  for(const key of ["id","owner_id","storage_id"])v[key]=v[key]?Number(v[key]):null;
  try{await changeDirectory("/locations",v);form.reset();}catch(e){$("household-message").textContent=e.message;}
});

refresh().catch(e=>error(e.message));
