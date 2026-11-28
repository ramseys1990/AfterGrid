/* Standalone visual editor; no production APIs, credentials or external resources. */
"use strict";
(function(root){
  const T=root.AfterGridTheme;
  const labels={bg:"Page background",panel:"Card surface",sidebar:"Navigation",hero:"Feature surface",text:"Primary text",muted:"Secondary text",accent:"Accent",onAccent:"Button text",border:"Border"};
  function node(tag,text,attrs={}){
    const e=document.createElement(tag);
    if(text!==null)e.textContent=text;
    for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);
    return e;
  }
  function mount(host,base,onSave){
    let draft=T.createDraft(base,"local.my-theme","My theme"), mode="dark";
    host.replaceChildren();
    const title=node("h2","Theme Studio (future)");
    const intro=node("p","Create a local theme from the selected palette. Changes remain inside this preview until you save. Both light and dark palettes must pass the initial contrast checks.");
    host.append(title,intro);
    const controls=node("div",null,{class:"grid studio-fields"});
    function field(label,id,value,limit,set){
      const wrap=node("div",null,{class:"field"}), input=node("input",null,{id,type:"text",maxlength:String(limit)});
      input.value=value;input.addEventListener("input",()=>{set(input.value);update();});
      wrap.append(node("label",label,{for:id}),input);controls.append(wrap);return input;
    }
    const name=field("Theme name","studio-name",draft.theme.name,48,v=>draft.theme.name=v);
    const ident=field("Package ID","studio-id",draft.theme.id,64,v=>draft.theme.id=v);
    const author=field("Author","studio-author",draft.author,100,v=>draft.author=v);
    const license=field("License","studio-license",draft.license,100,v=>draft.license=v);
    const desc=field("Description","studio-description",draft.theme.description,160,v=>draft.theme.description=v);
    const modeBox=node("div",null,{class:"field"});
    const modeInput=node("select",null,{id:"studio-mode"});
    for(const value of ["light","dark"])modeInput.append(node("option",value==="light"?"Light":"Dark",{value}));
    modeInput.value=mode;modeBox.append(node("label","Edit palette",{for:"studio-mode"}),modeInput);controls.append(modeBox);
    const radiusBox=node("div",null,{class:"field"});
    const radius=node("input",null,{id:"studio-radius",type:"range",min:"0",max:"16",step:"1"});
    radius.value=draft.theme.radius;
    const radiusLabel=node("label","Corner radius: "+radius.value+" px",{for:"studio-radius"});
    radiusBox.append(radiusLabel,radius);controls.append(radiusBox);
    radius.addEventListener("input",()=>{draft.theme.radius=Number(radius.value);radiusLabel.textContent="Corner radius: "+radius.value+" px";update();});
    host.append(controls);
    const palette=node("div",null,{class:"studio-palette"});
    const preview=node("section",null,{class:"studio-preview","aria-label":"Theme preview"});
    const nav=node("div","AfterGrid / Overview",{class:"studio-nav"});
    const hero=node("div",null,{class:"hero"});hero.append(node("div","Local resource system",{class:"eyebrow"}),node("h3","Life beyond the grid."),node("p","A sample of your theme."));
    const cards=node("div",null,{class:"grid"});
    for(const [h,n] of [["Knowledge library","Example resource"],["Maps & navigation","Example resource"]]){
      const card=node("article",null,{class:"tile"});card.append(node("h3",h),node("p",n),node("span","Open resource",{class:"studio-demo-button"}));cards.append(card);
    }
    preview.append(nav,hero,cards);
    const diagnostics=node("div",null,{class:"stack"}), message=node("p","",{role:"status","aria-live":"polite",id:"studio-result"});
    const save=node("button","Save local theme",{id:"studio-save",type:"button"});
    const reset=node("button","Reset draft",{id:"studio-reset",type:"button",class:"quiet"});
    const actions=node("div",null,{class:"actions"});actions.append(save,reset);
    host.append(palette,preview,diagnostics,actions,message);
    function drawColors(){
      palette.replaceChildren();
      for(const [key,label] of Object.entries(labels)){
        const row=node("div",null,{class:"studio-color"});
        const input=node("input",null,{type:"color",id:"studio-"+key});input.value=draft.theme[mode][key];
        const hex=node("output",input.value.toUpperCase(),{for:input.id});
        input.addEventListener("input",()=>{draft.theme[mode][key]=input.value.toUpperCase();hex.textContent=draft.theme[mode][key];update();});
        row.append(node("label",label,{for:input.id}),input,hex);palette.append(row);
      }
    }
    function update(){
      // Preview only safe hex tokens; metadata never enters CSS or markup.
      T.apply(preview,{theme:{id:"studio-preview",radius:draft.theme.radius},appearance:mode,tokens:draft.theme[mode]});
      diagnostics.replaceChildren();
      for(const result of T.contrastReport(draft.theme)){
        const line=node("p",result.mode+" palette: "+result.minimum.toFixed(2)+":1 ("+result.pair+") — "+(result.passes?"passes initial text checks":"needs improvement"));
        diagnostics.append(line);
      }
      const valid=T.validatePackage(draft);save.disabled=!valid;
      message.textContent=valid?"Draft passes package checks. Save to use it locally.":"Adjust package fields or contrast before saving.";
    }
    modeInput.addEventListener("change",()=>{mode=modeInput.value;drawColors();update();});
    reset.addEventListener("click",()=>{
      draft=T.createDraft(base,"local.my-theme","My theme");mode="dark";
      name.value=draft.theme.name;ident.value=draft.theme.id;author.value=draft.author;license.value=draft.license;desc.value=draft.theme.description;
      modeInput.value=mode;radius.value=draft.theme.radius;radiusLabel.textContent="Corner radius: "+radius.value+" px";drawColors();update();
    });
    save.addEventListener("click",()=>{if(!T.validatePackage(draft))return;try{onSave(JSON.stringify(draft));}catch(e){message.textContent=e.message||"Unable to save local theme.";}});
    drawColors();update();
  }
  root.AfterGridStudio={mount};
})(globalThis);
