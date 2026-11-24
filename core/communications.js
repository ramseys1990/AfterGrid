"use strict";
(()=>{
  const $=id=>document.getElementById(id);
  let canEdit=false;
  async function api(path,body){
    const r=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Request failed");return data;
  }
  function add(root,tag,value){const n=document.createElement(tag);n.textContent=value;root.append(n);return n;}
  function button(root,label,fn){const b=add(root,"button",label);b.type="button";b.addEventListener("click",()=>Promise.resolve().then(fn).catch(e=>$("message").textContent=e.message));}
  function edit(kind,record){const f=$(kind);for(const [key,value] of Object.entries({...record,...(record.steps||{})})){if(f.elements.namedItem(key))f.elements.namedItem(key).value=value??"";}f.scrollIntoView({block:"start"});}
  async function remove(kind,id){if(confirm("Delete this shared "+kind+"?")){await api("/api/admin/communications/delete",{kind,id});await refresh();}}
  async function refresh(){
    const status=await api("/api/status");
    canEdit=!!status.admin;$("plan").hidden=!canEdit;$("device").hidden=!canEdit;
    if(!canEdit){$("plan").reset();$("device").reset();}
    for(const id of ["services","devices","plans"])$(id).replaceChildren();
    if(status.setup_required){$("message").textContent="Complete initial setup in the portal.";return;}
    const [modules,data]=await Promise.all([api("/api/modules"),api("/api/communications")]);
    for(const id of ["meshmonitor","tak"]){
      const m=modules.find(x=>x.id===id),card=document.createElement("article");
      add(card,"h3",m?.name||id);add(card,"p","Server: "+(m?.status||"unavailable"));
      if(m?.status==="running"&&m.shared&&m.lan_url){
        if(id==="meshmonitor"){const link=add(card,"a","Open native MeshMonitor");link.href=m.lan_url;link.rel="noopener noreferrer";}
        else{const host=new URL(m.lan_url).hostname;add(card,"p",host+":8446 enrollment TLS · :8443 Marti mTLS · :8089 CoT mTLS");}
      }else add(card,"p","Not shared on LAN or not running. Manage from the portal.");
      add(card,"small","Device connectivity: not measured here");$("services").append(card);
    }
    for(const p of data.plans){
      const card=document.createElement("article");add(card,"h3",p.name);add(card,"p",p.scope||"Shared plan");
      for(const level of ["primary","alternate","contingency","emergency"]){add(card,"h4",level.toUpperCase());add(card,"p",p.steps[level]);}
      add(card,"small","Updated "+new Date(p.updated*1000).toLocaleString());
      if(canEdit){button(card,"Edit",()=>edit("plan",p));button(card,"Delete",()=>remove("plan",p.id));}$("plans").append(card);
    }
    for(const d of data.devices){
      const card=document.createElement("article");add(card,"h3",d.label);add(card,"p",[d.method,d.assigned,d.callsign].filter(Boolean).join(" · "));add(card,"p",d.notes);
      add(card,"small",d.checked?"Manually checked "+new Date(d.checked*1000).toLocaleString():"Not manually checked");
      if(canEdit){button(card,"Edit",()=>edit("device",d));button(card,"Record manual check",async()=>{if(confirm("Confirm you have actually checked this device outside AfterGrid?")){await api("/api/admin/communications/checked",{id:d.id});await refresh();}});button(card,"Delete",()=>remove("device",d.id));}$("devices").append(card);
    }
    if(!data.plans.length)add($("plans"),"p","No shared PACE plans.");
    if(!data.devices.length)add($("devices"),"p","No registered devices.");
    $("message").textContent="Updated from local server.";
  }
  for(const kind of ["plan","device"]){
    $(kind).addEventListener("submit",async event=>{
      event.preventDefault();const f=event.currentTarget,data=Object.fromEntries(new FormData(f));
      if(data.id)data.id=Number(data.id);else delete data.id;
      try{await api("/api/admin/communications/"+kind,data);f.reset();await refresh();}catch(e){$("message").textContent=e.message;}
    });
  }
  $("refresh").addEventListener("click",()=>refresh().catch(e=>$("message").textContent=e.message));
  refresh().catch(e=>$("message").textContent=e.message);
})();
