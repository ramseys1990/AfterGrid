"use strict";
const $ = id => document.getElementById(id);
let status;
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
  view(status.setup_required?"setup":"dashboard");
  if(!status.setup_required){
    const modules=await api("/api/modules");
    $("catalog").replaceChildren();
    for(const mod of modules){
      const card=document.createElement("article");
      for(const [tag,value] of [["small",mod.category],["h3",mod.name],["p",mod.description],["small","Planned"]]){
        const node=document.createElement(tag);node.textContent=value;card.append(node);
      }
      $("catalog").append(card);
    }
  }
}
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
