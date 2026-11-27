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
  if(!status.admin){$("core-update-result").textContent="Not checked.";$("update-health-result").replaceChildren();$("backup-health-result").replaceChildren();$("kopia-repository-result").textContent="";$("kopia-initialize").disabled=true;$("backup-policy-source").replaceChildren();$("backup-policy-source").disabled=true;$("backup-policy-check").disabled=true;$("backup-policy-result").replaceChildren();$("backup-retention-controls").replaceChildren();$("backup-schedule-source").replaceChildren();$("backup-schedule-source").disabled=true;$("backup-schedule-interval").disabled=true;$("backup-schedule-enable").disabled=true;$("backup-schedule-disable").disabled=true;$("backup-protected-create").disabled=true;$("backup-schedule-result").replaceChildren();$("backup-core-result").replaceChildren();pending.clear();jobSignature="";$("jobs").replaceChildren();$("installation-summary").replaceChildren();$("local-inventory").replaceChildren();$("content-results").replaceChildren();$("downloads").replaceChildren();$("map-status").replaceChildren();$("map-download").hidden=true;$("routing-status").replaceChildren();$("routing-graph-controls").replaceChildren();$("routing-download").hidden=true;$("content-message").textContent="";}
  view(status.setup_required?"setup":"dashboard");
  if(!status.setup_required){
    if(status.admin){refreshCoreUpdate().catch(()=>{});await renderJobs();await renderInstallationSummary();refreshLocalContent().catch(e=>{$("local-inventory").textContent=e.message;});}
    await renderModules();
    await refreshPreparedness();
    await refreshHouseholds();
  }
}
async function renderModules(){
    const modules=await api("/api/modules");
    if(status.admin && status.selection_pending)renderWizard(modules);
    $("catalog").replaceChildren();
    renderPreparednessApps(modules);
    for(const mod of modules){
      const card=document.createElement("article");card.id="app-"+mod.id;
      for(const [tag,value] of [["small",mod.category],["h3",mod.name],["p",mod.description],["small",mod.status]]){
        const node=document.createElement(tag);node.textContent=value;card.append(node);
      }
      if(mod.installable && mod.status==="running" && (!mod.admin_only||status.admin) && (!mod.loopback_only||(mod.shared&&mod.lan_url)||["127.0.0.1","localhost"].includes(location.hostname))){
        if(mod.id==="tak"){
          const host=mod.shared&&mod.lan_url?new URL(mod.lan_url).hostname:"127.0.0.1";
          const note=document.createElement("p");note.textContent="Native TAK client endpoints: "+host+":8446 (enrollment TLS), "+host+":8443 (Marti mTLS), "+host+":8089 (CoT mTLS). Import the trusted CA and enroll a client first.";card.append(note);
        }else{
          const link=document.createElement("a");
          const url=new URL(mod.shared&&mod.lan_url?mod.lan_url:location.href);if(mod.loopback_only)url.protocol="http:";url.port=mod.port;url.pathname="/";url.search="";url.hash="";
          link.href=mod.id==="routing"?"/maps":url.href;link.textContent=mod.id==="routing"?"Open route planner":mod.id==="maps"?"Open native tile viewer":"Open application";link.target="_blank";link.rel="noopener noreferrer";card.append(link);
        }
        if(mod.id==="maps"){const styled=document.createElement("a");styled.href="/maps";styled.textContent="Open styled offline map";card.append(styled);}
      }
      if(status.admin && mod.installable){
        if(mod.setup_note){const note=document.createElement("p");note.textContent=mod.setup_note;card.append(note);}
        if(["homebox","grocy","media","kolibri","notes"].includes(mod.id) && mod.status==="running" && !mod.shared){
          const setup=document.createElement("a");setup.href="/native-setup/"+mod.id;setup.textContent="Set up native account";card.append(setup);
        }
        if(mod.loopback_only && !mod.shared && !["homebox","grocy","media","kolibri","notes"].includes(mod.id) && !["127.0.0.1","localhost"].includes(location.hostname)){
          const note=document.createElement("small");note.textContent=mod.id==="tak"?"Local setup only. Use the native admin CLI over SSH forwards for 8446 and 8443, with the trusted CA.":mod.id==="kolibri"?"Local setup only. Forward both 8086 and 8087 over SSH; open http://127.0.0.1:8086.":"Local setup only. SSH forward port "+mod.port+" and open http://127.0.0.1:"+mod.port;card.append(note);
        }
        if(mod.id==="meshmonitor" && mod.status==="running"){
          const reveal=document.createElement("button");reveal.textContent="Show initial MeshMonitor credentials";
          const credentials=document.createElement("pre");credentials.hidden=true;
          reveal.addEventListener("click",async()=>{
            if(!credentials.hidden){credentials.textContent="";credentials.hidden=true;reveal.textContent="Show initial MeshMonitor credentials";return;}
            if(location.protocol!=="https:"&&!["127.0.0.1","localhost"].includes(location.hostname)&&!confirm("Initial credentials will travel over unencrypted HTTP. Continue only on a trusted LAN?"))return;
            try{const c=await api("/api/admin/meshmonitor/credentials",{});credentials.textContent="Username: "+c.username+"\nInitial password: "+c.initial_password+"\nIf changed in MeshMonitor, use your new password.";credentials.hidden=false;reveal.textContent="Hide credentials";}catch(e){error(e.message);}
          });card.append(reveal,credentials);
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
        const actions=mod.status==="not installed"?["install"]:mod.status==="running"?["stop","restart",...(mod.id==="routing"?[]:["update"]),"uninstall"]:["start","install","stop","uninstall"];
        const backup=document.createElement("details"),backupTitle=document.createElement("summary");
        backupTitle.textContent="Backup source plan";
        const backupButton=document.createElement("button"),backupInfo=document.createElement("div");
        backupButton.type="button";backupButton.textContent="Read backup sources";
        backupButton.addEventListener("click",async()=>{
          backupButton.disabled=true;backupInfo.textContent="Reading reviewed Compose mounts…";
          try{
            const plan=await api("/api/admin/modules/"+mod.id+"/backup-plan");
            if(!status?.admin||!card.isConnected)return;
            backupInfo.replaceChildren();
            function line(value){const p=document.createElement("p");p.textContent=value;backupInfo.append(p);}
            line("Source plan only — no verified snapshot.");
            line(plan.guidance);
            for(const source of plan.sources)line(source.role+" · "+(source.kopia_path||"not included in native source plan")+" (container: "+source.container_path+")");
            if(plan.worker_secrets_required)line("Worker-generated secrets must be included separately for exact recovery; not visible in Kopia.");
          }catch(e){if(status?.admin&&card.isConnected)backupInfo.textContent=e.message;}
          finally{backupButton.disabled=false;}
        });
        backup.append(backupTitle,backupButton,backupInfo);
        if(["grocy","homebox","notes","meshmonitor","tak","kolibri","media"].includes(mod.id)&&["running","stopped"].includes(mod.status)){
          const snapshot=document.createElement("button");snapshot.type="button";snapshot.textContent="Create consistent snapshot";
          snapshot.disabled=pending.has(mod.id);
          snapshot.addEventListener("click",async()=>{
            if(!confirm("Temporarily stop "+mod.name+" if running, create a Kopia snapshot, then restore its prior state. Confirm Kopia is connected, no other backups or native administration are active and no one is editing application files. This does not verify a restore or separate worker secrets. Continue?"))return;
            snapshot.disabled=true;
            try{await api("/api/admin/modules/"+mod.id+"/snapshot",{confirmed:true});await renderJobs();await renderModules();}
            catch(e){error(e.message);snapshot.disabled=false;}
          });backup.append(snapshot);
        }
        if(["grocy","homebox","notes","meshmonitor","tak","kolibri","media"].includes(mod.id)){
          const verify=document.createElement("button");verify.type="button";verify.textContent="Verify latest managed snapshot";
          verify.disabled=pending.has(mod.id);
          verify.addEventListener("click",async()=>{
            if(!confirm("Restore the latest successful managed "+mod.name+" snapshot into a NEW private directory under /restore, then check application data. Live files are not replaced. Confirm space is available and no native backup administration is active. Restored files remain on disk for review. Continue?"))return;
            verify.disabled=true;
            try{await api("/api/admin/modules/"+mod.id+"/verify-snapshot",{confirmed:true});await renderJobs();await renderModules();}
            catch(e){error(e.message);verify.disabled=false;}
          });backup.append(verify);
        }
        if(["kiwix","maps","routing","media"].includes(mod.id)){
          for(const [action,label] of [["snapshot","Snapshot offline content"],["verify","Read-verify latest content snapshot"]]){
            const b=document.createElement("button");b.type="button";b.textContent=label;b.disabled=pending.has(mod.id);
            b.addEventListener("click",async()=>{
              const message=action==="snapshot"?"Finish all downloads, graph operations and external imports. AfterGrid pauses new managed content changes during snapshot, but external writes are not blocked. Large snapshots can take hours. Continue?":"Read every file from the latest managed content snapshot using Kopia. This may take hours and does not restore files or prove native startup. Continue?";
              if(!confirm(message))return;
              b.disabled=true;
              try{await api("/api/admin/backups/content/"+mod.id+"/"+action,{confirmed:true});await renderJobs();await renderModules();}
              catch(e){error(e.message);b.disabled=false;}
            });backup.append(b);
          }
        }
        card.append(backup);
        const versions=document.createElement("details");
        const summary=document.createElement("summary");summary.textContent="Image versions and update history";
        const info=document.createElement("div"),check=document.createElement("button");check.type="button";check.textContent="Read local versions";
        check.addEventListener("click",async()=>{
          check.disabled=true;info.textContent="Reading local Docker image information…";
          try{
            const result=await api("/api/admin/modules/"+mod.id+"/versions");
            if(!status?.admin||!card.isConnected)return;
            info.replaceChildren();
            for(const service of result.services){
              const section=document.createElement("div");
              for(const value of [service.service+" — "+service.comparison,"Reviewed target: "+service.configured_image,"Installed image IDs: "+(service.installed_image_ids.join(", ")||"none"),"Local target ID: "+(service.local_target_image_id||"not present or unknown")]){
                const p=document.createElement("p");p.textContent=value;section.append(p);
              }
              info.append(section);
            }
            const note=document.createElement("p");note.textContent="Local comparison only. No registry check. A matching image does not prove the latest upstream version.";info.append(note);
            if(!result.manual_update_supported){const n=document.createElement("p");n.textContent="Routing image updates are deferred until graph compatibility and recovery are validated.";info.append(n);}
            for(const entry of result.history){const p=document.createElement("p");p.textContent="Update #"+entry.id+" · "+new Date(entry.created*1000).toLocaleString()+" · "+entry.state+" · "+entry.stage;info.append(p);}
          }catch(e){if(status?.admin&&card.isConnected)info.textContent=e.message;}
          finally{check.disabled=false;}
        });
        const registry=document.createElement("button");registry.type="button";registry.textContent="Check configured registry image (internet)";
        const registryInfo=document.createElement("div");
        registry.addEventListener("click",async()=>{
          if(!confirm("Contact the image registry for this reviewed reference? No image layers will be downloaded or containers changed."))return;
          registry.disabled=true;registryInfo.textContent="Reading registry metadata…";
          try{
            const result=await api("/api/admin/modules/"+mod.id+"/registry-check",{});
            if(!status?.admin||!card.isConnected)return;
            registryInfo.replaceChildren();
            for(const value of [result.comparison,"Configured reference: "+result.configured_image,
              "Docker platform: "+(result.platform||"unknown"),"Remote image config digest: "+(result.registry_config_digest||"unknown"),
              "Checked: "+new Date(result.checked_at*1000).toLocaleString(),
              result.digest_pinned?"Digest-pinned reference: a newer release requires a reviewed configuration change.":"Checks the configured tag only, not newer upstream release tags.",
              result.detail||"Different digests do not prove a newer or compatible release."]){
              const p=document.createElement("p");p.textContent=value;registryInfo.append(p);
            }
          }catch(e){if(status?.admin&&card.isConnected)registryInfo.textContent=e.message;}
          finally{registry.disabled=false;}
        });
        versions.append(summary,check,info,registry,registryInfo);
        if(mod.id==="kiwix"){
          const eligibility=document.createElement("div"),localButton=document.createElement("button"),onlineButton=document.createElement("button");
          localButton.type=onlineButton.type="button";
          localButton.textContent="Review guarded update eligibility";
          onlineButton.textContent="Confirm approved candidate with registry (internet)";
          async function readEligibility(online){
            if(online&&!confirm("Check the approved candidate's registry identity? No image layers are downloaded or containers changed."))return;
            localButton.disabled=onlineButton.disabled=true;eligibility.textContent="Checking eligibility…";
            try{
              const r=await api("/api/admin/modules/kiwix/update-eligibility",online?{}:undefined);
              if(!status?.admin||!card.isConnected)return;
              eligibility.replaceChildren();
              for(const value of [r.status,"Approved target: "+(r.candidate||"none"),"Registry checked: "+(r.registry_checked?"yes":"no"),...(r.blockers||[]),"Advisory only. No automatic update execution enabled."]){
                const p=document.createElement("p");p.textContent=value;eligibility.append(p);
              }
              if(online&&r.status==="reviewed candidate confirmed"){
                const prep=document.createElement("button");prep.type="button";prep.textContent="Prepare protected pre-update backup";
                const guarded=document.createElement("button");guarded.type="button";guarded.textContent="Run guarded approved update";
                eligibility.append(prep,guarded);
                guarded.addEventListener("click",async()=>{
                  if(!confirm("Run the reviewed Kiwix update? A fresh pinned backup, full content verification and prior image archive must succeed first. The reader may be interrupted. If recreation fails, AfterGrid attempts image-only local reader recovery. The update remains failed and paused for review."))return;
                  guarded.disabled=prep.disabled=true;
                  try{
                    const job=await api("/api/admin/modules/kiwix/guarded-update",{candidate:r.candidate,platform:r.platform,previous_image_id:r.installed_image_ids[0],target_image_id:r.expected_target_image_id,confirmed:true});
                    if(status?.admin&&card.isConnected){eligibility.textContent="Guarded update job "+job.id+" queued. Check installation activity.";await renderJobs();}
                  }catch(e){if(status?.admin&&card.isConnected)eligibility.textContent=e.message;}
                  finally{guarded.disabled=prep.disabled=false;}
                });
                prep.addEventListener("click",async()=>{
                  if(!confirm("Create a new pinned Kiwix snapshot and read every file? Content operations are paused during preparation. This may take hours and consume storage. No update will be installed."))return;
                  prep.disabled=true;
                  try{
                    const job=await api("/api/admin/modules/kiwix/update-preparation",{candidate:r.candidate,platform:r.platform,previous_image_id:r.installed_image_ids[0],target_image_id:r.expected_target_image_id,confirmed:true});
                    if(status?.admin&&card.isConnected){eligibility.textContent="Preparation job "+job.id+" queued. Check installation activity.";await renderJobs();}
                  }catch(e){if(status?.admin&&card.isConnected)eligibility.textContent=e.message;}
                  finally{prep.disabled=false;}
                });
              }
              const history=await api("/api/admin/modules/kiwix/update-preparation");
              if(!status?.admin||!card.isConnected)return;
              if(history.latest){
                const p=document.createElement("p"),h=history.latest;
                p.textContent="Latest "+(h.action||"preparation")+": job "+h.job+" · "+h.state+(h.evidence?" · protected snapshot "+h.evidence.snapshot_id+" · exact content read passed"+(h.evidence.previous_image_archive?" · previous image archive recorded":"")+(h.state==="succeeded"&&h.evidence.update_performed?" · target identity and catalog verified":h.evidence.rollback_status==="restored"?" · previous reader restored; update paused":h.evidence.rollback_status?" · rollback "+h.evidence.rollback_status+"; inspect outcome":h.evidence.recreation_attempted?" · recreation attempted; inspect outcome":" · no recreation recorded"):"");
                eligibility.append(p);
              }
            }catch(e){if(status?.admin&&card.isConnected)eligibility.textContent=e.message;}
            finally{localButton.disabled=onlineButton.disabled=false;}
          }
          localButton.addEventListener("click",()=>readEligibility(false));
          onlineButton.addEventListener("click",()=>readEligibility(true));
          const preferences=document.createElement("div"),prefButton=document.createElement("button");
          prefButton.type="button";prefButton.textContent="Configure future automatic update preference";
          async function readPreferences(){
            prefButton.disabled=true;preferences.textContent="Reading update preferences…";
            try{
              const report=await api("/api/admin/modules/kiwix/update-preferences");
              if(!status?.admin||!card.isConnected)return;
              preferences.replaceChildren();
              const note=document.createElement("p");
              note.textContent="Preferences only. Automatic execution is disabled; separate activation will be required after acceptance. Window uses UTC and controls admission, not guaranteed completion.";
              preferences.append(note);
              const row=report.preference||{enabled:false,weekday:6,start_minute:120,duration_minutes:120};
              function control(label,input){
                const wrap=document.createElement("label");wrap.textContent=label+" ";wrap.append(input);preferences.append(wrap);
              }
              const enabled=document.createElement("input");enabled.type="checkbox";enabled.checked=row.enabled;
              control("Request future automatic updates",enabled);
              const weekday=document.createElement("select");
              ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].forEach((day,i)=>{const opt=document.createElement("option");opt.value=i;opt.textContent=day;weekday.append(opt);});
              weekday.value=row.weekday;control("Day (UTC)",weekday);
              const start=document.createElement("input");start.type="time";start.required=true;
              start.value=String(Math.floor(row.start_minute/60)).padStart(2,"0")+":"+String(row.start_minute%60).padStart(2,"0");
              control("Start (UTC)",start);
              const duration=document.createElement("input");duration.type="number";duration.min=30;duration.max=360;duration.step=1;duration.required=true;duration.value=row.duration_minutes;
              control("Duration (minutes)",duration);
              const save=document.createElement("button");save.type="button";save.textContent="Save preference";save.disabled=report.recovery_mode===true;preferences.append(save);
              const message=document.createElement("p");preferences.append(message);
              if(report.window_open)message.textContent="Window open until "+new Date(report.current_window_end*1000).toISOString()+". Execution disabled.";
              else if(report.next_window_start!==null)message.textContent="Next window: "+new Date(report.next_window_start*1000).toISOString()+". Execution disabled.";
              save.addEventListener("click",async()=>{
                if(!start.checkValidity()||!duration.checkValidity())return;
                const parts=start.value.split(":").map(Number),minute=parts[0]*60+parts[1];
                if(minute+duration.valueAsNumber>1440){message.textContent="Window must end on the same UTC day.";return;}
                if(!confirm("Save this preference only? No automatic update will run until separately activated after acceptance."))return;
                save.disabled=true;
                try{
                  await api("/api/admin/modules/kiwix/update-preferences",{enabled:enabled.checked,weekday:Number(weekday.value),start_minute:minute,duration_minutes:duration.valueAsNumber,confirmed:true});
                  if(status?.admin&&card.isConnected)await readPreferences();
                }catch(e){if(status?.admin&&card.isConnected)message.textContent=e.message;}
                finally{save.disabled=false;}
              });
            }catch(e){if(status?.admin&&card.isConnected)preferences.textContent=e.message;}
            finally{prefButton.disabled=false;}
          }
          prefButton.addEventListener("click",readPreferences);
          versions.append(localButton,onlineButton,eligibility,prefButton,preferences);
        }
        card.append(versions);
        if(mod.shared && mod.lan_url){
          const note=document.createElement("p");note.textContent="LAN URL: "+mod.lan_url+(mod.lan_dns?" — local DNS must point to the server.":" — reserve the server IP for stable links.")+(mod.id==="tak"?" TLS; enroll with the trusted CA.":" HTTP is unencrypted.");card.append(note);
        }else if(mod.share_available){
          const note=document.createElement("p");note.textContent=(mod.lan_dns?"Add a local DNS record for "+new URL(mod.lan_url).hostname+". ":"")+"Complete native account setup before sharing. LAN URL: "+mod.lan_url;card.append(note);
        }else if(["homebox","grocy","kopia","meshmonitor","tak","kolibri","media","notes"].includes(mod.id)){
          const note=document.createElement("small");note.textContent="LAN sharing needs a private LAN bind configured on the server; see the LAN setup guide.";card.append(note);
        }
        if(mod.shared && mod.status!=="not installed")actions.push("unshare");
        else if(mod.share_available&&mod.status==="running")actions.push("share");
        const controls=document.createElement("div");controls.className="controls";
        for(const action of actions){
          const b=document.createElement("button");b.textContent=action==="share"?"Share on LAN":action==="unshare"?"Return to local-only":action;b.addEventListener("click",async()=>{
            if(action==="share"){
              const warning=mod.id==="homebox"?"Confirm you created your Homebox account. Sharing closes public registration.":mod.id==="grocy"?"Confirm you changed Grocy's default administrator password.":mod.id==="meshmonitor"?"MeshMonitor requires native login. Confirm native account setup and permissions. Keep the initial password private.":mod.id==="tak"?"Confirm native administrator enrollment and secure storage of the CA and credentials. Only authenticated TLS endpoints will be shared.":mod.id==="kolibri"?"Confirm Kolibri facility and administrator setup is complete and learner permissions are configured.":mod.id==="media"?"Confirm Jellyfin setup is complete, administrator password is set, remote access is disabled and local library permissions are configured.":mod.id==="notes"?"Confirm DokuWiki native setup is complete, ACLs are enabled, Closed Wiki is selected, public registration is disabled and users have appropriate access.":"Kopia uses its generated native administrator password. Keep it private.";
              if(!confirm(warning+" "+(mod.lan_dns?"Confirm local DNS is configured. ":"")+(mod.id==="tak"?"Continue only on a trusted LAN?":"LAN HTTP is unencrypted. Continue only on a trusted LAN?")))return;
            }
            if(action==="unshare"&&!confirm("Return to loopback-only access? This recreates and starts the application while keeping its data."))return;
            if(action==="uninstall"&&!confirm("Remove this application's containers? Its data will be retained."))return;
            if(action==="update"&&!confirm("Confirm you have a current application-consistent backup and can restore it. This pulls only the reviewed configured image, may interrupt service, and cannot automatically roll back data migrations. Continue?"))return;
            b.disabled=true;error("");
            try{await api("/api/admin/modules/"+mod.id+"/"+action,action==="update"?{backup_confirmed:true}:{});await renderJobs();await renderModules();}
            catch(e){error(e.message);}finally{b.disabled=false;}
          });b.disabled=pending.has(mod.id);controls.append(b);
        }
        card.append(controls);
      }
      $("catalog").append(card);
    }
}
async function refreshCoreUpdate(){
  const button=$("core-update-refresh"),result=$("core-update-result");
  button.disabled=true;
  try{
    const r=await api("/api/admin/core-update/status");
    if(!status?.admin)return;
    result.textContent=r.host_reconciliation_required
      ?"Update maintenance requires host reconciliation. Do not release maintenance or rebuild containers manually."
      :r.maintenance_active
        ?"Recovery maintenance is active. Core update activation is not released."
        :"Core update activation is not released. Your applications remain independently managed.";
  }catch(e){if(status?.admin)result.textContent="Core update status unavailable.";}
  finally{button.disabled=false;}
}
$("core-update-refresh").addEventListener("click",refreshCoreUpdate);
$("update-health-refresh").addEventListener("click",async()=>{
  const button=$("update-health-refresh"),root=$("update-health-result");
  button.disabled=true;root.textContent="Reading local update health…";
  try{
    const r=await api("/api/admin/updates/health");
    if(!status?.admin)return;
    root.replaceChildren();
    const line=(parent,value)=>{const p=document.createElement("p");p.textContent=value;parent.append(p);};
    const date=v=>Number.isFinite(v)?new Date(v*1000).toISOString():"not recorded";
    line(root,r.automatic_execution_enabled?"Automatic execution active for reviewed candidates.":"Automatic execution disabled; separate activation required.");
    line(root,"Reader: "+r.reader_state+" · Approved candidate: "+(r.approved_candidate||"none"));
    line(root,"Rollback hold: "+r.rollback_hold.status+(r.rollback_hold.image_id?" · "+r.rollback_hold.image_id:""));
    const resolution=r.rollback_resolution;
    if(resolution&&resolution.status!=="not applicable"){
      line(root,"Rollback resolution: "+resolution.status);
      if(resolution.clear_enabled){
        const resolve=document.createElement("button");resolve.textContent="Verify and resolve rollback hold";
        resolve.addEventListener("click",async()=>{
          if(!confirm("Reverify the exact archive, protected snapshot and catalog before removing the override? No image update or data restore will be performed."))return;
          resolve.disabled=true;
          try{const job=await api("/api/admin/modules/kiwix/resolve-rollback",{failed_job:resolution.failed_job,image_id:r.rollback_hold.image_id,confirmed:true});line(root,"Resolution queued · #"+job.id);}
          catch(e){line(root,e.message);resolve.disabled=false;}
        });root.append(resolve);
      }
      if(resolution.base_image)line(root,"Base Compose target: "+resolution.base_image+" · "+(resolution.base_matches_rollback?"matches recovered image locally":"not confirmed to match recovered image"));
      for(const blocker of resolution.blockers)line(root,"Resolution: "+blocker);
    }
    if(r.maintenance_active)line(root,"Recovery maintenance active.");
    if(r.recovery_mode)line(root,"Recovery mode restricts updates.");
    for(const blocker of r.blockers)line(root,"Review: "+blocker);
    for(const s of r.local_images||[]){
      line(root,"Effective local Compose target: "+s.configured_image);
      line(root,"Installed image: "+(s.installed_image_ids.join(", ")||"none"));
    }
    const pref=r.preferences;
    if(pref.dispatch)line(root,"Last scheduled admission: "+pref.dispatch.status+(pref.dispatch.job?" · #"+pref.dispatch.job:""));
    if(pref.release_enabled&&pref.preference?.enabled){
      const activate=document.createElement("button");activate.textContent=pref.execution_enabled?"Deactivate automatic updates":"Activate automatic updates";
      activate.addEventListener("click",async()=>{
        if(!confirm(pref.execution_enabled?"Disable future automatic admissions? Running jobs will continue.":"Allow reviewed Kiwix updates in the configured UTC window, with protected backup and rollback?"))return;
        activate.disabled=true;
        try{await api("/api/admin/modules/kiwix/update-activation",{enabled:!pref.execution_enabled,confirmed:true});button.click();}
        catch(e){line(root,e.message);activate.disabled=false;}
      });root.append(activate);
    }
    if(pref.preference?.enabled){
      const p=pref.preference,days=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
      line(root,"Future update preference: "+days[p.weekday]+" "+String(Math.floor(p.start_minute/60)).padStart(2,"0")+":"+String(p.start_minute%60).padStart(2,"0")+" UTC · "+p.duration_minutes+" min");
      line(root,pref.window_open?"Window open until "+date(pref.current_window_end):"Next window: "+date(pref.next_window_start));
    }else line(root,"Future automatic update preference: disabled");
    for(const [name,attempt] of [["Latest guarded update",r.latest_guarded_update],["Latest preparation",r.latest_preparation],["Latest manual update",r.latest_manual_update]]){
      const details=document.createElement("details"),summary=document.createElement("summary");
      summary.textContent=name+": "+(attempt?attempt.state+" · #"+attempt.id:"none recorded");
      details.append(summary);root.append(details);
      if(!attempt)continue;
      line(details,"Submitted "+date(attempt.created)+" · "+attempt.stage);
      if(attempt.evidence_invalid)line(details,"Recorded evidence invalid; inspect host.");
      const e=attempt.evidence;
      if(!e)continue;
      if(e.snapshot_id)line(details,"Recorded pre-update snapshot: "+e.snapshot_id+" · "+e.verification+" verification · pin "+(e.pin_confirmed?"recorded":"unconfirmed"));
      if(e.previous_image_archive)line(details,"Previous archive: "+e.previous_image_archive.image_id+" · "+e.previous_image_archive.bytes+" bytes · checksum "+e.previous_image_archive.sha256);
      if(e.recreation_attempted)line(details,"Recreation attempted.");
      if(e.rollback_status)line(details,"Recorded rollback: "+e.rollback_status+" · "+(e.rollback_image_id||"identity not confirmed"));
      if(attempt.state==="succeeded"&&e.update_performed)line(details,"Result image "+e.result_image_id+" · catalog sample verified.");
      else if(attempt.action==="guarded-update"&&attempt.state!=="succeeded")line(details,"Update success not confirmed; inspect before further changes.");
    }
    line(root,"Recovery evidence is historical; archive and pin are not reverified on refresh. Use the Kiwix application card for explicit online checks and preferences.");
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-health-refresh").addEventListener("click",async()=>{
  const button=$("backup-health-refresh"),root=$("backup-health-result");
  button.disabled=true;root.textContent="Reading recorded backup health…";
  try{
    const report=await api("/api/admin/backups/health");
    if(!status?.admin)return;
    root.replaceChildren();
    const date=value=>Number.isFinite(value)?new Date(value*1000).toLocaleString():"not recorded";
    const line=(parent,text)=>{const p=document.createElement("p");p.textContent=text;parent.append(p);};
    const attempt=row=>row?row.state+" (job "+row.id+", submitted "+date(row.created)+")":"not recorded";
    line(root,"Repository connection: "+report.repository.connection+(report.repository.storage_type?" · "+report.repository.storage_type:""));
    line(root,"Inventory check: "+(report.inventory_job?"job "+report.inventory_job+" · "+date(report.inventory_checked_at):"not generated")+". Availability and pin observations are historical, not current.");
    const supported=report.sources.filter(s=>s.supported);
    const attention=supported.filter(s=>["failed","interrupted","unknown","dispatching"].includes(s.schedule.result)||[s.latest_attempt,s.latest_verification_attempt].some(a=>a&&["failed","interrupted"].includes(a.state))||s.repository_at_inventory==="unavailable");
    const due=supported.filter(s=>s.schedule.enabled&&s.schedule.next_due<=report.observed_at);
    line(root,supported.filter(s=>s.verified).length+" of "+supported.length+" reviewed sources have recorded verification of their latest successful capture. "+attention.length+" need review; "+due.length+" schedules due (may be deferred). Optional sources may not be installed.");
    if(report.maintenance_active||!report.managed_execution_enabled)line(root,"Managed scheduling deferred or disabled by recovery mode.");
    if(report.latest_retention_attempt)line(root,"Last retention operation: "+attempt(report.latest_retention_attempt));
    for(const s of report.sources){
      const details=document.createElement("details"),summary=document.createElement("summary");
      summary.textContent=s.key+" — "+(!s.supported?"excluded":attention.includes(s)?"review needed":s.verified?"verification recorded":s.snapshot_job?"not verified":"no recorded snapshot");
      details.append(summary);root.append(details);
      if(!s.supported){line(details,"MicroTAK data recovery excluded.");continue;}
      line(details,"Latest successful snapshot: "+(s.snapshot_job?"job "+s.snapshot_job+" · submitted "+date(s.captured_at):"none recorded"));
      line(details,"Latest snapshot attempt: "+attempt(s.latest_attempt));
      line(details,"Latest verification attempt: "+attempt(s.latest_verification_attempt));
      line(details,"Verification of latest successful snapshot: "+(s.verified?s.verification_kind+" · "+attempt(s.verified):"not recorded"));
      line(details,"Matching inventory: "+s.repository_at_inventory+"; pin "+(s.pin_at_inventory===true?"observed":s.pin_at_inventory===false?"not present":"not checked"));
      if(s.latest_protected_capture){const p=s.latest_protected_capture;line(details,"Latest protected capture: job "+p.job+" · "+date(p.created)+"; verification "+attempt(p.verification)+"; pin at inventory "+(p.pin_at_inventory===true?"observed":p.pin_at_inventory===false?"not present":"not checked"));}
      else line(details,"No successful protected capture recorded.");
      line(details,"Schedule: "+s.schedule.status+(s.schedule.enabled?" · "+s.schedule.interval+" · next eligible "+date(s.schedule.next_due):"")+(s.schedule.result?" · "+s.schedule.phase+" "+s.schedule.result:""));
    }
    line(root,"Generate a fresh recovery inventory below to recheck the exact latest snapshot IDs in Kopia. Keep an independent portable package.");
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("kopia-status-check").addEventListener("click",async()=>{
  const button=$("kopia-status-check"),create=$("kopia-initialize"),root=$("kopia-repository-result");
  button.disabled=true;create.disabled=true;root.textContent="Checking native Kopia…";
  try{
    const result=await api("/api/admin/kopia/status");
    if(!status?.admin)return;
    root.textContent="Repository: "+result.connection+(result.storage_type?" · "+result.storage_type:"")+". Snapshot and restore verification pending.";
    create.disabled=result.connection!=="not connected";
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-policy-sources").addEventListener("click",async()=>{
  const select=$("backup-policy-source"),root=$("backup-policy-result"),button=$("backup-policy-sources");
  button.disabled=true;select.disabled=true;$("backup-policy-check").disabled=true;select.replaceChildren();
  try{
    const keys=await api("/api/admin/backups/policy-sources");
    if(!status?.admin)return;
    for(const key of keys){const option=document.createElement("option");option.value=key;option.textContent=key;select.append(option);}
    if(keys.includes("global"))select.value="global";
    select.disabled=!keys.length;$("backup-policy-check").disabled=!keys.length;
    root.textContent="Select a reviewed source to inspect native policy.";
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-policy-source").addEventListener("change",()=>{$("backup-retention-controls").replaceChildren();$("backup-policy-result").textContent="Read effective policy for selected source.";});
$("backup-policy-check").addEventListener("click",async()=>{
  const root=$("backup-policy-result"),button=$("backup-policy-check"),select=$("backup-policy-source");
  button.disabled=true;select.disabled=true;$("backup-retention-controls").replaceChildren();root.textContent="Reading native effective policy…";
  try{
    const result=await api("/api/admin/backups/effective-policy/"+select.value.split("/").map(encodeURIComponent).join("/"));
    if(!status?.admin)return;
    root.replaceChildren();
    const line=text=>{const p=document.createElement("p");p.textContent=text;root.append(p);};
    const p=result.policy,s=p.schedule;
    line("Source: "+result.key+(result.source?" · "+result.source:""));
    line("Native scheduling policy: "+(s.manual?"manual only":s.automatic_policy?"automatic settings present":"no interval or time configured")+". Not proof that a native job is running or application-consistent.");
    if(s.interval_seconds)line("Interval: "+s.interval_seconds+" seconds");
    if(s.times_utc.length)line("Scheduled times (Kopia UTC): "+s.times_utc.join(", "));
    if(s.cron_count)line("Cron entries: "+s.cron_count+" (inspect native Kopia for expressions)");
    line("Retention: "+Object.entries(p.retention).map(([k,v])=>k.replace("keep","")+": "+(v===null?"not reported":v)).join(" · "));
    line("Use managed schedules separately. Retention affects unpinned backups; no global changes.");
    if(result.retention_changes_enabled && Object.values(p.retention).every(Number.isInteger)){
      const controls=$("backup-retention-controls"),fields={};
      for(const [key,value] of Object.entries(p.retention)){
        const label=document.createElement("label");label.textContent=key.replace("keep","")+" ";
        const input=document.createElement("input");input.type="number";input.min=key==="keepLatest"?"3":"0";input.max="3650";input.step="1";input.value=value;input.required=true;
        label.append(input);controls.append(label);fields[key]=input;
      }
      const apply=document.createElement("button");apply.type="button";apply.textContent="Queue retention change for "+result.key;controls.append(apply);
      apply.addEventListener("click",async()=>{
        if(select.value!==result.key){controls.replaceChildren();root.textContent="Reload policy for selected source.";return;}
        if(!Object.values(fields).every(input=>input.checkValidity())){root.textContent="Enter valid retention counts; keep at least three latest snapshots.";return;}
        if(!confirm("Change retention for "+result.key+"? Older unpinned snapshots may expire. Confirm a fresh verified protected snapshot and independent recovery package."))return;
        apply.disabled=true;
        try{
          const counts=Object.fromEntries(Object.entries(fields).map(([k,input])=>[k,input.valueAsNumber]));
          const job=await api("/api/admin/backups/retention",{key:result.key,expected:p.retention,counts,confirmed:true});
          if(status?.admin){controls.replaceChildren();root.textContent="Retention job "+job.id+" queued. Check activity and reload effective policy after completion.";await renderJobs();}
        }catch(e){if(status?.admin)root.textContent=e.message;}
        finally{apply.disabled=false;}
      });
    }
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{if(status?.admin){button.disabled=false;select.disabled=false;}}
});
async function loadBackupSchedules(){
  const root=$("backup-schedule-result"),select=$("backup-schedule-source");
  const previous=select.value;
  select.disabled=true;$("backup-schedule-interval").disabled=true;$("backup-schedule-enable").disabled=true;$("backup-schedule-disable").disabled=true;$("backup-protected-create").disabled=true;
  try{
    const result=await api("/api/admin/backups/schedules");
    if(!status?.admin)return;
    select.replaceChildren();root.replaceChildren();
    for(const key of result.available){
      const o=document.createElement("option");o.value=key;o.textContent=key;select.append(o);
    }
    if(result.available.includes(previous))select.value=previous;
    const line=text=>{const p=document.createElement("p");p.textContent=text;root.append(p);};
    for(const [key,row] of Object.entries(result.sources)){
      line(key+": "+(row.enabled?row.interval+" · next eligible "+new Date(row.next_due*1000).toLocaleString():"disabled")+" · "+row.phase+" "+row.result+(row.job?" (job "+row.job+")":"")+" · verification "+row.verification+(row.source_job?" (snapshot job "+row.source_job+")":""));
    }
    if(!Object.keys(result.sources).length)line("No schedules configured.");
    if(!result.execution_enabled)line("Managed schedules are disabled in recovery mode.");
    select.disabled=!result.execution_enabled;
    $("backup-schedule-interval").disabled=!result.execution_enabled;
    $("backup-schedule-enable").disabled=!result.execution_enabled;
    $("backup-schedule-disable").disabled=!result.execution_enabled;
    $("backup-protected-create").disabled=!result.execution_enabled;
  }catch(e){if(status?.admin)root.textContent=e.message;}
}
$("backup-schedule-load").addEventListener("click",loadBackupSchedules);
async function changeBackupSchedule(enabled){
  if(!confirm(enabled?"Enable this managed snapshot schedule? Application sources may be stopped and restarted. Confirm native raw scheduling is disabled and automatic verification can consume additional time and storage.":"Disable future scheduled snapshots? An existing job is not cancelled."))return;
  try{
    await api("/api/admin/backups/schedules",{key:$("backup-schedule-source").value,interval:$("backup-schedule-interval").value,enabled,confirmed:true});
    await loadBackupSchedules();
  }catch(e){if(status?.admin)$("backup-schedule-result").textContent=e.message;}
}
$("backup-schedule-enable").addEventListener("click",()=>changeBackupSchedule(true));
$("backup-schedule-disable").addEventListener("click",()=>changeBackupSchedule(false));
$("backup-protected-create").addEventListener("click",async()=>{
  if(!confirm("Create a NEW pinned snapshot? This may temporarily stop the application. The snapshot will not expire automatically and may consume storage. Verify it separately. Continue?"))return;
  const button=$("backup-protected-create");button.disabled=true;
  try{
    const result=await api("/api/admin/backups/protected-snapshot",{key:$("backup-schedule-source").value,confirmed:true});
    if(status?.admin){$("backup-schedule-result").textContent="Protected capture queued (job "+result.id+"). Verify the snapshot separately.";await renderJobs();}
  }catch(e){if(status?.admin)$("backup-schedule-result").textContent=e.message;}
  finally{if(status?.admin)button.disabled=false;}
});
$("kopia-initialize").addEventListener("click",async()=>{
  if(!confirm("Create a NEW encrypted repository in the configured empty /repository directory? Confirm the intended backup destination is mounted and the generated repository password is stored securely off-server. Do not use this to connect existing storage."))return;
  $("kopia-initialize").disabled=true;
  try{
    await api("/api/admin/kopia/initialize",{confirmed:true});
    if(!status?.admin)return;
    $("kopia-repository-result").textContent="Initialization queued. See installation activity; check repository connection after completion.";
    await renderJobs();
  }catch(e){if(status?.admin)$("kopia-repository-result").textContent=e.message;}
});
$("backup-core-snapshot").addEventListener("click",async()=>{
  if(!confirm("Create a private SQLite export of AfterGrid accounts and configuration, then snapshot it using connected Kopia. Active sessions are removed from the copy only. Finish all downloads and regional operations first; stable download metadata is included. This does not capture worker secrets or full recovery. Continue?"))return;
  const button=$("backup-core-snapshot"),root=$("backup-core-result");
  button.disabled=true;
  try{
    await api("/api/admin/backups/core/snapshot",{confirmed:true});
    if(status?.admin){root.textContent="Core database snapshot queued. See installation activity.";await renderJobs();}
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-core-verify").addEventListener("click",async()=>{
  if(!confirm("Restore the latest successful managed core database snapshot to a NEW private directory. Verify its integrity, administrator record and absence of login sessions. The restored copy contains sensitive credentials; retain it securely or remove it manually after review. Live data will not be replaced. Continue?"))return;
  const button=$("backup-core-verify"),root=$("backup-core-result");
  button.disabled=true;
  try{
    await api("/api/admin/backups/core/verify-snapshot",{confirmed:true});
    if(status?.admin){root.textContent="Core restore verification queued. See installation activity.";await renderJobs();}
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-worker-snapshot").addEventListener("click",async()=>{
  if(!confirm("Back up the worker database and existing generated application credentials to connected encrypted Kopia. Confirm you have saved the repository password securely off-server and no native backup administration is active. Unfinished jobs are marked interrupted in the copy only. This is not a verified recovery yet. Continue?"))return;
  const button=$("backup-worker-snapshot"),root=$("backup-core-result");
  button.disabled=true;
  try{
    await api("/api/admin/backups/worker/snapshot",{confirmed:true});
    if(status?.admin){root.textContent="Worker state snapshot queued. See installation activity.";await renderJobs();}
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-worker-verify").addEventListener("click",async()=>{
  if(!confirm("Restore the latest successful worker snapshot into a NEW private directory and verify the original export digest, database and generated secret sets. The restored envelope contains plaintext credentials. Keep it private and remove it manually when no longer needed. No live secrets or database will be changed. Continue?"))return;
  const button=$("backup-worker-verify"),root=$("backup-core-result");
  button.disabled=true;
  try{
    await api("/api/admin/backups/worker/verify-snapshot",{confirmed:true});
    if(status?.admin){root.textContent="Worker restore verification queued. See installation activity.";await renderJobs();}
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-manifest-generate").addEventListener("click",async()=>{
  if(!confirm("Check the exact latest successful managed snapshots in connected Kopia. No backups are created or pinned. Independent capture points do not constitute an atomic recovery set. Continue?"))return;
  const button=$("backup-manifest-generate"),root=$("backup-core-result");
  button.disabled=true;
  try{
    await api("/api/admin/backups/recovery-manifest",{confirmed:true});
    if(status?.admin){root.textContent="Recovery inventory queued. See installation activity; download after success.";await renderJobs();}
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-manifest-download").addEventListener("click",async()=>{
  const button=$("backup-manifest-download"),root=$("backup-core-result");
  button.disabled=true;
  try{
    const result=await api("/api/admin/backups/recovery-manifest");
    if(!status?.admin)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
    const link=document.createElement("a");link.href=url;link.download="aftergrid-recovery-inventory-"+result.manifest_job+".json";link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    root.textContent="Inventory from job "+result.manifest_job+": "+result.records.filter(x=>x.repository_status==="present").length+" of "+result.records.length+" reviewed sources present at generation. Keep it off-server; not a complete recovery package.";
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
$("backup-core-check").addEventListener("click",async()=>{
  const button=$("backup-core-check"),root=$("backup-core-result");
  button.disabled=true;root.textContent="Reading core backup requirements…";
  try{
    const plan=await api("/api/admin/backups/core");
    if(!status?.admin)return;
    root.replaceChildren();
    function line(value){const p=document.createElement("p");p.textContent=value;root.append(p);}
    line("Source plan only — no verified snapshot.");
    for(const source of plan.sources)line(source.path+" — "+source.guidance);
    for(const gap of plan.missing)line("Not covered: "+gap);
    line(plan.repository_guidance);
  }catch(e){if(status?.admin)root.textContent=e.message;}
  finally{button.disabled=false;}
});
function renderPreparednessApps(modules){
  const groups={knowledge:["kiwix"],navigation:["maps","routing"],communications:["meshmonitor","tak"],resources:["homebox","grocy","media"],learning:["kolibri","media","notes"]};
  for(const [group,ids] of Object.entries(groups)){
    const root=$("prep-"+group+"-apps");root.replaceChildren();
    for(const id of ids){
      const mod=modules.find(m=>m.id===id);
      const line=document.createElement("p");
      const label=mod?.name||id;
      const state=!mod?.installable?"status unavailable":mod.status;
      const local=["127.0.0.1","localhost"].includes(location.hostname);
      const accessible=mod?.installable&&state==="running"&&(!mod.admin_only||status?.admin)&&(!mod.loopback_only||(mod.shared&&mod.lan_url)||local);
      const link=document.createElement("a");
      link.textContent=label+" — "+state+(state==="running"&&!accessible?" (not available from this browser)":"");
      link.href="#app-"+id;
      if(accessible&&id!=="tak"){
        if(id==="maps"||id==="routing"){link.href="/maps";}
        else{
          const url=new URL(mod.shared&&mod.lan_url?mod.lan_url:location.href);
          if(mod.loopback_only)url.protocol="http:";
          url.port=mod.port;url.pathname="/";url.search="";url.hash="";
          link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";
        }
      }else if(accessible&&id==="tak"){link.href="/communications";}
      if(mod)line.append(link);else line.textContent=label+" — "+state;
      root.append(line);
    }
  }
}
async function refreshPreparedness(){
  const button=$("preparedness-refresh");button.disabled=true;
  $("preparedness-message").textContent="Reading local resource indicators…";
  try{
    const data=await api("/api/preparedness");
    const k=data.knowledge,n=data.navigation,c=data.communications,r=data.resources;
    $("prep-knowledge").textContent=k?k.indexed+" indexed archive(s) · "+k.unindexed+" unindexed. Indexing does not prove content quality or readability.":"Local library status unavailable.";
    $("prep-navigation").textContent=n?n.map_archives+" map archive(s) · "+(n.routing_graph_prepared?"Routing graph marker present":"No prepared routing graph")+" · "+n.waypoints+" waypoint(s) · "+n.saved_routes+" saved route(s).":"Navigation resource status unavailable.";
    $("prep-communications").textContent=c?c.pace_plans+" PACE plan(s) · "+c.device_records+" device record(s) · "+c.devices_ever_checked+" ever manually checked. Not live device status.":"Communications records unavailable.";
    $("prep-resources").textContent=r?r.households+" household(s) · "+r.mapped_locations+" mapped location(s). Counts are not available stock.":"Resource directory unavailable.";
    $("preparedness-message").textContent="Local indicators read. Refresh after changing content or plans.";
  }catch(e){
    for(const id of ["knowledge","navigation","communications","resources"])$("prep-"+id).textContent="Not checked.";
    $("preparedness-message").textContent=e.message;
  }finally{button.disabled=false;}
}
$("preparedness-refresh").addEventListener("click",async()=>{
  $("preparedness-refresh").disabled=true;
  try{await renderModules();await refreshPreparedness();}
  catch(e){$("preparedness-message").textContent=e.message;}
  finally{$("preparedness-refresh").disabled=false;}
});
function renderWizard(modules){
  const root=$("wizard-options");
  const saved=status.submitted_selection;
  const checked=new Set(saved||[...root.querySelectorAll("input:checked")].map(i=>i.value));
  root.replaceChildren();
  $("essentials").disabled=!!saved||submittingWizard;
  $("skip-wizard").disabled=!!saved||submittingWizard;
  $("wizard-form").querySelector("button[type=submit]").textContent=saved?"Retry saved selection":"Install selected";
  if(saved){
    for(const id of saved){
      const p=document.createElement("p");p.textContent=modules.find(m=>m.id===id)?.name||id;root.append(p);
    }
    $("wizard-message").textContent="Submission not yet confirmed. Retry this saved selection; applications already queued will not be queued twice.";
    return;
  }
  $("wizard-message").textContent="";
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
  }catch(e){try{await refresh();}catch(_){/* preserve original submission error */}error(e.message);}
  finally{submittingWizard=false;for(const el of controls)el.disabled=false; $("essentials").disabled=!!status?.submitted_selection; $("skip-wizard").disabled=!!status?.submitted_selection; $("wizard-form").querySelector("button[type=submit]").disabled=false;}
}
$("essentials").addEventListener("click",()=>{
  for(const input of $("wizard-options").querySelectorAll("input"))input.checked=["kiwix","homebox","grocy","kopia"].includes(input.value);
});
$("wizard-form").addEventListener("submit",event=>{
  event.preventDefault();
  const chosen=status.submitted_selection||[...$("wizard-options").querySelectorAll("input:checked")].map(i=>i.value);
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
$("content-pack").addEventListener("change",event=>{
  if(event.target.value)$("content-search").elements.q.value=event.target.value;
});
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

async function renderInstallationSummary(){
  const root=$("installation-summary");
  try{
    const report=await api("/api/admin/installation-summary");
    if(!status?.admin)return;
    root.replaceChildren();
    const rows=report.applications;
    if(!rows.length){root.textContent="No optional applications have been selected for installation.";return;}
    const counts={queued:0,running:0,succeeded:0,failed:0,interrupted:0};
    for(const item of rows)if(Object.hasOwn(counts,item.state))counts[item.state]++;
    const total=document.createElement("p");
    total.textContent=counts.succeeded+" completed · "+counts.running+" installing · "+counts.queued+" queued · "+(counts.failed+counts.interrupted)+" need attention";
    root.append(total);
    for(const item of rows){
      const row=document.createElement("article"),title=document.createElement("strong"),stage=document.createElement("p");
      title.textContent=item.name+" · "+({succeeded:"Installation completed",running:"Installing",queued:"Queued",failed:"Installation failed",interrupted:"Interrupted"}[item.state]||"Unknown");
      stage.textContent=item.stage+" · Job #"+item.id;
      row.append(title,stage);
      if(item.total>0){const p=document.createElement("progress");p.max=item.total;p.value=item.completed;p.setAttribute("aria-label","Completed stages for "+item.name);row.append(p);}
      if(item.retry_available&&!status.recovery_maintenance&&!status.recovery_core_only&&!status.recovery_offline){
        const b=document.createElement("button");b.type="button";b.textContent="Retry "+item.name;
        b.addEventListener("click",async()=>{
          if(!confirm("Retry "+item.name+" using existing data?"))return;
          b.disabled=true;
          try{await api("/api/admin/modules/"+item.module+"/install",{});await renderJobs();await renderInstallationSummary();await renderModules();}
          catch(e){error(e.message);b.disabled=false;}
        });row.append(b);
      }
      root.append(row);
    }
  }catch(e){if(status?.admin)root.textContent="Installation summary unavailable: "+e.message;}
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
    if(job.action==="install"&&["failed","interrupted"].includes(job.state)&&!pending.has(job.module)&&jobs.find(j=>j.module===job.module)?.id===job.id&&!status.recovery_core_only&&!status.recovery_offline&&!status.recovery_maintenance){
      const retry=document.createElement("button");retry.type="button";retry.textContent="Retry this application";
      retry.addEventListener("click",async()=>{if(!confirm("Retry installation of "+job.module+" using existing application data?"))return;retry.disabled=true;try{await api("/api/admin/modules/"+job.module+"/install",{});await renderJobs();await renderModules();}catch(e){error(e.message);retry.disabled=false;}});row.append(retry);
    }
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
  try{if(await renderJobs())await renderModules();await renderInstallationSummary();await renderDownloads();await refreshMaps();await refreshRoutingData();}catch(e){error(e.message);}finally{polling=false;}
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
let overviewGeneration=0,overviewOffset=0,overviewNext=null;
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
  if(!admin)clearOverview();
  if(!admin){$("household-form").reset();$("location-form").reset();$("inventory-connect").reset();$("inventory-connections").replaceChildren();$("native-locations").replaceChildren();$("household-message").textContent="";}
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
      const report=document.createElement("div");
      directoryButton(card,"Live inventory",async()=>{
        report.textContent="Reading native inventory…";
        try{
          const r=await api("/api/admin/inventory/report/"+l.id);
          report.replaceChildren();
          if(r.module==="homebox"){report.textContent=r.item_records+" item records in "+r.location+" (not unit quantity; excludes child locations).";}
          else if(!r.products.length){report.textContent="No stock entries in "+r.location+".";}
          else for(const p of r.products){const line=document.createElement("p");line.textContent=p.product+": "+p.amount+" "+p.unit;report.append(line);}
        }catch(e){report.textContent=e.message;}
      });
      card.append(report);
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
  const overviewHousehold=$("inventory-overview-household");
  const previous=overviewHousehold.value;
  householdOptions(overviewHousehold,"All households",previous);
  option(overviewHousehold,"0","Shared / unassigned");
  if(previous==="0")overviewHousehold.value="0";
  clearOverview();
  renderDirectory();
  if(status?.admin)await refreshInventoryConnections();
}
function clearOverview(){
  overviewGeneration++;
  overviewOffset=0;overviewNext=null;
  $("inventory-overview-results").replaceChildren();
  $("inventory-overview-prev").disabled=true;
  $("inventory-overview-next").disabled=true;
  $("inventory-overview-form").querySelector("button").disabled=false;
}
async function loadOverview(offset){
  const generation=++overviewGeneration;
  const root=$("inventory-overview-results");
  const form=$("inventory-overview-form");
  const household=$("inventory-overview-household").value;
  const q=new URLSearchParams({basis:$("inventory-overview-basis").value,offset:String(offset)});
  if(household!=="")q.set("household",household);
  root.textContent="Reading native inventory…";
  form.querySelector("button").disabled=true;
  $("inventory-overview-prev").disabled=true;$("inventory-overview-next").disabled=true;
  try{
    const result=await api("/api/admin/inventory/overview?"+q);
    if(generation!==overviewGeneration||!status?.admin)return;
    overviewOffset=result.offset;overviewNext=result.next_offset;
    root.replaceChildren();
    const summary=document.createElement("p");
    summary.textContent=result.locations.length?
      "Locations "+(result.offset+1)+"–"+(result.offset+result.locations.length)+" of "+result.total_locations+" · "+result.available_locations+" available · "+result.unavailable_locations+" unavailable. Homebox item records on this page: "+(result.homebox_item_records??"not available")+". Not unit quantities.":
      "No mapped locations match this filter.";
    root.append(summary);
    for(const item of result.locations){
      const card=document.createElement("article"),title=document.createElement("strong"),detail=document.createElement("p");
      title.textContent=item.label+" · "+item.module;
      detail.textContent="Owner: "+(item.owner_name||"Shared / unassigned")+" · Storage: "+(item.storage_name||"Shared / unassigned");
      card.append(title,detail);
      const line=document.createElement("p");
      if(item.state!=="available"){line.textContent="Unavailable: "+item.error;card.append(line);}
      else if(item.module==="homebox"){line.textContent=item.item_records+" direct item records in "+item.native_label;card.append(line);}
      else{
        line.textContent=item.products.length?"Stock in "+item.native_label:"No stock entries in "+item.native_label;
        card.append(line);
        if(item.products.length){
          const list=document.createElement("ul");
          for(const product of item.products){const li=document.createElement("li");li.textContent=product.product+": "+product.amount+" "+product.unit;list.append(li);}
          card.append(list);
        }
      }
      root.append(card);
    }
    $("inventory-overview-prev").disabled=offset===0;
    $("inventory-overview-next").disabled=overviewNext===null;
  }catch(e){if(generation===overviewGeneration&&status?.admin){root.textContent=e.message;$("inventory-overview-prev").disabled=overviewOffset===0;}}
  finally{if(generation===overviewGeneration)form.querySelector("button").disabled=false;}
}
$("inventory-overview-form").addEventListener("submit",event=>{event.preventDefault();loadOverview(0);});
$("inventory-overview-household").addEventListener("change",clearOverview);
$("inventory-overview-basis").addEventListener("change",clearOverview);
$("inventory-overview-prev").addEventListener("click",()=>loadOverview(Math.max(0,overviewOffset-8)));
$("inventory-overview-next").addEventListener("click",()=>{if(overviewNext!==null)loadOverview(overviewNext);});
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

async function refreshInventoryConnections(){
  const result=await api("/api/admin/inventory/connections");
  if(!status?.admin)return;
  const root=$("inventory-connections");root.replaceChildren();
  for(const [module,connected] of Object.entries(result)){
    const row=document.createElement("article"),p=document.createElement("p");
    p.textContent=module+" — "+(connected?"Key saved":"Not connected");row.append(p);
    if(connected){
      directoryButton(row,"Discover locations",async()=>showNativeLocations(module,(await api("/api/admin/inventory/locations/"+module)).locations));
      directoryButton(row,"Disconnect",async()=>{
        if(!confirm("Forget the saved API key? Native inventory and location mappings remain unchanged."))return;
        await api("/api/admin/inventory/disconnect",{module});clearOverview();$("native-locations").replaceChildren();await refreshInventoryConnections();
      });
    }
    root.append(row);
  }
}
function showNativeLocations(module,locations){
  if(!status?.admin)return;
  const root=$("native-locations");root.replaceChildren();
  if(!locations.length){root.textContent="No native locations found.";return;}
  for(const l of locations){
    const row=document.createElement("article"),p=document.createElement("p");p.textContent=l.label;row.append(p);
    directoryButton(row,"Use location",()=>{
      const existing=directory.locations.find(x=>x.module===module&&x.native_id===l.native_id);
      const form=$("location-form");form.reset();
      form.elements.module.value=module;form.elements.native_id.value=l.native_id;form.elements.label.value=l.label;
      if(existing)for(const key of ["id","owner_id","storage_id"])form.elements[key].value=existing[key]??"";
      form.scrollIntoView();
    });
    root.append(row);
  }
}
$("inventory-connect").addEventListener("submit",async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector("button");button.disabled=true;
  const data=Object.fromEntries(new FormData(form));form.elements.key.value="";
  try{const r=await api("/api/admin/inventory/connect",data);clearOverview();await refreshInventoryConnections();showNativeLocations(data.module,r.locations);$("household-message").textContent="Native key saved; select a location.";}
  catch(e){$("household-message").textContent=e.message;}
  finally{button.disabled=false;}
});
async function refreshMaps(){
  const result=await api("/api/admin/maps");
  if(!status?.admin)return;
  const root=$("map-status");root.replaceChildren();
  const state=document.createElement("p");state.textContent="Map operation: "+result.state+" — "+(result.detail||"");root.append(state);
  if(result.estimate_bytes!==undefined){const p=document.createElement("p");p.textContent="Estimated archive: "+bytes(result.estimate_bytes)+" (approximate; extra space required)";root.append(p);}
  const free=document.createElement("p");free.textContent="Available storage: "+bytes(result.free_bytes);root.append(free);
  for(const file of result.files){const p=document.createElement("p");p.textContent=file.name+" — "+bytes(file.size_bytes);root.append(p);}
  if(result.output){const pre=document.createElement("pre");pre.textContent=result.output;root.append(pre);}
  $("map-download").hidden=result.state!=="estimated";
}
$("map-estimate").addEventListener("submit",async event=>{
  event.preventDefault();
  const v=Object.fromEntries(new FormData(event.currentTarget));
  try{await api("/api/admin/maps/estimate",{build:v.build,bbox:[v.west,v.south,v.east,v.north].map(Number),zoom:Number(v.zoom)});await refreshMaps();}
  catch(e){error(e.message);}
});
$("map-download").addEventListener("click",async()=>{
  if(!confirm("Download this regional archive? Internet and free storage are required."))return;
  try{await api("/api/admin/maps/download",{});await refreshMaps();}catch(e){error(e.message);}
});
async function refreshRoutingData(){
  const r=await api("/api/admin/routing-data");if(!status?.admin)return;
  const select=$("routing-estimate").elements.region;
  if(!select.options.length)for(const item of r.regions)option(select,item.id,item.name);
  const root=$("routing-status");root.replaceChildren();
  function line(value){const p=document.createElement("p");p.textContent=value;root.append(p);}
  line("Routing data: "+r.state+" — "+(r.detail||""));
  line("Available storage: "+bytes(r.free_bytes));
  if(r.size_bytes!==undefined)line("PBF size: "+bytes(r.size_bytes)+" (graph requires additional space)");
  for(const file of r.files)line(file.name+" — "+bytes(file.size_bytes));
  if(r.state==="downloading"&&r.size_bytes){const p=document.createElement("progress");p.max=r.size_bytes;p.value=r.bytes||0;root.append(p);line(bytes(r.bytes||0)+" downloaded");}
  line("Selected on disk: "+r.selected_slot+" · "+(r.graph_ready?"prepared":"not prepared")+" (see application status for actual availability)");
  line("Slot A: "+(r.original_ready?"ready":"not prepared")+" · Slot B: "+(r.candidate_ready?"ready":"not prepared"));
  for(const archived of r.archives||[])line("Retained archive: "+archived.name+(archived.complete?"":" (incomplete; inspect storage)"));
  const controls=$("routing-graph-controls");controls.replaceChildren();
  const busy=pending.has("routing")||["estimating","downloading","verifying"].includes(r.state);
  function graphButton(label,action,question){
    const b=document.createElement("button");b.type="button";b.textContent=label;b.disabled=busy;
    b.addEventListener("click",async()=>{if(!confirm(question))return;b.disabled=true;try{await api("/api/admin/modules/routing/"+action,{});await renderJobs();await renderModules();await refreshRoutingData();}catch(e){error(e.message);b.disabled=false;}});controls.append(b);
  }
  const a=r.selected_slot==="tiles", b=r.selected_slot==="tiles-next";
  if((a&&r.original_ready&&!r.candidate_occupied&&r.files.some(f=>f.name==="incoming.osm.pbf"))||(b&&r.candidate_ready&&!r.original_occupied&&r.files.some(f=>f.name==="region.osm.pbf")))
    graphButton("Prepare inactive graph slot","prepare-graph","Build a separate graph? This uses substantial CPU, RAM and disk. Existing routing remains selected.");
  if(r.original_ready&&r.candidate_ready&&a){
    graphButton("Switch to slot B","activate-graph","Switch routing to slot B? Routing briefly stops. Slot A is retained.");
    graphButton("Archive inactive slot B","archive-replacement","Move inactive slot B and its source into retained archives? This frees the slot, not disk space. Slot B will no longer be available for immediate rollback.");
  }
  if(r.original_ready&&r.candidate_ready&&b){
    graphButton("Switch to slot A","rollback-graph","Switch routing to slot A? Routing briefly stops. Slot B is retained.");
    graphButton("Archive inactive slot A","archive-original","Move inactive slot A and its source into retained archives? This frees the slot, not disk space. Slot A will no longer be available for immediate rollback.");
  }
  $("routing-download").hidden=r.state!=="estimated";
}
$("routing-estimate").addEventListener("submit",async event=>{
  event.preventDefault();try{await api("/api/admin/routing-data/estimate",{region:event.currentTarget.elements.region.value});await refreshRoutingData();}catch(e){error(e.message);}
});
$("routing-download").addEventListener("click",async()=>{
  if(!confirm("Download selected PBF? Existing routing graph will not be replaced."))return;
  try{await api("/api/admin/routing-data/download",{});await refreshRoutingData();}catch(e){error(e.message);}
});
refresh().catch(e=>error(e.message));
