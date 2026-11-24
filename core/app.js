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
  if(!status.admin){pending.clear();jobSignature="";$("jobs").replaceChildren();}
  view(status.setup_required?"setup":"dashboard");
  if(!status.setup_required){
    if(status.admin)await renderJobs();
    await renderModules();
  }
}
async function renderModules(){
    const modules=await api("/api/modules");
    $("catalog").replaceChildren();
    for(const mod of modules){
      const card=document.createElement("article");
      for(const [tag,value] of [["small",mod.category],["h3",mod.name],["p",mod.description],["small",mod.status]]){
        const node=document.createElement(tag);node.textContent=value;card.append(node);
      }
      if(mod.installable && mod.status==="running" && (!mod.admin_only||status.admin) && (!mod.loopback_only||["127.0.0.1","localhost"].includes(location.hostname))){
        const link=document.createElement("a");
        const url=new URL(location.href);if(mod.loopback_only)url.protocol="http:";url.port=mod.port;url.pathname="/";url.search="";url.hash="";
        link.href=url.href;link.textContent="Open application";link.target="_blank";link.rel="noopener noreferrer";card.append(link);
      }
      if(status.admin && mod.installable){
        if(mod.setup_note){const note=document.createElement("p");note.textContent=mod.setup_note;card.append(note);}
        if(mod.loopback_only && !["127.0.0.1","localhost"].includes(location.hostname)){
          const note=document.createElement("small");note.textContent="Local setup only. SSH forward port "+mod.port+" and open http://127.0.0.1:"+mod.port;card.append(note);
        }
        if(mod.id==="kopia" && mod.status==="running"){
          const reveal=document.createElement("button");reveal.textContent="Show backup credentials";
          const credentials=document.createElement("pre");credentials.hidden=true;
          reveal.addEventListener("click",async()=>{
            if(!credentials.hidden){credentials.textContent="";credentials.hidden=true;reveal.textContent="Show backup credentials";return;}
            try{const c=await api("/api/admin/kopia/credentials");credentials.textContent="Username: "+c.username+"\nUI password: "+c.ui_password+"\nRepository password: "+c.repository_password;credentials.hidden=false;reveal.textContent="Hide credentials";}
            catch(e){error(e.message);}
          });card.append(reveal,credentials);
        }
        const actions=mod.status==="not installed"?["install"]:mod.status==="running"?["stop","restart","update","uninstall"]:["start","install","stop","uninstall"];
        const controls=document.createElement("div");controls.className="controls";
        for(const action of actions){
          const b=document.createElement("button");b.textContent=action;b.addEventListener("click",async()=>{
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
  try{if(await renderJobs())await renderModules();}catch(e){error(e.message);}finally{polling=false;}
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
refresh().catch(e=>error(e.message));

