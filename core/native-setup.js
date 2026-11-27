"use strict";
const field=id=>document.getElementById(id);
const moduleId=location.pathname.split("/").pop();
const homebox=moduleId==="homebox";
const media=moduleId==="media";
const kolibri=moduleId==="kolibri";
const creates=homebox||media||kolibri;
field("title").textContent=(homebox?"Homebox":media?"Jellyfin":kolibri?"Kolibri":"Grocy")+" native account setup";
field("guidance").textContent=homebox?"Create one account for your shared collection, or verify an existing account. Its email is only a local login identifier; no email is sent. After verification, return to the card and Share on LAN to close registration.":media?"Create the administrator for a fresh Jellyfin installation while its port stays local-only. Setup disables remote access. If setup was interrupted after the account was created, choose Finish interrupted setup with the same credentials. Existing completed installations use Verify existing account. This form never resets an existing password. Configure /media and offline library providers inside Jellyfin after sharing.":"For a fresh Grocy installation, replace its admin/admin default password before sharing. Existing installations should use Verify existing account. This form never resets an unknown administrator password.";
if(kolibri)field("guidance").textContent="Create the device administrator and AfterGrid learning facility on a fresh Kolibri installation. Guests can read imported content; learner accounts require passwords and self-registration stays disabled. New setup disables automatic and learner-requested downloads. Native setup temporarily stores its provisioning task; this form verifies and clears that task before reporting success. After an interrupted attempt, use Verify existing account with the same credentials. Import channels inside Kolibri after sharing both application ports on LAN.";
const option=document.createElement("option");option.value=creates?"create":"secure-default";option.textContent=creates?"Create native account":"Replace default administrator password";field("mode").prepend(option);field("mode").value=option.value;
if(media){const finish=document.createElement("option");finish.value="finish-setup";finish.textContent="Finish interrupted setup";field("mode").append(finish);}
field("username-label").textContent=homebox?"Native account email":"Native username";
if(!homebox){field("username").value="admin";field("username").readOnly=!media&&!kolibri;}
function modeChanged(){
  const verify=field("mode").value==="verify";
  const existing=verify||field("mode").value==="finish-setup";
  field("name-label").hidden=!homebox||verify;field("name").required=homebox&&!verify;
  field("confirm-label").hidden=existing;field("password-confirm").required=!existing;
  field("password").minLength=existing?1:12;field("password").autocomplete=existing?"current-password":"new-password";
  field("password-label").textContent=existing?"Native password":"New native password (at least 12 characters)";
  field("submit").textContent=verify?"Verify native account":existing?"Finish interrupted setup":creates?"Create native account":"Replace default password";
  field("password").value="";field("password-confirm").value="";field("result").textContent="";
}
field("mode").addEventListener("change",modeChanged);modeChanged();
field("native-form").addEventListener("submit",async event=>{
  event.preventDefault();if(field("submit").disabled)return;const mode=field("mode").value;
  if(!["verify","finish-setup"].includes(mode)&&field("password").value!==field("password-confirm").value){field("result").textContent="The new passwords must match.";return;}
  const payload={mode,username:field("username").value,password:field("password").value,confirmed:field("confirmed").checked};
  if(homebox&&mode==="create")payload.name=field("name").value;
  field("submit").disabled=true;field("result").textContent="Contacting the local native application.";
  try{
    const response=await fetch("/api/admin/modules/"+moduleId+"/native-setup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Native setup unavailable");
    field("mode").value="verify";modeChanged();field("result").textContent=result.message;
  }catch(e){field("result").textContent=e.message+(media?" If an account may have been created, use Finish interrupted setup with the same credentials. Do not create it again.":" If a change may have completed, verify the existing account before retrying setup.");}
  finally{payload.password="";field("password").value="";field("password-confirm").value="";field("submit").disabled=false;}
});
window.addEventListener("pagehide",()=>{field("password").value="";field("password-confirm").value="";});
