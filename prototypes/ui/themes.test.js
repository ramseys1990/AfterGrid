"use strict";
// Run from this directory: node --test themes.test.js
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const T=require("./themes.js");
test("four bundled themes and all eight appearance palettes pass validation",()=>{
  assert.equal(T.builtins.length,4);
  for(const t of T.builtins){
    assert.ok(T.validate(t),t.id);
    for(const mode of ["light","dark"]){
      const x=T.resolve(t.id,mode,false);
      assert.equal(x.theme.id,t.id);assert.equal(x.appearance,mode);assert.equal(x.tokens,t[mode]);
    }
  }
});
test("invalid inputs cannot become CSS tokens",()=>{
  const t=structuredClone(T.builtins[0]);
  for(const invalid of [{...t,radius:99},{...t,id:"../../x"},{...t,extra:"javascript"},{...t,dark:{...t.dark,bg:"url(https://example.com)"}},{...t,dark:{...t.dark,text:t.dark.bg}},{...t,dark:{...t.dark,extra:"#ffffff"}}]){
    assert.equal(T.validate(invalid),false);
  }
});
test("system mode, unknown theme and protected built-ins",()=>{
  assert.equal(T.resolve("missing","system",true).theme.id,"overwatch");
  assert.equal(T.resolve("outpost","system",false).appearance,"light");
  const duplicate={...T.builtins[0],name:"Impostor"};
  assert.equal(T.resolve("overwatch","dark",true,[duplicate]).theme.name,"Overwatch");
  const custom={...T.builtins[0],id:"community.example",name:"Example"};
  assert.ok(T.validate(custom));
  assert.equal(T.resolve(custom.id,"light",false,[custom]).theme.id,custom.id);
});
test("renderer applies only known tokens and fixed metadata",()=>{
  const values={};const element={style:{setProperty:(k,v)=>values[k]=v},dataset:{}};
  T.apply(element,T.resolve("fortress","dark",false));
  assert.equal(values["--accent"],"#ECAA39");
  assert.equal(values["--radius"],"3px");
  assert.equal(Object.keys(values).length,10);
  assert.equal(element.dataset.theme,"fortress");assert.equal(element.style.colorScheme,"dark");
});
test("prototype syntax and offline boundary",()=>{
  const html=fs.readFileSync(__dirname+"/index.html","utf8");
  const js=fs.readFileSync(__dirname+"/prototype.js","utf8");
  new vm.Script(js);
  assert.match(html,/connect-src 'none'/);
  assert.doesNotMatch(js,/\b(fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/);
  for(const asset of ["style.css","themes.js","prototype.js"])assert.ok(html.includes('"'+asset+'"'));
});

test("versioned theme manifests, import round trip and built-ins",()=>{
  const p=JSON.parse(fs.readFileSync(__dirname+"/example-theme.json","utf8"));
  assert.ok(T.builtinPackages.every(x=>T.validatePackage(x,false)));
  assert.ok(T.validatePackage(p));
  assert.equal(T.parsePackage(JSON.stringify(p)).theme.id,p.theme.id);
  assert.equal(T.loadPackages(JSON.stringify(T.addPackage([],p)))[0].theme.id,p.theme.id);
  assert.equal(T.resolve(p.theme.id,"dark",false,[p.theme]).theme.name,p.theme.name);
  assert.throws(()=>T.addPackage([p],p));
  assert.throws(()=>T.parsePackage(JSON.stringify({...p,schema_version:2})));
  assert.throws(()=>T.parsePackage(JSON.stringify({...p,theme:{...p.theme,id:"overwatch"}})));
  assert.throws(()=>T.parsePackage(JSON.stringify({...p,theme:{...p.theme,css:"body{display:none}"}})));
  assert.throws(()=>T.parsePackage(" ".repeat(T.MAX_BYTES+1)));
  assert.throws(()=>T.parsePackage("{"));
  assert.equal(T.loadPackages("invalid").length,0);
  assert.equal(T.loadPackages(JSON.stringify([p,p,{}])).length,1);
  const full=Array.from({length:T.MAX_CUSTOM},(_,i)=>({...p,theme:{...p.theme,id:"local.sample"+i}}));
  assert.throws(()=>T.addPackage(full,p));
});
