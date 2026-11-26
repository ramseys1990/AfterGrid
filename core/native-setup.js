"use strict";
const field=id=>document.getElementById(id);
const moduleId=location.pathname.split("/").pop();
const homebox=moduleId==="homebox";
field("title").textContent=(homebox?"Homebox":"Grocy")+" native account setup";
field("guidance").textContent=homebox?"Create one account for your shared collection, or verify an existing account. Its email is only a local login identifier; no email is sent. After verification, return to the card and Share on LAN to close registration.":"For a fresh Grocy installation, replace its admin/admin default password before sharing. Existing installations should use Verify existing account. This form never resets an unknown administrator password.";
const option=document.createElement("option");option.value=homebox?"create":"secure-default";option.textContent=homebox?"Create native account":"Replace default administrator password";field("mode").prepend(option);field("mode").value=option.value;
field("username-label").textContent=homebox?"Native account email":"Native username";
if(!homebox){field("username").value="admin";field("username").readOnly=true;}
function modeChanged(){
  const verify=field("mode").value==="verify";
  field("name-label").hidden=!homebox||verify;field("name").required=homebox&&!verify;
  field("confirm-label").hidden=verify;field("password-confirm").required=!verify;
  field("password").minLength=verify?1:12;field("password").autocomplete=verify?"current-password":"new-password";
  field("password-label").textContent=verify?"Native password":"New native password (at least 12 characters)";
  field("submit").textContent=verify?"Verify native account":homebox?"Create native account":"Replace default password";
  field("password").value="";field("password-confirm").value="";field("result").textContent="";
}
field("mode").addEventListener("change",modeChanged);modeChanged();
field("native-form").addEventListener("submit",async event=>{
  event.preventDefault();if(field("submit").disabled)return;const mode=field("mode").value;
  if(mode!=="verify"&&field("password").value!==field("password-confirm").value){field("result").textContent="The new passwords must match.";return;}
  const payload={mode,username:field("username").value,password:field("password").value,confirmed:field("confirmed").checked};
  if(homebox&&mode==="create")payload.name=field("name").value;
  field("submit").disabled=true;field("result").textContent="Contacting the local native application…";
  try{
    const response=await fetch("/api/admin/modules/"+moduleId+"/native-setup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Native setup unavailable");
    field("mode").value="verify";modeChanged();field("result").textContent=result.message;
  }catch(e){field("result").textContent=e.message+" If a change may have completed, verify the existing account before retrying setup.";}
  finally{payload.password="";field("password").value="";field("password-confirm").value="";field("submit").disabled=false;}
});
window.addEventListener("pagehide",()=>{field("password").value="";field("password-confirm").value="";});
